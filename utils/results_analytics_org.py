"""Institution-wide internal-results analytics.

Where ``results_analytics`` answers *"how did this one class arm do?"*, this
module rolls the same entered scores up to any level of the school and slices
them every way a school owner / principal actually makes decisions:

* **Scope** — a single arm, a whole class (all arms), a section (nursery /
  primary / junior / senior secondary) or the **entire school**.
* **Leagues** — ranked comparisons of the scope's child units (sections within
  the school, classes within a section, arms within a class), of every
  **subject**, and of every **teacher**.
* **Decisions** — derived KPIs and plain-English recommendations: which
  students need intervention, which subjects are dragging the school down,
  which teachers to commend, which need training/support, and which to flag
  for a performance/retention review — plus honour-roll and gender-gap reads.

Everything is computed from scores already entered (no new data) with a single
bulk score fetch (no N+1). Results are cached in ``AnalyticsCache`` keyed by
term + scope + the caller's accessible-class set, so a teacher and an admin get
correctly-scoped (and correctly-cached) numbers.
"""
from __future__ import annotations

import hashlib

# Section machine-key -> friendly label, ordered nursery → senior.
SECTION_LABELS = [
    ('nursery', 'Nursery'), ('primary', 'Primary School'),
    ('junior', 'Junior Secondary'), ('senior', 'Senior Secondary'),
]
SECTION_ORDER = {k: i for i, (k, _l) in enumerate(SECTION_LABELS)}
DISTINCTION = 75          # average at/above which a student earns a distinction
MIN_TEACHER_ENTRIES = 10  # below this a teacher verdict is "insufficient data"


def _section_label(key):
    key = (key or '').lower()
    for k, lbl in SECTION_LABELS:
        if k == key:
            return lbl
    return (key or 'Unspecified').title()


def _cache_key(term_id, scope, scope_id, allowed_ids):
    if allowed_ids is None:
        tag = 'all'
    else:
        tag = hashlib.md5((','.join(map(str, sorted(allowed_ids)))).encode()).hexdigest()[:10]
    return f'results_org:{term_id}:{scope}:{scope_id or 0}:{tag}'


def bust_all():
    """Drop every cached org-analytics row (called after any score change)."""
    from models import db, AnalyticsCache
    try:
        AnalyticsCache.query.filter(
            AnalyticsCache.cache_key.like('results_org:%')).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def org_analytics(term_id, scope='school', scope_id=None, allowed_ids=None,
                  *, use_cache=True, ttl=600):
    """Analytics payload for a scope in a term. ``allowed_ids`` (or None for
    everything) limits which class-arm assignments are counted, so teachers see
    only their own classes rolled up. Cached for ``ttl`` seconds."""
    from models import AnalyticsCache
    scope = scope if scope in ('school', 'section', 'class', 'arm') else 'school'
    key = _cache_key(term_id, scope, scope_id, allowed_ids)
    if use_cache:
        hit = AnalyticsCache.get(key)
        if hit is not None:
            hit['cached'] = True
            return hit
    data = _compute(term_id, scope, scope_id, allowed_ids)
    try:
        AnalyticsCache.set(key, data, ttl_seconds=ttl)
    except Exception:
        pass
    data['cached'] = False
    return data


def _grade_bands():
    from models import GradeScale
    bands = GradeScale.query.order_by(GradeScale.order, GradeScale.min_score.desc()).all()
    return [(b.grade, b.min_score, b.max_score) for b in bands]


def _grade_for(total, bands):
    for grade, lo, hi in bands:
        if lo <= total <= hi:
            return grade
    return 'F'


def _mean(xs):
    return round(sum(xs) / len(xs), 2) if xs else 0


def _scope_assignments(term_id, scope, scope_id, allowed_ids):
    """The ClassArmAssignments (with .school_class eager-loaded) that fall inside
    the requested scope and the caller's access."""
    from sqlalchemy.orm import joinedload
    from models import ClassArmAssignment, SchoolClass
    q = (ClassArmAssignment.query
         .options(joinedload(ClassArmAssignment.school_class),
                  joinedload(ClassArmAssignment.arm))
         .filter_by(term_id=term_id))
    rows = q.all()
    if allowed_ids is not None:
        allowed = set(allowed_ids)
        rows = [a for a in rows if a.id in allowed]
    if scope == 'arm' and scope_id:
        rows = [a for a in rows if a.id == int(scope_id)]
    elif scope == 'class' and scope_id:
        rows = [a for a in rows if a.class_id == int(scope_id)]
    elif scope == 'section' and scope_id:
        want = str(scope_id).lower()
        rows = [a for a in rows if a.school_class and (a.school_class.section or '').lower() == want]
    return rows


