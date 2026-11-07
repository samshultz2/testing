"""Deeper exam analytics for the Insights page (/results/analytics/insights).

Every analysis is branch-scoped (``bid`` = branch in view, None = all),
batched (a handful of grouped queries, never one per student) and sample-size
aware: rates carry a 95% range and a "small group" flag, correlations need
``MIN_CORRELATION_N`` students, and gaps say whether they are a real
difference or could be chance (utils.stats_guard). Grading rules come from
utils.exam_rules so "credit" and "5 credits incl. English and Maths" mean the
same as everywhere else.

Sections
--------
value_added        WAEC grade vs what the student's SSS3 class scores predicted,
                   per subject and per teacher
mock_accuracy      last mock WAEC of the session vs the real WAEC, per subject
bece_to_waec       JSS3 BECE results vs WAEC three years later
near_credit        D7s (one grade short of a credit) and pupils one grade short
                   of 5 credits incl. English and Maths
combinations       subject combinations / electives vs the 5-credit rate
teachers           per-teacher credit rate across years (+ value added)
fairness           gender / arm / branch / boarding gaps, with significance
attendance_bands   attendance bands vs the 5-credit rate
cohorts            intake cohorts (JSS1 year) — stayed, left, joined, outcome
readiness_over_time  share on track at each mock sitting through the session
weak_topics        weakest mock-JAMB topics per subject
"""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

from models import db, Student
from utils import exam_rules as R
from utils.stats_guard import (rate, gap_verdict, correlation_ci, confidence,
                               MIN_CORRELATION_N, MIN_GROUP_N)


# --------------------------------------------------------------------------- #
# Shared loaders
# --------------------------------------------------------------------------- #
def waec_by_student(year, bid=None, model=None):
    """{student_id: {canonical subject: grade}} for one WAEC (or NECO) year."""
    from models import WAECResult
    model = model or WAECResult
    q = db.session.query(model.student_id, model.subject, model.grade).filter(model.exam_year == year)
    if bid is not None:
        q = q.join(Student, Student.id == model.student_id).filter(Student.branch_id == bid)
    out = defaultdict(dict)
    for sid, subj, grade in q.all():
        if grade:
            out[sid][R.canonical_subject(subj)] = R.norm_grade(grade)
    return dict(out)


def _session_terms(year):
    from utils.helpers import session_for_exam_year
    from models import Term
    sess = session_for_exam_year(year)
    if not sess:
        return None, []
    return sess, Term.query.filter_by(session_id=sess.id).order_by(Term.term_number).all()


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = mean(xs), mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if not sxx or not syy:
        return None
    return sxy / (sxx * syy) ** 0.5