def _compute(term_id, scope, scope_id, allowed_ids):
    from sqlalchemy.orm import joinedload
    from models import (ClassSubject, Subject, Student, StudentEnrollment,
                        StudentScore, SchoolSettings)

    assignments = _scope_assignments(term_id, scope, scope_id, allowed_ids)
    if not assignments:
        return _empty(term_id, scope, scope_id, allowed_ids)
    asg_by_id = {a.id: a for a in assignments}
    class_ids = {a.class_id for a in assignments}
    pass_mark = SchoolSettings.get('pass_mark', 50)
    bands = _grade_bands()

    # Subjects for every class in scope (arm_id NULL = applies to all arms).
    all_cs = (ClassSubject.query
              .options(joinedload(ClassSubject.subject))
              .filter(ClassSubject.term_id == term_id, ClassSubject.is_active == True,  # noqa: E712
                      ClassSubject.class_id.in_(class_ids)).all())
    cs_by_class = {}
    for cs in all_cs:
        cs_by_class.setdefault(cs.class_id, []).append(cs)

    def applicable(a):
        return [cs for cs in cs_by_class.get(a.class_id, [])
                if cs.arm_id is None or cs.arm_id == a.arm_id]

    enrollments = (StudentEnrollment.query
                   .options(joinedload(StudentEnrollment.student))
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(list(asg_by_id)),
                           StudentEnrollment.is_active == True).all())  # noqa: E712
    if not enrollments:
        return _empty(term_id, scope, scope_id, allowed_ids)

    cs_ids = [cs.id for cs in all_cs]
    sids = [e.student_id for e in enrollments]
    present = {}                       # (sid, cs_id) -> summed subject total
    if cs_ids and sids:
        for s in StudentScore.query.filter(
                StudentScore.student_id.in_(sids),
                StudentScore.class_subject_id.in_(cs_ids)).all():
            if s.score is None:
                continue
            k = (s.student_id, s.class_subject_id)
            present[k] = present.get(k, 0) + s.score

    # Branch names for the "by branch" league (whole-group owners comparing
    # campuses). Only meaningful when more than one branch is in scope.
    branch_name = {}
    branch_ids = {a.branch_id for a in assignments if a.branch_id}
    if branch_ids:
        from models import Branch
        for b in Branch.query.filter(Branch.id.in_(list(branch_ids))).all():
            branch_name[b.id] = b.name

    # Term attendance % per enrolment (present sessions / opened sessions), one
    # bulk query — the basis for the attendance-vs-results correlation.
    att_pct_by_enr = _attendance_pct_map(term_id, [e.id for e in enrollments])

    # ---- accumulators -----------------------------------------------------
    grade_dist = {g: 0 for g, _l, _h in bands} or {'F': 0}
    subj_acc = {}      # subject_id -> {name, totals[]}
    teacher_acc = {}   # teacher_name -> {...}
    unit_acc = {}      # unit_key -> {label, averages[], pass, students, scope, scope_id, order}
    branch_acc = {}    # branch_id -> {label, averages[], pass, students}
    att_pairs = []     # (attendance_pct, average) for the correlation
    student_recs = []
    cells_possible = cells_entered = 0
    band_defs = [('0–39', 0, 39.999), ('40–49', 40, 49.999), ('50–59', 50, 59.999),
                 ('60–69', 60, 69.999), ('70–79', 70, 79.999), ('80–100', 80, 1e9)]

    def unit_of(a, student):
        """(key, label, order, child_scope, child_id) for the league one level
        below the current scope."""
        sc = a.school_class
        if scope == 'school':
            sect = (sc.section if sc else '') or ''
            return (f'sec:{sect.lower()}', _section_label(sect),
                    SECTION_ORDER.get(sect.lower(), 99), 'section', sect.lower())
        if scope == 'section':
            return (f'cls:{a.class_id}', sc.name if sc else f'Class {a.class_id}',
                    (sc.level if sc else 99), 'class', a.class_id)
        if scope == 'class':
            return (f'arm:{a.id}', a.display_name, a.id, 'arm', a.id)
        return (None, None, None, None, None)   # arm scope: compared by subject

    for e in enrollments:
        a = asg_by_id[e.class_arm_assignment_id]
        st = e.student
        applic = applicable(a)
        assessed = []
        failed = 0
        for cs in applic:
            teacher = (cs.teacher_name or '').strip() or 'Unassigned'
            T = teacher_acc.setdefault(teacher, {
                'name': teacher, 'totals': [], 'entries': 0, 'possible': 0,
                'fail': 0, 'subjects': set(), 'classes': set()})
            T['possible'] += 1
            T['subjects'].add(cs.subject.name if cs.subject else '')
            T['classes'].add(a.display_name)
            cells_possible += 1
            k = (e.student_id, cs.id)
            if k in present:
                total = round(present[k], 2)
                assessed.append(total)
                cells_entered += 1
                g = _grade_for(total, bands)
                grade_dist[g] = grade_dist.get(g, 0) + 1
                S = subj_acc.setdefault(cs.subject_id, {
                    'name': cs.subject.name if cs.subject else f'Subject {cs.subject_id}',
                    'totals': []})
                S['totals'].append(total)
                T['totals'].append(total)
                T['entries'] += 1
                if total < pass_mark:
                    T['fail'] += 1
                    failed += 1
        if not assessed:
            continue
        avg = _mean(assessed)
        student_recs.append({
            'id': e.student_id, 'name': st.full_name if st else str(e.student_id),
            'class': a.display_name, 'average': avg, 'assessed': len(assessed),
            'failed': failed, 'gender': (getattr(st, 'gender', '') or '').lower(),
        })
        key, label, order, cscope, cid = unit_of(a, st)
        if key is not None:
            U = unit_acc.setdefault(key, {
                'label': label, 'averages': [], 'pass': 0, 'students': 0,
                'scope': cscope, 'scope_id': cid, 'order': order})
            U['averages'].append(avg)
            U['students'] += 1
            if avg >= pass_mark:
                U['pass'] += 1
        if a.branch_id:
            B = branch_acc.setdefault(a.branch_id, {
                'label': branch_name.get(a.branch_id, f'Branch {a.branch_id}'),
                'averages': [], 'pass': 0, 'students': 0})
            B['averages'].append(avg)
            B['students'] += 1
            if avg >= pass_mark:
                B['pass'] += 1
        apct = att_pct_by_enr.get(e.id)
        if apct is not None:
            att_pairs.append((apct, avg))

    if not student_recs:
        return _empty(term_id, scope, scope_id, allowed_ids)

    averages = [s['average'] for s in student_recs]
    class_avg = _mean(averages)
    passed = sum(1 for a in averages if a >= pass_mark)
    distinctions = sum(1 for a in averages if a >= DISTINCTION)
    ranked = sorted(student_recs, key=lambda s: -s['average'])

    # ---- subject league (hardest first) -----------------------------------
    subjects = []
    for sid_, info in subj_acc.items():
        tot = info['totals']
        sg = {g: 0 for g, _l, _h in bands}
        for t in tot:
            sg[_grade_for(t, bands)] = sg.get(_grade_for(t, bands), 0) + 1
        subjects.append({
            'id': sid_, 'name': info['name'], 'average': _mean(tot),
            'pass_rate': round(100 * sum(1 for t in tot if t >= pass_mark) / len(tot), 1) if tot else 0,
            'assessed': len(tot), 'highest': round(max(tot), 1) if tot else 0,
            'lowest': round(min(tot), 1) if tot else 0,
            'grades': [{'grade': g, 'count': sg.get(g, 0)} for g, _l, _h in bands],
        })
    subjects.sort(key=lambda r: (r['assessed'] == 0, r['average']))

    # ---- teacher league ---------------------------------------------------
    teachers = []
    for name, T in teacher_acc.items():
        if name == 'Unassigned' and not T['entries']:
            continue
        ent = T['entries']
        avg = _mean(T['totals'])
        pr = round(100 * (ent - T['fail']) / ent, 1) if ent else 0
        comp = round(100 * ent / T['possible'], 1) if T['possible'] else 0
        flag, verdict = _teacher_verdict(avg, pr, ent, comp)
        teachers.append({
            'name': name, 'average': avg, 'pass_rate': pr, 'entries': ent,
            'completion': comp, 'subjects': sorted(x for x in T['subjects'] if x),
            'subject_count': len([x for x in T['subjects'] if x]),
            'class_count': len(T['classes']), 'flag': flag, 'verdict': verdict,
        })
    teachers.sort(key=lambda t: -t['average'])

    # ---- unit league (children of the scope) ------------------------------
    units = []
    for U in unit_acc.values():
        uavg = _mean(U['averages'])
        units.append({
            'label': U['label'], 'students': U['students'], 'average': uavg,
            'pass_rate': round(100 * U['pass'] / U['students'], 1) if U['students'] else 0,
            'scope': U['scope'], 'scope_id': U['scope_id'], '_order': U['order'],
        })
    units.sort(key=lambda u: -u['average'])

    # ---- branch league (only when more than one campus is in scope) -------
    branches = []
    if len(branch_acc) > 1:
        for B in branch_acc.values():
            branches.append({
                'label': B['label'], 'students': B['students'], 'average': _mean(B['averages']),
                'pass_rate': round(100 * B['pass'] / B['students'], 1) if B['students'] else 0,
            })
        branches.sort(key=lambda b: -b['average'])

    # ---- attendance vs results -------------------------------------------
    attendance = _attendance_analysis(att_pairs, pass_mark)

    # ---- histograms & splits ----------------------------------------------
    score_bands = [{'band': lbl, 'count': sum(1 for a in averages if lo <= a <= hi)}
                   for lbl, lo, hi in band_defs]
    gender = []
    for gkey, glabel in (('male', 'Boys'), ('female', 'Girls')):
        vals = [s['average'] for s in student_recs if s['gender'] == gkey]
        if vals:
            gp = sum(1 for a in vals if a >= pass_mark)
            gender.append({'group': glabel, 'count': len(vals), 'average': _mean(vals),
                           'pass_rate': round(100 * gp / len(vals), 1)})

    intervention = sorted(
        [s for s in student_recs if s['average'] < pass_mark or s['failed'] >= 2],
        key=lambda s: s['average'])[:40]
    honour = [{'name': s['name'], 'class': s['class'], 'average': s['average']}
              for s in ranked if s['average'] >= DISTINCTION][:40]

    summary = {
        'units': len(assignments), 'students': len(enrollments),
        'assessed': len(student_recs), 'class_average': class_avg,
        'highest': round(max(averages), 2), 'lowest': round(min(averages), 2),
        'pass_rate': round(100 * passed / len(averages), 1),
        'fail_rate': round(100 * (len(averages) - passed) / len(averages), 1),
        'distinction_rate': round(100 * distinctions / len(averages), 1),
        'distinctions': distinctions,
        'completion': round(100 * cells_entered / cells_possible, 1) if cells_possible else 0,
        'pass_mark': pass_mark, 'distinction_mark': DISTINCTION,
        'top_student': ranked[0]['name'] if ranked else '',
        'subjects_count': len(subjects), 'teachers_count': len(teachers),
    }

    payload = {
        'scope': scope, 'scope_id': scope_id,
        'scope_label': _scope_label(term_id, scope, scope_id, assignments),
        'summary': summary,
        'grade_distribution': [{'grade': g, 'count': grade_dist.get(g, 0)} for g, _l, _h in bands]
                              or [{'grade': 'F', 'count': grade_dist.get('F', 0)}],
        'score_bands': score_bands, 'gender': gender,
        'subjects': subjects, 'teachers': teachers, 'units': units,
        'unit_kind': {'school': 'Section', 'section': 'Class', 'class': 'Arm',
                      'arm': 'Subject'}.get(scope, 'Unit'),
        'branches': branches, 'attendance': attendance,
        'top_students': [{'name': s['name'], 'class': s['class'], 'average': s['average']}
                         for s in ranked[:10]],
        'honour_roll': honour, 'intervention': intervention,
        'recommendations': _recommendations(summary, units, subjects, teachers,
                                             gender, intervention, honour, scope,
                                             branches, attendance),
        'trends': _org_trends(term_id, scope, scope_id, allowed_ids, assignments),
        'selectors': _selectors(term_id, allowed_ids),
    }
    return payload


def _student_averages(assignment_ids, term_id, pass_mark):
    """Slim per-student averages (mean of a student's assessed subject totals)
    for a set of assignments in a term — the shared basis for roll-ups and the
    term-on-term trend. Returns the list of student averages (0–100)."""
    from sqlalchemy.orm import joinedload
    from models import ClassSubject, StudentEnrollment, StudentScore
    if not assignment_ids:
        return []
    from models import ClassArmAssignment
    asgs = (ClassArmAssignment.query
            .filter(ClassArmAssignment.id.in_(list(assignment_ids))).all())
    asg_by_id = {a.id: a for a in asgs}
    class_ids = {a.class_id for a in asgs}
    if not class_ids:
        return []
    all_cs = (ClassSubject.query
              .filter(ClassSubject.term_id == term_id, ClassSubject.is_active == True,  # noqa: E712
                      ClassSubject.class_id.in_(class_ids)).all())
    cs_by_class = {}
    for cs in all_cs:
        cs_by_class.setdefault(cs.class_id, []).append(cs)
    enrollments = (StudentEnrollment.query
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(list(asg_by_id)),
                           StudentEnrollment.is_active == True).all())  # noqa: E712
    cs_ids = [cs.id for cs in all_cs]
    sids = [e.student_id for e in enrollments]
    present = {}
    if cs_ids and sids:
        for s in StudentScore.query.filter(
                StudentScore.student_id.in_(sids),
                StudentScore.class_subject_id.in_(cs_ids)).all():
            if s.score is None:
                continue
            k = (s.student_id, s.class_subject_id)
            present[k] = present.get(k, 0) + s.score
    out = []
    for e in enrollments:
        a = asg_by_id[e.class_arm_assignment_id]
        applic = [cs for cs in cs_by_class.get(a.class_id, [])
                  if cs.arm_id is None or cs.arm_id == a.arm_id]
        assessed = [round(present[(e.student_id, cs.id)], 2)
                    for cs in applic if (e.student_id, cs.id) in present]
        if assessed:
            out.append(round(sum(assessed) / len(assessed), 2))
    return out