def _fit(xs, ys):
    """Least-squares line y = a + b·x; (a, b) or None."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _meets_map(waec):
    return {sid: R.five_credit_status(g) for sid, g in waec.items()}


# --------------------------------------------------------------------------- #
# 1. Value added (internal SSS3 scores → expected WAEC grade)
# --------------------------------------------------------------------------- #
def internal_scores(year, student_ids):
    """{(student_id, canonical subject): (score %, teacher)} — each student's
    latest SSS3-session term result per subject."""
    from models import TermResult, ClassSubject, Subject
    sess, terms = _session_terms(year)
    if not terms or not student_ids:
        return {}
    rows = (db.session.query(TermResult.student_id, TermResult.term_id, TermResult.total_score,
                             Subject.name, ClassSubject.teacher_name)
            .join(ClassSubject, ClassSubject.id == TermResult.class_subject_id)
            .join(Subject, Subject.id == ClassSubject.subject_id)
            .filter(TermResult.term_id.in_([t.id for t in terms]),
                    TermResult.student_id.in_(list(student_ids)),
                    TermResult.total_score.isnot(None))
            .order_by(TermResult.term_id).all())
    out = {}
    for sid, _tid, score, subj, teacher in rows:
        out[(sid, R.canonical_subject(subj))] = (float(score), (teacher or '').strip())
    return out


def value_added(year, bid=None):
    waec = waec_by_student(year, bid)
    internal = internal_scores(year, set(waec))
    pairs = []
    for (sid, subj), (score, teacher) in internal.items():
        g = waec.get(sid, {}).get(subj)
        if g:
            pairs.append({'sid': sid, 'subject': subj, 'teacher': teacher or 'Unassigned',
                          'internal': score, 'actual': R.points(g), 'credit': R.is_credit(g)})
    out = {'n': len(pairs), 'subjects': [], 'teachers': [], 'r': None, 'ci': None,
           'enough': len(pairs) >= MIN_CORRELATION_N}
    if not out['enough']:
        return out
    fit = _fit([p['internal'] for p in pairs], [p['actual'] for p in pairs])
    r = _pearson([p['internal'] for p in pairs], [p['actual'] for p in pairs])
    out['r'] = round(r, 2) if r is not None else None
    out['ci'] = correlation_ci(r, len(pairs)) if r is not None else None
    if not fit:
        out['enough'] = False
        return out
    a, b = fit
    for p in pairs:
        p['expected'] = max(1.0, min(9.0, a + b * p['internal']))
        p['va'] = p['actual'] - p['expected']

    def roll(key):
        groups = defaultdict(list)
        for p in pairs:
            groups[key(p)].append(p)
        rows = []
        for k, ps in groups.items():
            n = len(ps)
            va = mean(p['va'] for p in ps)
            credits = sum(1 for p in ps if p['credit'])
            rows.append({'name': k, 'n': n, 'va': round(va, 2),
                         'expected': round(mean(p['expected'] for p in ps), 2),
                         'actual': round(mean(p['actual'] for p in ps), 2),
                         'credit': rate(credits, n), 'small': n < MIN_GROUP_N,
                         'verdict': ('Above expectation' if va >= .5 and n >= MIN_GROUP_N else
                                     'Below expectation' if va <= -.5 and n >= MIN_GROUP_N else
                                     'As expected' if n >= MIN_GROUP_N else 'Too few to judge')})
        return sorted(rows, key=lambda r: (r['small'], -r['va']))
    out['subjects'] = roll(lambda p: p['subject'])
    out['teachers'] = roll(lambda p: '%s — %s' % (p['teacher'], p['subject']))
    out['line'] = {'a': round(a, 3), 'b': round(b, 4)}
    return out


# --------------------------------------------------------------------------- #
# 2. Mock → real accuracy
# --------------------------------------------------------------------------- #
def mock_accuracy(year, bid=None):
    from models.mock_waec import MockWAECExam, MockWAECResult
    sess, _terms = _session_terms(year)
    waec = waec_by_student(year, bid)
    out = {'exam': None, 'subjects': [], 'n': 0}
    if not sess or not waec:
        return out
    exams = (MockWAECExam.query.filter_by(session_id=sess.id)
             .order_by(MockWAECExam.exam_date.desc(), MockWAECExam.exam_number.desc()).all())
    exam = None
    for ex in exams:
        if MockWAECResult.query.filter_by(mock_exam_id=ex.id).filter(
                MockWAECResult.student_id.in_(list(waec))).first():
            exam = ex
            break
    if exam is None:
        return out
    out['exam'] = exam.display_name
    per = defaultdict(list)
    for r in MockWAECResult.query.filter(MockWAECResult.mock_exam_id == exam.id,
                                         MockWAECResult.student_id.in_(list(waec))).all():
        if r.is_absent or not r.grade:
            continue
        subj = R.canonical_subject(r.subject)
        real = waec.get(r.student_id, {}).get(subj)
        if real:
            per[subj].append((R.points(r.grade), R.points(real), R.is_credit(r.grade), R.is_credit(real)))
    rows = []
    for subj, ps in per.items():
        n = len(ps)
        diff = mean(real - mock for mock, real, _a, _b in ps)
        rows.append({'subject': subj, 'n': n, 'bias': round(diff, 2),
                     'mae': round(mean(abs(real - mock) for mock, real, _a, _b in ps), 2),
                     'exact': rate(sum(1 for m, r_, _a, _b in ps if m == r_), n),
                     'credit_agree': rate(sum(1 for _m, _r, a, b in ps if a == b), n),
                     'small': n < MIN_GROUP_N,
                     'verdict': ('Mock harder than WAEC' if diff >= .75 else
                                 'Mock easier than WAEC' if diff <= -.75 else 'Mock well matched')})
    out['subjects'] = sorted(rows, key=lambda r: (r['small'], -abs(r['bias'])))
    out['n'] = sum(r['n'] for r in rows)
    return out


# --------------------------------------------------------------------------- #
# 3. BECE (JSS3) → WAEC
# --------------------------------------------------------------------------- #
def bece_to_waec(year, bid=None):
    from models.models_school_exams import SchoolExamResult, get_scheme
    waec = waec_by_student(year, bid)
    out = {'n': 0, 'bands': [], 'r': None, 'ci': None}
    if not waec:
        return out
    rows = (SchoolExamResult.query.filter(SchoolExamResult.level == 'jss3',
                                          SchoolExamResult.student_id.in_(list(waec))).all())
    by = defaultdict(lambda: defaultdict(list))        # sid -> year -> [norm points]
    schemes = {}
    for r in rows:
        key = (r.level, r.body)
        if key not in schemes:
            schemes[key] = get_scheme(r.level, r.body)
        sc = schemes[key]
        n = len(sc.bands) or 1
        by[r.student_id][r.exam_year].append(sc.grade_points(r.grade) / n)
    meets = _meets_map(waec)
    pairs = []
    for sid, years in by.items():
        latest = max(years)
        bece = mean(years[latest])
        w = waec[sid]
        pairs.append((bece, mean(R.points(g) for g in w.values()), meets[sid]['meets']))
    out['n'] = len(pairs)
    if not pairs:
        return out
    bands = [('Top third at BECE', lambda b: b >= 2 / 3), ('Middle third', lambda b: 1 / 3 <= b < 2 / 3),
             ('Bottom third', lambda b: b < 1 / 3)]
    for label, test in bands:
        ps = [p for p in pairs if test(p[0])]
        if ps:
            out['bands'].append({'band': label, 'n': len(ps),
                                 'avg_points': round(mean(p[1] for p in ps), 2),
                                 'five_credit': rate(sum(1 for p in ps if p[2]), len(ps))})
    if len(pairs) >= MIN_CORRELATION_N:
        r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
        out['r'] = round(r, 2) if r is not None else None
        out['ci'] = correlation_ci(r, len(pairs)) if r is not None else None
    return out


# --------------------------------------------------------------------------- #
# 4. Near credit
# --------------------------------------------------------------------------- #
def near_credit(year, bid=None, limit=40):
    waec = waec_by_student(year, bid)
    subj = defaultdict(lambda: {'entries': 0, 'd7': 0, 'e8': 0, 'credit': 0})
    for grades in waec.values():
        for s, g in grades.items():
            row = subj[s]
            row['entries'] += 1
            row['d7'] += g == 'D7'
            row['e8'] += g == 'E8'
            row['credit'] += R.is_credit(g)
    subjects = []
    for s, v in subj.items():
        if v['d7']:
            subjects.append({'subject': s, 'entries': v['entries'], 'd7': v['d7'], 'e8': v['e8'],
                             'credit': rate(v['credit'], v['entries']),
                             'credit_if_d7': rate(v['credit'] + v['d7'], v['entries'])})
    subjects.sort(key=lambda r: -r['d7'])
    students = []
    if waec:
        names = {s.id: s for s in Student.query.filter(Student.id.in_(list(waec))).all()}
        for sid, grades in waec.items():
            st = R.five_credit_status(grades)
            if st['near'] and sid in names:
                students.append({'id': sid, 'name': names[sid].full_name, 'code': names[sid].student_id,
                                 'credits': st['credits'],
                                 'd7': sorted(s for s, g in grades.items() if g == 'D7')})
    students.sort(key=lambda r: (-r['credits'], r['name']))
    meets = sum(1 for g in waec.values() if R.five_credit_status(g)['meets'])
    return {'subjects': subjects, 'students': students[:limit], 'students_total': len(students),
            'meets': rate(meets, len(waec)), 'meets_if_one_more': rate(meets + len(students), len(waec))}


# --------------------------------------------------------------------------- #
# 5. Subject combinations / electives
# --------------------------------------------------------------------------- #
def combinations(year, bid=None, min_n=5):
    waec = waec_by_student(year, bid)
    meets = _meets_map(waec)
    combos = defaultdict(list)
    taking = defaultdict(set)
    for sid, grades in waec.items():
        electives = tuple(sorted(s for s in grades if not R.is_core(s)))
        combos[electives].append(sid)
        for s in electives:
            taking[s].add(sid)
    rows = []
    for combo, sids in combos.items():
        if len(sids) >= min_n:
            rows.append({'subjects': list(combo), 'n': len(sids),
                         'five_credit': rate(sum(1 for s in sids if meets[s]['meets']), len(sids))})
    rows.sort(key=lambda r: (-r['five_credit']['pct'], -r['n']))
    all_ids = set(waec)
    electives = []
    for subj, ids in taking.items():
        rest = all_ids - ids
        if len(ids) < MIN_GROUP_N or len(rest) < MIN_GROUP_N:
            continue
        k1 = sum(1 for s in ids if meets[s]['meets'])
        k2 = sum(1 for s in rest if meets[s]['meets'])
        electives.append({'subject': subj, 'takers': rate(k1, len(ids)), 'others': rate(k2, len(rest)),
                          'gap': round(k1 / len(ids) * 100 - k2 / len(rest) * 100, 1),
                          'verdict': gap_verdict(k1, len(ids), k2, len(rest))})
    electives.sort(key=lambda r: -abs(r['gap']))
    return {'combos': rows, 'electives': electives, 'students': len(waec)}


# --------------------------------------------------------------------------- #
# 6. Teachers across years
# --------------------------------------------------------------------------- #
def teachers(years, bid=None):
    """[{'teacher', 'subject', 'years': {year: rate}, 'trend'}] — credit rate of
    each teacher's SSS3 students in their subject, per WAEC year."""
    from models import (ClassSubject, Subject, SchoolClass, StudentEnrollment,
                        ClassArmAssignment)
    sss3 = [c.id for c in SchoolClass.query.all() if re.sub(r'\s+', '', (c.name or '').upper()) == 'SSS3']
    table = defaultdict(dict)
    for y in years:
        sess, terms = _session_terms(y)
        if not terms or not sss3:
            continue
        waec = waec_by_student(y, bid)
        if not waec:
            continue
        tids = [t.id for t in terms]
        arm_of = {}
        for sid, arm_id in (db.session.query(StudentEnrollment.student_id, ClassArmAssignment.arm_id)
                            .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
                            .filter(ClassArmAssignment.class_id.in_(sss3), ClassArmAssignment.term_id.in_(tids),
                                    StudentEnrollment.student_id.in_(list(waec)))
                            .order_by(ClassArmAssignment.term_id).all()):
            arm_of[sid] = arm_id
        owners = {}                     # (subject, arm or None) -> teacher (latest term wins)
        for subj, arm_id, teacher in (db.session.query(Subject.name, ClassSubject.arm_id, ClassSubject.teacher_name)
                                      .join(ClassSubject, ClassSubject.subject_id == Subject.id)
                                      .filter(ClassSubject.class_id.in_(sss3), ClassSubject.term_id.in_(tids))
                                      .order_by(ClassSubject.term_id).all()):
            if (teacher or '').strip():
                owners[(R.canonical_subject(subj), arm_id)] = teacher.strip()
        acc = defaultdict(lambda: [0, 0])
        for sid, grades in waec.items():
            arm = arm_of.get(sid)
            for subj, g in grades.items():
                t = owners.get((subj, arm)) or owners.get((subj, None))
                if t:
                    a = acc[(t, subj)]
                    a[0] += R.is_credit(g)
                    a[1] += 1
        for (t, subj), (k, n) in acc.items():
            table[(t, subj)][y] = rate(k, n)
    out = []
    for (t, subj), by_year in table.items():
        ys = sorted(by_year)
        trend = None
        if len(ys) >= 2:
            trend = round(by_year[ys[-1]]['pct'] - by_year[ys[0]]['pct'], 1)
        out.append({'teacher': t, 'subject': subj, 'years': by_year, 'trend': trend,
                    'latest': by_year[ys[-1]]})
    out.sort(key=lambda r: (r['latest']['small'], -r['latest']['pct']))
    return out