def _org_trends(term_id, scope, scope_id, allowed_ids, ref_assignments):
    """Scope average & pass rate across every term of the session — the
    institution-level term-on-term trend. ``ref_assignments`` are the current
    scope's assignments (used to translate an arm scope to other terms)."""
    from models import db, Term, ClassArmAssignment, SchoolSettings
    term = db.session.get(Term, term_id)
    if not term or not term.session_id:
        return {'term_names': [], 'averages': [], 'pass_rates': []}
    pass_mark = SchoolSettings.get('pass_mark', 50)
    terms = Term.query.filter_by(session_id=term.session_id).order_by(Term.term_number).all()
    # For an arm scope, follow the same class+arm across terms (assignment ids
    # are term-specific); other scopes filter by stable class_id / section.
    arm_key = None
    if scope == 'arm' and ref_assignments:
        a0 = ref_assignments[0]
        arm_key = (a0.class_id, a0.arm_id)
    names, averages, pass_rates = [], [], []
    for t in terms:
        names.append(t.name)
        if arm_key:
            rows = ClassArmAssignment.query.filter_by(
                term_id=t.id, class_id=arm_key[0], arm_id=arm_key[1]).all()
            if allowed_ids is not None:
                rows = [r for r in rows if r.id in allowed_ids]
            ids = [r.id for r in rows]
        else:
            ids = [a.id for a in _scope_assignments(t.id, scope, scope_id, allowed_ids)]
        vals = _student_averages(ids, t.id, pass_mark) if ids else []
        if vals:
            averages.append(round(sum(vals) / len(vals), 2))
            pass_rates.append(round(100 * sum(1 for v in vals if v >= pass_mark) / len(vals), 1))
        else:
            averages.append(None)
            pass_rates.append(None)
    return {'term_names': names, 'averages': averages, 'pass_rates': pass_rates}