# --------------------------------------------------------------------------- #
# 7. Fairness gaps
# --------------------------------------------------------------------------- #
def fairness(year, bid=None):
    from models import StudentEnrollment, ClassArmAssignment, ClassArm
    from models.models_branch import Branch
    waec = waec_by_student(year, bid)
    meets = _meets_map(waec)
    if not waec:
        return []
    studs = {s.id: s for s in Student.query.filter(Student.id.in_(list(waec))).all()}
    sess, terms = _session_terms(year)
    arm_name = {}
    if terms:
        for sid, name in (db.session.query(StudentEnrollment.student_id, ClassArm.name)
                          .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
                          .join(ClassArm, ClassArm.id == ClassArmAssignment.arm_id)
                          .filter(ClassArmAssignment.term_id.in_([t.id for t in terms]),
                                  StudentEnrollment.student_id.in_(list(waec)))
                          .order_by(ClassArmAssignment.term_id).all()):
            arm_name[sid] = name
    branches = {b.id: b.name for b in Branch.query.all()}
    dims = [('Gender', lambda s: (s.gender or '').strip().title() or None),
            ('Class arm', lambda s: arm_name.get(s.id)),
            ('Boarding', lambda s: (s.boarding_status or '').strip().title() or None)]
    if bid is None and len(branches) > 1:
        dims.append(('Branch', lambda s: branches.get(s.branch_id)))
    out = []
    for dim, key in dims:
        groups = defaultdict(list)
        for sid, st in studs.items():
            k = key(st)
            if k:
                groups[k].append(sid)
        if len(groups) < 2:
            continue
        rows = []
        for g, ids in groups.items():
            k1 = sum(1 for s in ids if meets[s]['meets'])
            rest = [s for s in studs if s not in set(ids) and key(studs[s])]
            k2 = sum(1 for s in rest if meets[s]['meets'])
            rows.append({'group': g, 'rate': rate(k1, len(ids)),
                         'gap': round((k1 / len(ids) - (k2 / len(rest) if rest else 0)) * 100, 1),
                         'verdict': gap_verdict(k1, len(ids), k2, len(rest))})
        rows.sort(key=lambda r: -r['rate']['pct'])
        out.append({'dimension': dim, 'rows': rows})
    return out


# --------------------------------------------------------------------------- #
# 8. Attendance bands
# --------------------------------------------------------------------------- #
BANDS = [('Below 75%', 0, 75), ('75–85%', 75, 85), ('85–95%', 85, 95), ('95% and above', 95, 101)]


def attendance_bands(year, bid=None):
    from models import Attendance, StudentEnrollment, ClassArmAssignment
    waec = waec_by_student(year, bid)
    meets = _meets_map(waec)
    sess, terms = _session_terms(year)
    out = {'bands': [], 'n': 0, 'threshold': None}
    if not waec or not terms:
        return out
    present, marked = defaultdict(int), defaultdict(int)
    for sid, am, pm in (db.session.query(StudentEnrollment.student_id, Attendance.morning_present,
                                         Attendance.afternoon_present)
                        .join(Attendance, Attendance.enrollment_id == StudentEnrollment.id)
                        .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
                        .filter(ClassArmAssignment.term_id.in_([t.id for t in terms]),
                                StudentEnrollment.student_id.in_(list(waec))).all()):
        marked[sid] += 2
        present[sid] += int(bool(am)) + int(bool(pm))
    att = {sid: present[sid] / marked[sid] * 100 for sid in marked if marked[sid]}
    out['n'] = len(att)
    for label, lo, hi in BANDS:
        ids = [s for s, a in att.items() if lo <= a < hi]
        if ids:
            out['bands'].append({'band': label, 'n': len(ids),
                                 'five_credit': rate(sum(1 for s in ids if meets[s]['meets']), len(ids))})
    # Plain-language threshold: compare below-85% vs 85%+ when both are big enough.
    lo_ids = [s for s, a in att.items() if a < 85]
    hi_ids = [s for s, a in att.items() if a >= 85]
    if lo_ids and hi_ids:
        k1 = sum(1 for s in lo_ids if meets[s]['meets'])
        k2 = sum(1 for s in hi_ids if meets[s]['meets'])
        out['threshold'] = {'below': rate(k1, len(lo_ids)), 'above': rate(k2, len(hi_ids)),
                            'gap': round(k2 / len(hi_ids) * 100 - k1 / len(lo_ids) * 100, 1),
                            'verdict': gap_verdict(k2, len(hi_ids), k1, len(lo_ids))}
    return out