def _attendance_pct_map(term_id, enrollment_ids):
    """{enrollment_id: term attendance %} in one bulk query. % = present
    sessions / opened sessions (morning + afternoon). Empty when no records."""
    from models import Week, Attendance
    if not enrollment_ids:
        return {}
    week_ids = [w.id for w in Week.query.filter_by(term_id=term_id).all()]
    if not week_ids:
        return {}
    agg = {}       # enr_id -> [present_sessions, opened_days]
    for a in Attendance.query.filter(
            Attendance.enrollment_id.in_(list(enrollment_ids)),
            Attendance.week_id.in_(week_ids)).all():
        cell = agg.setdefault(a.enrollment_id, [0, 0])
        cell[0] += (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
        cell[1] += 1
    return {eid: round(pres / (days * 2) * 100, 1)
            for eid, (pres, days) in agg.items() if days}


ATT_BANDS = [('<50%', 0, 49.999), ('50–69%', 50, 69.999), ('70–84%', 70, 84.999),
             ('85–94%', 85, 94.999), ('95–100%', 95, 1e9)]


def _pearson(pairs):
    """Pearson correlation of (x, y) pairs, rounded; None when undefined."""
    n = len(pairs)
    if n < 3:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return round(cov / (vx ** 0.5 * vy ** 0.5), 2)


def _attendance_analysis(att_pairs, pass_mark):
    """Average score per attendance band + the attendance↔score correlation."""
    if not att_pairs:
        return {'bands': [], 'correlation': None, 'coverage': 0}
    bands = []
    for lbl, lo, hi in ATT_BANDS:
        vals = [avg for apct, avg in att_pairs if lo <= apct <= hi]
        if vals:
            bands.append({'band': lbl, 'count': len(vals), 'average': _mean(vals)})
    return {'bands': bands, 'correlation': _pearson(att_pairs), 'coverage': len(att_pairs)}


def _teacher_verdict(avg, pass_rate, entries, completion):
    """Map a teacher's aggregate to an actionable HR verdict."""
    if entries < MIN_TEACHER_ENTRIES:
        return 'insufficient', 'Insufficient data to assess'
    if completion < 60:
        return 'compliance', 'Score entry incomplete — compliance follow-up'
    if avg >= 65 and pass_rate >= 75:
        return 'strong', 'Strong performer — commend & retain'
    if avg >= 55 and pass_rate >= 60:
        return 'good', 'Meets expectations'
    if avg < 45 or pass_rate < 45:
        return 'review', 'Underperforming — training & performance review'
    return 'watch', 'Below target — targeted support / monitoring'


def _recommendations(summary, units, subjects, teachers, gender, intervention, honour,
                     scope, branches=None, attendance=None):
    """Plain-English, decision-oriented reads an owner/principal can act on."""
    recs = []

    def add(tone, title, text):
        recs.append({'tone': tone, 'title': title, 'text': text})

    pm = summary['pass_mark']
    ca = summary['class_average']
    pr = summary['pass_rate']
    # Overall health verdict.
    if pr >= 80 and ca >= 60:
        add('positive', 'Healthy academic standing',
            f"Pass rate is {pr}% with a {ca} average — above a defensible benchmark. "
            f"This is a strong story for parents, boards and prospective funders.")
    elif pr >= 55:
        add('watch', 'Mixed results — room to grow',
            f"A {pr}% pass rate and {ca} average are workable but leave value on the table. "
            f"Target the weakest units and subjects below to lift the whole cohort.")
    else:
        add('negative', 'Academic performance needs urgent attention',
            f"Only {pr}% of assessed students are at or above the {pm} pass mark "
            f"(average {ca}). Treat this as a turnaround priority this term.")

    if summary['completion'] < 85:
        add('watch', 'Data completeness limits confidence',
            f"Only {summary['completion']}% of expected scores are entered. "
            f"Chase the outstanding entries before circulating these numbers externally.")

    # Best / worst unit.
    if len(units) >= 2:
        best, worst = units[0], units[-1]
        gap = round(best['average'] - worst['average'], 1)
        add('insight', 'Widest performance gap',
            f"{best['label']} leads at {best['average']} while {worst['label']} trails at "
            f"{worst['average']} — a {gap}-point gap. Move proven practice from "
            f"{best['label']} into {worst['label']}, and review staffing there.")

    # Subjects.
    weak = [s for s in subjects if s['assessed'] and s['average'] < pm]
    if weak:
        names = ', '.join(s['name'] for s in weak[:4])
        add('negative', 'Subjects dragging results down',
            f"{len(weak)} subject(s) sit below the pass mark — hardest: {names}. "
            f"Prioritise these for scheme-of-work review, remedial classes and CPD.")
    strong = [s for s in subjects if s['average'] >= DISTINCTION]
    if strong:
        add('positive', 'Flagship subjects',
            f"{', '.join(s['name'] for s in strong[:4])} are performing at distinction level — "
            f"showcase them in marketing and study what makes them work.")

    # Teachers — commend / train / review.
    strong_t = [t for t in teachers if t['flag'] == 'strong']
    if strong_t:
        add('positive', 'Teachers to commend & retain',
            f"{', '.join(t['name'] for t in strong_t[:5])} are driving strong outcomes. "
            f"Recognise them, protect them from attrition and use them to mentor peers.")
    train_t = [t for t in teachers if t['flag'] in ('watch', 'review')]
    if train_t:
        add('watch', 'Teachers needing training / support',
            f"{', '.join(t['name'] for t in train_t[:5])} are below target. "
            f"Pair with a mentor, set a measurable improvement plan and re-review next term.")
    review_t = [t for t in teachers if t['flag'] == 'review' and t['class_count'] >= 1]
    if review_t:
        add('negative', 'Flag for performance / retention review',
            f"{', '.join(t['name'] for t in review_t[:5])} show sustained underperformance. "
            f"If a documented improvement plan does not move the numbers, escalate to a "
            f"formal retention decision. (This is a data signal, not a verdict — verify context.)")
    comp_t = [t for t in teachers if t['flag'] == 'compliance']
    if comp_t:
        add('watch', 'Score-entry compliance',
            f"{', '.join(t['name'] for t in comp_t[:5])} have not entered all their scores. "
            f"Results cannot be judged until entry is complete.")

    # Students.
    if intervention:
        add('watch', 'Students needing intervention',
            f"{len(intervention)} student(s) are below the pass mark or failing 2+ subjects. "
            f"Enrol them in remedial support and notify parents early.")
    if honour:
        add('positive', 'Honour roll',
            f"{len(honour)} student(s) earned a distinction (avg ≥ {DISTINCTION}). "
            f"Publicly recognise them — it reinforces culture and aids retention/referrals.")

    # Gender gap.
    if len(gender) == 2:
        g0, g1 = gender
        gap = round(abs(g0['average'] - g1['average']), 1)
        if gap >= 5:
            lead, lag = (g0, g1) if g0['average'] >= g1['average'] else (g1, g0)
            add('insight', 'Gender performance gap',
                f"{lead['group']} outperform {lag['group']} by {gap} points on average. "
                f"Investigate the drivers and target support at the trailing group.")

    # Branch (campus) comparison.
    if branches and len(branches) > 1:
        best, worst = branches[0], branches[-1]
        gap = round(best['average'] - worst['average'], 1)
        add('insight', 'Campus comparison',
            f"{best['label']} leads the group at {best['average']} while {worst['label']} "
            f"trails at {worst['average']} ({gap}-point gap). Transfer what works at "
            f"{best['label']} and audit leadership/staffing at {worst['label']}.")

    # Attendance ↔ results.
    if attendance and attendance.get('correlation') is not None:
        r = attendance['correlation']
        if r >= 0.3:
            add('insight', 'Attendance drives results',
                f"Attendance and scores are positively correlated (r={r}). Tightening "
                f"attendance follow-up is a concrete lever on academic outcomes — "
                f"prioritise chronically-absent students.")
        elif r <= -0.1:
            add('watch', 'Attendance–results link is weak',
                f"Attendance and scores barely track together (r={r}); poor results here "
                f"are being driven by teaching/curriculum factors more than absence.")
    return recs


def _scope_label(term_id, scope, scope_id, assignments):
    from models import db, SchoolClass
    if scope == 'school':
        return 'Whole School'
    if scope == 'section':
        return _section_label(scope_id)
    if scope == 'class' and scope_id:
        sc = db.session.get(SchoolClass, int(scope_id))
        return sc.name if sc else 'Class'
    if scope == 'arm' and assignments:
        return assignments[0].display_name
    return 'Whole School'


def _selectors(term_id, allowed_ids):
    """Sections / classes / arms available in this term for the scope picker,
    limited to the caller's access."""
    asgs = _scope_assignments(term_id, 'school', None, allowed_ids)
    sect_keys, classes, arms = {}, {}, []
    for a in asgs:
        sc = a.school_class
        sect = (sc.section if sc else '') or ''
        if sect:
            sect_keys[sect.lower()] = _section_label(sect)
        if sc and a.class_id not in classes:
            classes[a.class_id] = {'id': a.class_id, 'name': sc.name,
                                   'section': (sc.section or '').lower(),
                                   'level': sc.level or 99}
        arms.append({'id': a.id, 'label': a.display_name, 'class_id': a.class_id,
                     'section': (sc.section if sc else '') or ''})
    sections = [{'key': k, 'label': lbl} for k, lbl in
                sorted(sect_keys.items(), key=lambda kv: SECTION_ORDER.get(kv[0], 99))]
    class_list = sorted(classes.values(), key=lambda c: (c['level'], c['name']))
    arms.sort(key=lambda x: x['label'])
    return {'sections': sections, 'classes': class_list, 'arms': arms}


def resolve_teacher_staff(name):
    """Best-effort match of a free-text ``teacher_name`` to an active StaffMember
    id (so an admin can message that specific teacher). Titles are stripped and
    both name orders are tried. Returns the id or None when there's no clear hit."""
    n = (name or '').strip().lower()
    if not n:
        return None
    for title in ('prof. ', 'prof ', 'dr. ', 'dr ', 'mr. ', 'mr ', 'mrs. ', 'mrs ',
                  'miss ', 'ms. ', 'ms '):
        if n.startswith(title):
            n = n[len(title):].strip()
            break
    from models import StaffMember
    for st in StaffMember.query.filter_by(is_active=True).all():
        fn = (st.first_name or '').strip().lower()
        sn = (st.surname or '').strip().lower()
        if not (fn or sn):
            continue
        if n in (f'{fn} {sn}'.strip(), f'{sn} {fn}'.strip()):
            return st.id
        if fn and sn and fn in n and sn in n:
            return st.id
    return None


def teacher_scorecard(term_id, teacher_name, allowed_ids=None):
    """Per-class, per-subject breakdown for one teacher in a term — the drill-down
    behind the teacher-effectiveness league. Returns overall KPIs, a row per
    class-subject taught, subject/class roll-ups, an HR verdict and a term trend."""
    from sqlalchemy.orm import joinedload
    from models import (db, ClassSubject, StudentEnrollment, StudentScore,
                        SchoolSettings, Term)
    name = (teacher_name or '').strip()
    if not name or not term_id:
        return None
    pass_mark = SchoolSettings.get('pass_mark', 50)
    bands = _grade_bands()

    assignments = _scope_assignments(term_id, 'school', None, allowed_ids)
    asg_by_class = {}
    for a in assignments:
        asg_by_class.setdefault(a.class_id, []).append(a)
    class_ids = list(asg_by_class)
    if not class_ids:
        return {'teacher': name, 'summary': {}, 'rows': [], 'by_subject': [],
                'by_class': [], 'trend': {'term_names': [], 'averages': []}}

    css = (ClassSubject.query.options(joinedload(ClassSubject.subject))
           .filter(ClassSubject.term_id == term_id, ClassSubject.is_active == True,  # noqa: E712
                   ClassSubject.class_id.in_(class_ids)).all())
    css = [cs for cs in css if (cs.teacher_name or '').strip().lower() == name.lower()]
    if not css:
        return {'teacher': name, 'summary': {}, 'rows': [], 'by_subject': [],
                'by_class': [], 'trend': {'term_names': [], 'averages': []}}

    rows = []
    all_totals = []
    students_seen = set()
    subj_roll, class_roll = {}, {}
    for cs in css:
        applic = [a for a in asg_by_class.get(cs.class_id, [])
                  if cs.arm_id is None or a.arm_id == cs.arm_id]
        enr = (StudentEnrollment.query
               .filter(StudentEnrollment.class_arm_assignment_id.in_([a.id for a in applic]),
                       StudentEnrollment.is_active == True).all()) if applic else []  # noqa: E712
        sids = [e.student_id for e in enr]
        totals = []
        if sids:
            per = {}
            for s in StudentScore.query.filter(
                    StudentScore.student_id.in_(sids),
                    StudentScore.class_subject_id == cs.id).all():
                if s.score is not None:
                    per[s.student_id] = per.get(s.student_id, 0) + s.score
            totals = [round(v, 2) for v in per.values()]
            students_seen.update(sids)
        label = ', '.join(sorted({a.display_name for a in applic})) or (
            cs.school_class.name if cs.school_class else '')
        avg = _mean(totals)
        pr = round(100 * sum(1 for t in totals if t >= pass_mark) / len(totals), 1) if totals else 0
        comp = round(100 * len(totals) / len(sids), 1) if sids else 0
        subj_name = cs.subject.name if cs.subject else f'Subject {cs.subject_id}'
        rows.append({
            'subject': subj_name, 'class': label, 'students': len(sids),
            'assessed': len(totals), 'average': avg, 'pass_rate': pr, 'completion': comp,
            'highest': round(max(totals), 1) if totals else 0,
            'lowest': round(min(totals), 1) if totals else 0,
        })
        all_totals += totals
        subj_roll.setdefault(subj_name, []).extend(totals)
        class_roll.setdefault(label, []).extend(totals)

    rows.sort(key=lambda r: (r['assessed'] == 0, r['average']))
    overall_avg = _mean(all_totals)
    overall_pr = round(100 * sum(1 for t in all_totals if t >= pass_mark) / len(all_totals), 1) if all_totals else 0
    possible = sum(r['students'] for r in rows)
    completion = round(100 * len(all_totals) / possible, 1) if possible else 0
    flag, verdict = _teacher_verdict(overall_avg, overall_pr, len(all_totals), completion)

    by_subject = sorted(
        [{'name': k, 'average': _mean(v), 'assessed': len(v),
          'pass_rate': round(100 * sum(1 for t in v if t >= pass_mark) / len(v), 1) if v else 0}
         for k, v in subj_roll.items()], key=lambda x: -x['average'])
    by_class = sorted(
        [{'name': k, 'average': _mean(v), 'assessed': len(v),
          'pass_rate': round(100 * sum(1 for t in v if t >= pass_mark) / len(v), 1) if v else 0}
         for k, v in class_roll.items()], key=lambda x: -x['average'])

    # Term trend for this teacher across the session.
    term = db.session.get(Term, term_id)
    names, averages = [], []
    if term and term.session_id:
        for t in Term.query.filter_by(session_id=term.session_id).order_by(Term.term_number).all():
            names.append(t.name)
            tcss = (ClassSubject.query.filter(
                ClassSubject.term_id == t.id, ClassSubject.is_active == True).all())  # noqa: E712
            tcss = [c for c in tcss if (c.teacher_name or '').strip().lower() == name.lower()]
            tot = []
            if tcss:
                for c in tcss:
                    for sc in StudentScore.query.filter_by(class_subject_id=c.id).all():
                        if sc.score is not None:
                            tot.append(sc.score)
            averages.append(round(sum(tot) / len(tot), 2) if tot else None)

    return {
        'teacher': name,
        'staff_id': resolve_teacher_staff(name),
        'summary': {'classes': len({r['class'] for r in rows}), 'subjects': len(subj_roll),
                    'students': len(students_seen), 'entries': len(all_totals),
                    'average': overall_avg, 'pass_rate': overall_pr, 'completion': completion,
                    'pass_mark': pass_mark, 'flag': flag, 'verdict': verdict},
        'rows': rows, 'by_subject': by_subject, 'by_class': by_class,
        'trend': {'term_names': names, 'averages': averages},
    }


def subject_scorecard(term_id, subject_id, allowed_ids=None):
    """Per-class-arm, per-teacher breakdown for one subject in a term — the
    drill-down behind the subject league. Returns overall KPIs, a row per
    class-arm (with its teacher), teacher/class roll-ups, grade spread and a
    term trend, so a head of department can see where the subject is hardest
    and which teachers get better results in it."""
    from sqlalchemy.orm import joinedload
    from models import (db, Subject, ClassSubject, StudentEnrollment, StudentScore,
                        SchoolSettings, Term)
    if not subject_id or not term_id:
        return None
    subject = db.session.get(Subject, int(subject_id))
    if not subject:
        return None
    pass_mark = SchoolSettings.get('pass_mark', 50)
    bands = _grade_bands()

    assignments = _scope_assignments(term_id, 'school', None, allowed_ids)
    asg_by_class = {}
    for a in assignments:
        asg_by_class.setdefault(a.class_id, []).append(a)
    class_ids = list(asg_by_class)
    empty = {'subject': subject.name, 'subject_id': subject.id, 'summary': {}, 'rows': [],
             'by_teacher': [], 'by_class': [], 'grade_distribution': [],
             'trend': {'term_names': [], 'averages': []}}
    if not class_ids:
        return empty

    css = (ClassSubject.query.options(joinedload(ClassSubject.school_class))
           .filter(ClassSubject.term_id == term_id, ClassSubject.is_active == True,  # noqa: E712
                   ClassSubject.subject_id == subject.id,
                   ClassSubject.class_id.in_(class_ids)).all())
    if not css:
        return empty

    rows, all_totals = [], []
    students_seen = set()
    teacher_roll, class_roll = {}, {}
    grade_dist = {g: 0 for g, _l, _h in bands}
    for cs in css:
        applic = [a for a in asg_by_class.get(cs.class_id, [])
                  if cs.arm_id is None or a.arm_id == cs.arm_id]
        enr = (StudentEnrollment.query
               .filter(StudentEnrollment.class_arm_assignment_id.in_([a.id for a in applic]),
                       StudentEnrollment.is_active == True).all()) if applic else []  # noqa: E712
        sids = [e.student_id for e in enr]
        totals = []
        if sids:
            per = {}
            for s in StudentScore.query.filter(
                    StudentScore.student_id.in_(sids),
                    StudentScore.class_subject_id == cs.id).all():
                if s.score is not None:
                    per[s.student_id] = per.get(s.student_id, 0) + s.score
            totals = [round(v, 2) for v in per.values()]
            students_seen.update(sids)
        for t in totals:
            grade_dist[_grade_for(t, bands)] = grade_dist.get(_grade_for(t, bands), 0) + 1
        teacher = (cs.teacher_name or '').strip() or 'Unassigned'
        label = ', '.join(sorted({a.display_name for a in applic})) or (
            cs.school_class.name if cs.school_class else '')
        avg = _mean(totals)
        pr = round(100 * sum(1 for t in totals if t >= pass_mark) / len(totals), 1) if totals else 0
        comp = round(100 * len(totals) / len(sids), 1) if sids else 0
        rows.append({
            'class': label, 'teacher': teacher, 'students': len(sids),
            'assessed': len(totals), 'average': avg, 'pass_rate': pr, 'completion': comp,
            'highest': round(max(totals), 1) if totals else 0,
            'lowest': round(min(totals), 1) if totals else 0,
        })
        all_totals += totals
        teacher_roll.setdefault(teacher, []).extend(totals)
        class_roll.setdefault(label, []).extend(totals)

    rows.sort(key=lambda r: (r['assessed'] == 0, r['average']))
    overall_avg = _mean(all_totals)
    overall_pr = round(100 * sum(1 for t in all_totals if t >= pass_mark) / len(all_totals), 1) if all_totals else 0
    dist = round(100 * sum(1 for t in all_totals if t >= DISTINCTION) / len(all_totals), 1) if all_totals else 0
    possible = sum(r['students'] for r in rows)
    completion = round(100 * len(all_totals) / possible, 1) if possible else 0

    def _roll(d):
        return sorted(
            [{'name': k, 'average': _mean(v), 'assessed': len(v),
              'pass_rate': round(100 * sum(1 for t in v if t >= pass_mark) / len(v), 1) if v else 0}
             for k, v in d.items()], key=lambda x: -x['average'])

    # Term trend for this subject across the session.
    term = db.session.get(Term, term_id)
    names, averages = [], []
    if term and term.session_id:
        for t in Term.query.filter_by(session_id=term.session_id).order_by(Term.term_number).all():
            names.append(t.name)
            tcss = ClassSubject.query.filter(
                ClassSubject.term_id == t.id, ClassSubject.subject_id == subject.id,
                ClassSubject.is_active == True).all()  # noqa: E712
            tot = []
            for c in tcss:
                for sc in StudentScore.query.filter_by(class_subject_id=c.id).all():
                    if sc.score is not None:
                        tot.append(sc.score)
            averages.append(round(sum(tot) / len(tot), 2) if tot else None)

    band_defs = [('0–39', 0, 39.999), ('40–49', 40, 49.999), ('50–59', 50, 59.999),
                 ('60–69', 60, 69.999), ('70–79', 70, 79.999), ('80–100', 80, 1e9)]
    return {
        'subject': subject.name, 'subject_id': subject.id,
        'summary': {'classes': len({r['class'] for r in rows}), 'teachers': len(teacher_roll),
                    'students': len(students_seen), 'entries': len(all_totals),
                    'average': overall_avg, 'pass_rate': overall_pr, 'distinction_rate': dist,
                    'completion': completion, 'pass_mark': pass_mark,
                    'highest': round(max(all_totals), 1) if all_totals else 0,
                    'lowest': round(min(all_totals), 1) if all_totals else 0},
        'rows': rows, 'by_teacher': _roll(teacher_roll), 'by_class': _roll(class_roll),
        'grade_distribution': [{'grade': g, 'count': grade_dist.get(g, 0)} for g, _l, _h in bands],
        'score_bands': [{'band': lbl, 'count': sum(1 for t in all_totals if lo <= t <= hi)}
                        for lbl, lo, hi in band_defs],
        'trend': {'term_names': names, 'averages': averages},
    }


def _empty(term_id, scope, scope_id, allowed_ids):
    return {
        'scope': scope, 'scope_id': scope_id,
        'scope_label': _scope_label(term_id, scope, scope_id, []),
        'summary': {}, 'grade_distribution': [], 'score_bands': [], 'gender': [],
        'subjects': [], 'teachers': [], 'units': [], 'unit_kind': 'Unit',
        'branches': [], 'attendance': {'bands': [], 'correlation': None},
        'top_students': [], 'honour_roll': [], 'intervention': [],
        'recommendations': [], 'trends': {'term_names': [], 'averages': [], 'pass_rates': []},
        'selectors': _selectors(term_id, allowed_ids),
    }