# --------------------------------------------------------------------------- #
# 9. Intake cohorts
# --------------------------------------------------------------------------- #
def _cls_norm(name):
    return re.sub(r'[^A-Z0-9]', '', (name or '').upper())


def cohorts(bid=None):
    """One row per JSS1 intake session: started, still here, graduated, left,
    joined later (entered the same year group after JSS1) and — once they have
    sat WAEC — the 5-credit rate."""
    from models import (StudentEnrollment, ClassArmAssignment, SchoolClass, Term, AcademicSession,
                        WAECResult)
    from utils.helpers import session_exam_year
    classes = {c.id: _cls_norm(c.name) for c in SchoolClass.query.all()}
    order = {'JSS1': 1, 'JSS2': 2, 'JSS3': 3, 'SSS1': 4, 'SSS2': 5, 'SSS3': 6}
    sessions = {s.id: s for s in AcademicSession.query.all()}
    q = (db.session.query(StudentEnrollment.student_id, ClassArmAssignment.class_id, Term.session_id, Term.id)
         .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
         .join(Term, Term.id == ClassArmAssignment.term_id))
    if bid is not None:
        q = q.join(Student, Student.id == StudentEnrollment.student_id).filter(Student.branch_id == bid)
    first = {}                                  # sid -> (term_id, level, session_id)
    for sid, cid, sess_id, tid in q.all():
        lvl = order.get(classes.get(cid))
        if not lvl:
            continue
        if sid not in first or tid < first[sid][0]:
            first[sid] = (tid, lvl, sess_id)
    groups = defaultdict(lambda: {'start': [], 'joined': []})
    for sid, (_tid, lvl, sess_id) in first.items():
        sess = sessions.get(sess_id)
        y = session_exam_year(sess) if sess else None
        if not y:
            continue
        intake = y - (lvl - 1)                  # exam year of the JSS1 session for this year group
        groups[intake]['start' if lvl == 1 else 'joined'].append(sid)
    if not groups:
        return []
    all_ids = [s for g in groups.values() for s in g['start'] + g['joined']]
    studs = {s.id: s for s in Student.query.filter(Student.id.in_(all_ids)).all()}
    waec_years = defaultdict(set)
    for sid, y in db.session.query(WAECResult.student_id, WAECResult.exam_year).filter(
            WAECResult.student_id.in_(all_ids)).distinct():
        waec_years[sid].add(y)
    out = []
    for intake, g in sorted(groups.items(), reverse=True):
        if not g['start']:
            continue                    # no JSS1 records for this year group — nothing to follow
        start = [studs[s] for s in g['start'] if s in studs]
        joined = [studs[s] for s in g['joined'] if s in studs]
        waec_year = intake + 5
        members = start + joined
        sat = [s for s in members if waec_year in waec_years.get(s.id, ())]
        meets = 0
        if sat:
            w = waec_by_student(waec_year, bid)
            meets = sum(1 for s in sat if s.id in w and R.five_credit_status(w[s.id])['meets'])
        out.append({
            'intake': '%s/%s' % (intake - 1, intake), 'waec_year': waec_year,
            'started': len(start),
            'still_here': sum(1 for s in start if s.is_active and not s.is_graduated),
            'graduated': sum(1 for s in start if s.is_graduated),
            'left': sum(1 for s in start if not s.is_active),
            'joined': len(joined),
            'sat_waec': len(sat),
            'five_credit': rate(meets, len(sat)) if sat else None,
        })
    return out


# --------------------------------------------------------------------------- #
# 10. Readiness over the session (mock by mock)
# --------------------------------------------------------------------------- #
def readiness_over_time(year, bid=None):
    from models.mock_waec import MockWAECExam, MockWAECResult
    from models.mock_jamb import MockJAMBExam, MockJAMBResult
    from models import JAMBResult
    sess, _terms = _session_terms(year)
    points = []
    if sess:
        for ex in MockWAECExam.query.filter_by(session_id=sess.id).order_by(MockWAECExam.exam_date).all():
            per = defaultdict(dict)
            q = MockWAECResult.query.filter_by(mock_exam_id=ex.id)
            for r in q.all():
                if r.is_absent or not r.grade:
                    continue
                if bid is not None and r.student and r.student.branch_id != bid:
                    continue
                per[r.student_id][R.canonical_subject(r.subject)] = r.grade
            if per:
                k = sum(1 for g in per.values() if R.five_credit_status(g)['meets'])
                points.append({'label': ex.display_name, 'date': ex.exam_date, 'kind': 'Mock WAEC',
                               'measure': '5 credits incl. Eng & Maths', 'rate': rate(k, len(per))})
        for ex in MockJAMBExam.query.filter_by(session_id=sess.id).order_by(MockJAMBExam.exam_date).all():
            rs = [r for r in MockJAMBResult.query.filter_by(mock_exam_id=ex.id).all()
                  if bid is None or (r.student and r.student.branch_id == bid)]
            if rs:
                points.append({'label': ex.display_name, 'date': ex.exam_date, 'kind': 'Mock JAMB',
                               'measure': 'JAMB 200+', 'rate': rate(sum(1 for r in rs if (r.total_score or 0) >= 200), len(rs))})
    waec = waec_by_student(year, bid)
    if waec:
        k = sum(1 for g in waec.values() if R.five_credit_status(g)['meets'])
        points.append({'label': 'WASSCE %s' % year, 'date': None, 'kind': 'WAEC',
                       'measure': '5 credits incl. Eng & Maths', 'rate': rate(k, len(waec))})
    q = db.session.query(JAMBResult.total_score).filter(JAMBResult.exam_year == year)
    if bid is not None:
        q = q.join(Student, Student.id == JAMBResult.student_id).filter(Student.branch_id == bid)
    js = [t for (t,) in q.all() if t is not None]
    if js:
        points.append({'label': 'UTME %s' % year, 'date': None, 'kind': 'JAMB', 'measure': 'JAMB 200+',
                       'rate': rate(sum(1 for t in js if t >= 200), len(js))})
    return points


# --------------------------------------------------------------------------- #
# 11. Weak topics per subject (mock JAMB item answers)
# --------------------------------------------------------------------------- #
def weak_topics(year, bid=None, per_subject=3, min_answers=10):
    from models.mock_jamb import MockJAMBExam, MockJAMBAttempt
    from utils.mock_student_mastery import _answer_rows
    sess, _terms = _session_terms(year)
    if not sess:
        return []
    exam_ids = [e.id for e in MockJAMBExam.query.filter_by(session_id=sess.id).all()]
    if not exam_ids:
        return []
    q = MockJAMBAttempt.query.filter(MockJAMBAttempt.status == 'Submitted',
                                     MockJAMBAttempt.mock_exam_id.in_(exam_ids))
    if bid is not None:
        q = q.join(Student, Student.id == MockJAMBAttempt.student_id).filter(Student.branch_id == bid)
    rows = _answer_rows([a.id for a in q.all()])
    agg = defaultdict(lambda: [0, 0])
    for subj, topic, _sub, ok, _aid in rows:
        if not topic:
            continue
        a = agg[(R.canonical_subject(subj or ''), topic)]
        a[0] += 1 if ok else 0
        a[1] += 1
    by_subject = defaultdict(list)
    for (subj, topic), (c, t) in agg.items():
        if t >= min_answers:
            by_subject[subj].append({'topic': topic, 'answers': t, 'correct': rate(c, t)})
    out = []
    for subj, ts in sorted(by_subject.items()):
        ts.sort(key=lambda x: x['correct']['pct'])
        out.append({'subject': subj, 'topics': ts[:per_subject]})
    return out


# --------------------------------------------------------------------------- #
# Everything for one page load
# --------------------------------------------------------------------------- #
SECTIONS = ['value_added', 'near_credit', 'mock_accuracy', 'bece_to_waec', 'combinations',
            'teachers', 'fairness', 'attendance', 'cohorts', 'readiness', 'weak_topics']


def build(year, bid=None, years=None):
    """All sections for ``year`` (each computed defensively: a failure in one
    section is reported, never breaks the page)."""
    import logging
    out, errors = {}, {}
    calls = {
        'value_added': lambda: value_added(year, bid),
        'near_credit': lambda: near_credit(year, bid),
        'mock_accuracy': lambda: mock_accuracy(year, bid),
        'bece_to_waec': lambda: bece_to_waec(year, bid),
        'combinations': lambda: combinations(year, bid),
        'teachers': lambda: teachers(sorted(years or [year])[-4:], bid),
        'fairness': lambda: fairness(year, bid),
        'attendance': lambda: attendance_bands(year, bid),
        'cohorts': lambda: cohorts(bid),
        'readiness': lambda: readiness_over_time(year, bid),
        'weak_topics': lambda: weak_topics(year, bid),
    }
    for k, fn in calls.items():
        try:
            out[k] = fn()
        except Exception as e:  # pragma: no cover — defensive
            db.session.rollback()
            logging.getLogger(__name__).exception('insights section %s failed', k)
            out[k] = None
            errors[k] = str(e)
    out['errors'] = errors
    return out
