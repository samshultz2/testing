"""Services + analytics for the JSS3 (BECE) and Basic 6 (Common Entrance)
external exams. Pure functions over ``SchoolExamResult`` / ``SchoolExamCandidate``
— the routes in ``routes/school_exams`` only render what these return.

Everything is branch-scoped through ``utils.branch_scope``, like WAEC / JAMB.
"""
from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean, median, pstdev

from models import db, Student
from models.models_school_exams import (
    SchoolExamResult, SchoolExamCandidate, SchoolExamConfig, LEVELS, BODIES,
    KINDS, get_scheme, core_key, is_core_subject,
)

# --------------------------------------------------------------------------- #
# Schema self-heal (tenant DBs created before this feature)
# --------------------------------------------------------------------------- #
_ensured = set()


def ensure_school_exam_schema():
    """Create the three tables on the bound DB if missing. Once per engine."""
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return
    try:
        for model in (SchoolExamConfig, SchoolExamResult, SchoolExamCandidate):
            model.__table__.create(bind=engine, checkfirst=True)
        _ensured.add(key)
    except Exception:
        db.session.rollback()


# --------------------------------------------------------------------------- #
# Class / student resolution
# --------------------------------------------------------------------------- #
_CLASS_NAMES = {
    'jss3': {'jss3', 'js3', 'jss03', 'juniorsecondary3', 'juniorsecondaryschool3',
             'basic9', 'jhs3', 'year9'},
    'basic6': {'basic6', 'primary6', 'pry6', 'pri6', 'p6', 'prim6', 'grade6', 'year6',
               'bas6', 'b6'},
    'basic5': {'basic5', 'primary5', 'pry5', 'pri5', 'p5', 'prim5', 'grade5', 'year5',
               'bas5', 'b5'},
}

# Some schools write Common Entrance from Basic 5, others from Basic 6 (or
# both). Stored once per school; the "basic6" exams area follows it.
CE_SETTING_KEY = 'common_entrance_classes'
CE_CHOICES = {'basic6': 'Basic 6', 'basic5': 'Basic 5', 'both': 'Basic 5 and Basic 6'}


def ce_classes_setting():
    """'basic6' (default), 'basic5' or 'both'."""
    from models import SchoolSettings
    try:
        v = SchoolSettings.get(CE_SETTING_KEY, 'basic6')
    except Exception:
        db.session.rollback()
        v = 'basic6'
    return v if v in CE_CHOICES else 'basic6'


def level_class_keys(level):
    """The class-name keys that count for ``level`` (Basic 6 first)."""
    if level != 'basic6':
        return [level]
    return {'basic6': ['basic6'], 'basic5': ['basic5'], 'both': ['basic6', 'basic5']}[ce_classes_setting()]


def level_class_label(level):
    """'JSS3', 'Basic 6', 'Basic 5' or 'Basic 5 / 6'."""
    if level == 'jss3':
        return 'JSS3'
    return {'basic6': 'Basic 6', 'basic5': 'Basic 5', 'both': 'Basic 5 / 6'}[ce_classes_setting()]


def _find_class_by_key(key):
    from models import SchoolClass
    wanted = _CLASS_NAMES[key]
    for c in SchoolClass.query.order_by(SchoolClass.id).all():
        if _norm(c.name) in wanted:
            return c
    return None


def level_classes(level):
    """Every SchoolClass whose pupils sit this level's exam (for Common
    Entrance: Basic 6, Basic 5 or both, per the school's setting)."""
    out = []
    for key in level_class_keys(level):
        c = _find_class_by_key(key)
        if c is not None:
            out.append(c)
    return out


def level_class_ids(level):
    return [c.id for c in level_classes(level)]


def _norm(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def find_level_class(level):
    """The main SchoolClass for ``level`` (JSS3; Basic 6 — or Basic 5 when the
    school sits Common Entrance from Basic 5). Matched tolerantly by name
    (JSS 3, Junior Secondary 3, Primary 6, Pry 6 …)."""
    cls = level_classes(level)
    return cls[0] if cls else None


def _enrolled_rows(level, term_id=None):
    """(Student, arm name) for active enrolments in the level class this term."""
    from models import ClassArmAssignment, StudentEnrollment, ClassArm
    from utils.helpers import get_active_term
    from utils.branch_scope import scope_query
    cls_ids = level_class_ids(level)
    term = get_active_term() if term_id is None else None
    tid = term_id or (term.id if term else None)
    if not cls_ids or not tid:
        return []
    q = (db.session.query(Student, ClassArm.name)
         .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
         .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
         .join(ClassArm, ClassArm.id == ClassArmAssignment.arm_id)
         .filter(ClassArmAssignment.class_id.in_(cls_ids),
                 ClassArmAssignment.term_id == tid,
                 StudentEnrollment.is_active == True,     # noqa: E712
                 Student.is_active == True))              # noqa: E712
    return scope_query(q, Student).all()


def _recent_cohort(level):
    """Active students enrolled in the level class in any term of the active
    session or the session before it (branch-scoped)."""
    from models import ClassArmAssignment, StudentEnrollment, Term, AcademicSession
    from utils.helpers import get_active_session
    from utils.branch_scope import scope_query
    cls_ids = level_class_ids(level)
    cur = get_active_session()
    if not cls_ids or not cur:
        return []
    sessions = [cur.id]
    prev = (AcademicSession.query.filter(AcademicSession.id < cur.id)
            .order_by(AcademicSession.id.desc()).first())
    if prev:
        sessions.append(prev.id)
    q = (Student.query
         .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
         .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
         .join(Term, Term.id == ClassArmAssignment.term_id)
         .filter(ClassArmAssignment.class_id.in_(cls_ids), Term.session_id.in_(sessions),
                 Student.is_active == True)                # noqa: E712
         .distinct())
    return scope_query(q, Student).all()


def level_students(level, include_with_results=True):
    """Students who can have results for ``level``: everyone enrolled in the
    level class this term, plus (so results stay editable after promotion)
    anyone who already has results recorded for this level. Branch-scoped,
    sorted by name."""
    from utils.branch_scope import scope_query
    out = {s.id: s for s, _ in _enrolled_rows(level)}
    if include_with_results:
        # Results arrive after promotion (BECE / Common Entrance are released
        # when the cohort has already moved up), so last session's class counts.
        for s in _recent_cohort(level):
            out.setdefault(s.id, s)
        ids = {r[0] for r in db.session.query(SchoolExamResult.student_id)
               .filter(SchoolExamResult.level == level).distinct().all()}
        ids |= {r[0] for r in db.session.query(SchoolExamCandidate.student_id)
                .filter(SchoolExamCandidate.level == level).distinct().all()}
        ids -= set(out)
        if ids:
            for s in scope_query(Student.query.filter(Student.id.in_(ids)), Student).all():
                out[s.id] = s
    return sorted(out.values(), key=lambda s: ((s.surname or '').lower(), (s.first_name or '').lower()))


def student_arm_map(level, student_ids):
    """{student_id: arm name} from each student's most recent enrolment in the
    level's class(es), any term, so arm comparisons survive promotion. When
    two classes count (Basic 5 and 6) the class is included: "Basic 5 Gold"."""
    from models import ClassArmAssignment, StudentEnrollment, ClassArm, SchoolClass
    cls_ids = level_class_ids(level)
    if not cls_ids or not student_ids:
        return {}
    rows = (db.session.query(StudentEnrollment.student_id, ClassArm.name, SchoolClass.name)
            .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
            .join(ClassArm, ClassArm.id == ClassArmAssignment.arm_id)
            .join(SchoolClass, SchoolClass.id == ClassArmAssignment.class_id)
            .filter(ClassArmAssignment.class_id.in_(cls_ids),
                    StudentEnrollment.student_id.in_(list(student_ids)))
            .order_by(ClassArmAssignment.term_id).all())
    out = {}
    for sid, arm, cname in rows:
        out[sid] = f'{cname} {arm}' if len(cls_ids) > 1 else arm   # later terms win
    return out


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def entered_ids(level, body, year, student_ids):
    """Of ``student_ids``, those who already have results (or a sitting record)
    for this level / exam body / year — hidden from the "pick a student to
    enter" lists."""
    ids = list(student_ids or [])
    if not ids or not year:
        return set()
    out = {r[0] for r in db.session.query(SchoolExamResult.student_id).filter(
        SchoolExamResult.student_id.in_(ids), SchoolExamResult.level == level,
        SchoolExamResult.body == body, SchoolExamResult.exam_year == year).distinct()}
    out |= {r[0] for r in db.session.query(SchoolExamCandidate.student_id).filter(
        SchoolExamCandidate.student_id.in_(ids), SchoolExamCandidate.level == level,
        SchoolExamCandidate.body == body, SchoolExamCandidate.exam_year == year).distinct()}
    return out


def years_for(level, body=None):
    q = db.session.query(SchoolExamResult.exam_year).filter(SchoolExamResult.level == level)
    if body:
        q = q.filter(SchoolExamResult.body == body)
    ys = {r[0] for r in q.distinct().all()}
    q2 = db.session.query(SchoolExamCandidate.exam_year).filter(SchoolExamCandidate.level == level)
    if body:
        q2 = q2.filter(SchoolExamCandidate.body == body)
    ys |= {r[0] for r in q2.distinct().all()}
    return sorted(ys, reverse=True)


def _scoped(query, model, student_ids=None):
    from utils.branch_scope import scope_by_student
    query = scope_by_student(query, model)
    if student_ids is not None:
        query = query.filter(model.student_id.in_(list(student_ids) or [-1]))
    return query


def load(level, body, year, student_ids=None):
    """(results, candidates) for one level/body/year, branch-scoped."""
    res = _scoped(SchoolExamResult.query.filter_by(level=level, body=body, exam_year=year),
                  SchoolExamResult, student_ids).all()
    cands = _scoped(SchoolExamCandidate.query.filter_by(level=level, body=body, exam_year=year),
                    SchoolExamCandidate, student_ids).all()
    return res, cands


# --------------------------------------------------------------------------- #
# Saving
# --------------------------------------------------------------------------- #
def _num(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == '':
        return None
    try:
        return float(s)
    except ValueError:
        return None


def save_student_results(scheme, student_id, year, rows, candidate=None, replace=False):
    """Upsert one student's subject rows for (scheme.level, scheme.body, year).

    ``rows`` is an iterable of ``(subject, score, grade)``; a missing grade is
    derived from the score; a row with neither is skipped (or, with
    ``replace``, deleted). ``candidate`` is an optional dict of sitting fields
    (exam_number, centre, total_score, placement, admitted, remarks).
    Returns the number of subject rows saved. Caller commits."""
    level, body = scheme.level, scheme.body
    existing = {r.subject: r for r in SchoolExamResult.query.filter_by(
        student_id=student_id, level=level, body=body, exam_year=year).all()}
    saved, keep = 0, set()
    for subject, score, grade in rows:
        subject = (subject or '').strip()
        if not subject:
            continue
        score = _num(score)
        if score is not None:
            score = max(0.0, min(scheme.max_score, score))
        grade = (grade or '').strip().upper() or None
        if grade and not scheme.band_for_grade(grade):
            grade = None
        if not grade and score is not None:
            grade = scheme.grade_from_score(score)
        if not grade:
            continue
        keep.add(subject)
        r = existing.get(subject)
        if r is None:
            r = SchoolExamResult(student_id=student_id, level=level, body=body,
                                 exam_year=year, subject=subject)
            db.session.add(r)
            existing[subject] = r
        r.score, r.grade = score, grade
        saved += 1
    if replace:
        for subject, r in existing.items():
            if subject not in keep:
                db.session.delete(r)
    if candidate is not None:
        save_candidate(scheme, student_id, year, candidate)
    return saved


def save_candidate(scheme, student_id, year, data):
    c = SchoolExamCandidate.query.filter_by(student_id=student_id, level=scheme.level,
                                            body=scheme.body, exam_year=year).first()
    fields = {k: data.get(k) for k in ('exam_number', 'centre', 'total_score', 'placement',
                                        'admitted', 'remarks') if k in data}
    if c is None:
        if not any(v not in (None, '') for v in fields.values()):
            return None
        c = SchoolExamCandidate(student_id=student_id, level=scheme.level,
                                body=scheme.body, exam_year=year)
        db.session.add(c)
    for k in ('exam_number', 'centre', 'placement', 'remarks'):
        if k in fields:
            v = (fields[k] or '').strip() if isinstance(fields[k], str) else fields[k]
            setattr(c, k, (v or None) if v is not None else None)
    if 'total_score' in fields:
        c.total_score = _num(fields['total_score'])
    if 'admitted' in fields:
        a = fields['admitted']
        if isinstance(a, str):
            a = {'yes': True, 'true': True, '1': True, 'no': False, 'false': False,
                 '0': False}.get(a.strip().lower())
        c.admitted = a
    return c


def save_scheme(level, body, form):
    """Persist the settings form for (level, body). Returns (ok, message)."""
    import json
    from models.models_school_exams import normalise_bands
    row = SchoolExamConfig.query.filter_by(level=level, body=body).first()
    if row is None:
        row = SchoolExamConfig(level=level, body=body)
        db.session.add(row)
    row.exam_name = (form.get('exam_name') or '').strip()[:120] or None
    subjects = [s.strip() for s in re.split(r'[\n,]+', form.get('subjects') or '') if s.strip()]
    seen, clean = set(), []
    for s in subjects:
        if s.lower() not in seen:
            seen.add(s.lower())
            clean.append(s[:80])
    row.subjects_json = json.dumps(clean) if clean else None
    grades = form.getlist('band_grade')
    labels = form.getlist('band_label')
    mins = form.getlist('band_min')
    kinds = form.getlist('band_kind')
    bands = [{'grade': g, 'label': l, 'min': m, 'kind': k}
             for g, l, m, k in zip(grades, labels, mins, kinds) if (g or '').strip()]
    nb = normalise_bands(bands)
    if bands and not nb:
        return False, 'Grade bands are invalid — each needs a letter, a minimum % and a kind.'
    row.bands_json = json.dumps(nb) if nb else None
    ms = _num(form.get('max_score'))
    row.max_score = ms if ms and ms > 0 else None
    bc = _num(form.get('benchmark_credits'))
    row.benchmark_credits = int(bc) if bc is not None and bc >= 0 else None
    co = _num(form.get('cutoff'))
    row.cutoff = co
    return True, 'Settings saved.'


# --------------------------------------------------------------------------- #
# Per-candidate summaries
# --------------------------------------------------------------------------- #
def _pct(scheme, score):
    return None if score is None else round(float(score) / scheme.max_score * 100.0, 2)


def candidate_summaries(scheme, results, candidates, students=None):
    """One summary dict per candidate (student with results or a sitting row),
    ranked best first. ``students`` may pre-supply {id: Student}."""
    by_student = defaultdict(list)
    for r in results:
        by_student[r.student_id].append(r)
    cand_by = {c.student_id: c for c in candidates}
    ids = set(by_student) | set(cand_by)
    if students is None:
        students = {s.id: s for s in Student.query.filter(Student.id.in_(list(ids) or [-1])).all()}
    out = []
    for sid in ids:
        st = students.get(sid)
        if st is None:
            continue
        rows = sorted(by_student.get(sid, []), key=lambda r: r.subject)
        c = cand_by.get(sid)
        kinds = defaultdict(int)
        grades = defaultdict(int)
        core = {}
        for r in rows:
            k = scheme.kind_of(r.grade) or 'fail'
            kinds[k] += 1
            grades[r.grade] += 1
            ck = core_key(r.subject)
            if ck:
                core[ck] = scheme.is_credit(r.grade)
        credits = kinds['distinction'] + kinds['credit']
        passes = credits + kinds['pass']
        scores = [r.score for r in rows if r.score is not None]
        total = c.total_score if c and c.total_score is not None else (sum(scores) if scores else None)
        avg_pct = round(mean(_pct(scheme, s) for s in scores), 1) if scores else None
        gp = [scheme.grade_points(r.grade) for r in rows]
        core_credits = bool(core.get('english')) and bool(core.get('mathematics'))
        bench = scheme.benchmark_credits
        meets = bool(rows) and core_credits and (bench is None or credits >= bench)
        above_cut = (total >= scheme.cutoff) if (scheme.cutoff is not None and total is not None) else None
        out.append({
            'id': sid, 'student': st, 'name': st.full_name, 'student_code': st.student_id,
            'gender': (st.gender or '').title() or 'Unknown',
            'subjects': len(rows), 'results': rows,
            'grades': dict(grades), 'kinds': dict(kinds),
            'distinctions': kinds['distinction'], 'credits': credits, 'passes': passes,
            'fails': kinds['fail'],
            'avg_pct': avg_pct, 'total': round(total, 1) if total is not None else None,
            'avg_points': round(mean(gp), 2) if gp else 0,
            'core_credits': core_credits, 'meets_benchmark': meets,
            'above_cutoff': above_cut,
            'exam_number': c.exam_number if c else None,
            'centre': c.centre if c else None,
            'placement': c.placement if c else None,
            'admitted': c.admitted if c else None,
            'remarks': c.remarks if c else None,
        })
    out.sort(key=lambda d: (-(d['avg_points'] or 0), -(d['avg_pct'] or 0),
                            -(d['total'] or 0), d['name'].lower()))
    for i, d in enumerate(out, 1):
        d['position'] = i
    return out


# --------------------------------------------------------------------------- #
# Year statistics
# --------------------------------------------------------------------------- #
def _rate(n, d):
    return round(n / d * 100, 1) if d else 0.0


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** .5
    sy = sum((y - my) ** 2 for y in ys) ** .5
    if not sx or not sy:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), 3)


def subject_rows(scheme, results):
    """Per-subject analysis rows (entries, mean %, kinds, rates, grade counts)."""
    agg = defaultdict(list)
    for r in results:
        agg[r.subject].append(r)
    rows = []
    for subject, rs in agg.items():
        n = len(rs)
        kinds = defaultdict(int)
        grades = defaultdict(int)
        for r in rs:
            kinds[scheme.kind_of(r.grade) or 'fail'] += 1
            grades[r.grade] += 1
        scores = [_pct(scheme, r.score) for r in rs if r.score is not None]
        credits = kinds['distinction'] + kinds['credit']
        rows.append({
            'subject': subject, 'entries': n, 'core': is_core_subject(subject),
            'grades': dict(grades), 'kinds': dict(kinds),
            'distinctions': kinds['distinction'], 'credits': credits,
            'passes': credits + kinds['pass'], 'fails': kinds['fail'],
            'distinction_rate': _rate(kinds['distinction'], n),
            'credit_rate': _rate(credits, n),
            'pass_rate': _rate(credits + kinds['pass'], n),
            'fail_rate': _rate(kinds['fail'], n),
            'mean_pct': round(mean(scores), 1) if scores else None,
            'high_pct': round(max(scores), 1) if scores else None,
            'low_pct': round(min(scores), 1) if scores else None,
            'avg_points': round(mean(scheme.grade_points(r.grade) for r in rs), 2),
        })
    rows.sort(key=lambda r: (-r['credit_rate'], -(r['mean_pct'] or 0), r['subject']))
    for i, r in enumerate(rows, 1):
        r['rank'] = i
    return rows


def _group_rows(summaries, key):
    groups = defaultdict(list)
    for s in summaries:
        groups[key(s) or 'Unassigned'].append(s)
    out = []
    for name, ss in groups.items():
        out.append(_kpis_from(ss) | {'group': name})
    out.sort(key=lambda r: (-r['benchmark_rate'], -(r['avg_pct'] or 0), r['group']))
    return out


def _kpis_from(summaries, scheme=None):
    n = len(summaries)
    with_rows = [s for s in summaries if s['subjects']]
    pcts = [s['avg_pct'] for s in with_rows if s['avg_pct'] is not None]
    totals = [s['total'] for s in summaries if s['total'] is not None]
    adm_known = [s for s in summaries if s['admitted'] is not None]
    cut_known = [s for s in summaries if s['above_cutoff'] is not None]
    return {
        'candidates': n,
        'avg_pct': round(mean(pcts), 1) if pcts else None,
        'median_pct': round(median(pcts), 1) if pcts else None,
        'sd_pct': round(pstdev(pcts), 1) if len(pcts) > 1 else None,
        'avg_total': round(mean(totals), 1) if totals else None,
        'highest_total': max(totals) if totals else None,
        'lowest_total': min(totals) if totals else None,
        'avg_credits': round(mean(s['credits'] for s in with_rows), 2) if with_rows else 0,
        'avg_points': round(mean(s['avg_points'] for s in with_rows), 2) if with_rows else 0,
        'benchmark': sum(1 for s in summaries if s['meets_benchmark']),
        'benchmark_rate': _rate(sum(1 for s in summaries if s['meets_benchmark']), len(with_rows)),
        'core_credit': sum(1 for s in with_rows if s['core_credits']),
        'core_credit_rate': _rate(sum(1 for s in with_rows if s['core_credits']), len(with_rows)),
        'all_pass': sum(1 for s in with_rows if s['fails'] == 0),
        'all_pass_rate': _rate(sum(1 for s in with_rows if s['fails'] == 0), len(with_rows)),
        'with_distinction': sum(1 for s in with_rows if s['distinctions'] > 0),
        'admitted': sum(1 for s in adm_known if s['admitted']),
        'admission_known': len(adm_known),
        'admission_rate': _rate(sum(1 for s in adm_known if s['admitted']), len(adm_known)),
        'above_cutoff': sum(1 for s in cut_known if s['above_cutoff']),
        'cutoff_known': len(cut_known),
        'cutoff_rate': _rate(sum(1 for s in cut_known if s['above_cutoff']), len(cut_known)),
    }


def year_stats(level, body, year, student_ids=None):
    """Everything the dashboard / analytics pages need for one year."""
    scheme = get_scheme(level, body)
    results, cands = load(level, body, year, student_ids)
    summaries = candidate_summaries(scheme, results, cands)
    kpis = _kpis_from(summaries)
    n_entries = len(results)
    kind_counts = {k: 0 for k in KINDS}
    grade_dist = {g: 0 for g in scheme.grades}
    for r in results:
        kind_counts[scheme.kind_of(r.grade) or 'fail'] += 1
        grade_dist[r.grade] = grade_dist.get(r.grade, 0) + 1
    kpis.update({
        'entries': n_entries,
        'subject_pass_rate': _rate(n_entries - kind_counts['fail'], n_entries),
        'subject_credit_rate': _rate(kind_counts['distinction'] + kind_counts['credit'], n_entries),
        'subject_distinction_rate': _rate(kind_counts['distinction'], n_entries),
    })
    subjects = subject_rows(scheme, results)

    # Compare each subject's credit rate with the previous year with data.
    prev_year = next((y for y in years_for(level, body) if y < year), None)
    if prev_year:
        prev_res, _ = load(level, body, prev_year, student_ids)
        prev = {r['subject']: r for r in subject_rows(scheme, prev_res)}
        for r in subjects:
            p = prev.get(r['subject'])
            r['credit_delta'] = round(r['credit_rate'] - p['credit_rate'], 1) if p else None
    arms = student_arm_map(level, [s['id'] for s in summaries])
    for s in summaries:
        s['arm'] = arms.get(s['id'])
    # Credit-count distribution: how many candidates got 0, 1, 2 … credits.
    max_c = max((s['credits'] for s in summaries), default=0)
    credit_hist = [{'credits': i, 'count': sum(1 for s in summaries if s['subjects'] and s['credits'] == i)}
                   for i in range(0, max_c + 1)]
    # Average-% histogram in 10-point buckets.
    buckets = [{'label': f'{b}–{b + 9}' if b < 90 else '90–100', 'count': 0} for b in range(0, 100, 10)]
    for s in summaries:
        if s['avg_pct'] is not None:
            buckets[min(9, int(s['avg_pct'] // 10))]['count'] += 1
    core = [r for r in subjects if r['core']]
    placements = defaultdict(int)
    for s in summaries:
        if s['placement']:
            placements[s['placement'].strip()] += 1
    return {
        'placements': sorted(placements.items(), key=lambda kv: (-kv[1], kv[0].lower())),
        'scheme': scheme, 'year': year, 'prev_year': prev_year,
        'kpis': kpis, 'kind_counts': kind_counts, 'grade_dist': grade_dist,
        'subjects': subjects, 'candidates': summaries,
        'top': summaries[:10],
        'struggling': sorted([s for s in summaries if s['subjects']],
                             key=lambda s: (s['avg_points'], s['avg_pct'] or 0))[:10],
        'by_arm': _group_rows(summaries, lambda s: s.get('arm')),
        'by_gender': _group_rows(summaries, lambda s: s['gender']),
        'credit_hist': credit_hist, 'pct_hist': buckets, 'core': core,
        'has_scores': any(r.score is not None for r in results),
    }


# Candidate-list orderings for the dashboard: key -> (label, sort key).
# Every ordering ends in name so ties are stable and predictable.
CANDIDATE_SORTS = {
    'position': ('Position (best first)', lambda c: (c['position'],)),
    'name': ('Name A–Z', lambda c: (c['name'].lower(),)),
    'name_desc': ('Name Z–A', None),
    'distinctions': ('Most distinctions', lambda c: (-c['distinctions'], -c['credits'],
                                                     -(c['avg_pct'] or 0), c['name'].lower())),
    'credits': ('Most credits', lambda c: (-c['credits'], -c['distinctions'],
                                           -(c['avg_pct'] or 0), c['name'].lower())),
    'avg': ('Highest average %', lambda c: (-(c['avg_pct'] if c['avg_pct'] is not None else -1),
                                            c['name'].lower())),
    'total': ('Highest total', lambda c: (-(c['total'] if c['total'] is not None else -1),
                                          c['name'].lower())),
}


def sort_candidates(cands, key):
    """Order dashboard candidates by ``key`` (see CANDIDATE_SORTS). Unknown
    keys fall back to position. Returns (sorted list, key actually used)."""
    if key not in CANDIDATE_SORTS:
        key = 'position'
    if key == 'name_desc':
        return sorted(cands, key=lambda c: c['name'].lower(), reverse=True), key
    return sorted(cands, key=CANDIDATE_SORTS[key][1]), key


def trend(level, body, student_ids=None):
    """Year-over-year headline KPIs (oldest first) for the trend charts."""
    out = []
    for y in sorted(years_for(level, body)):
        st = year_stats(level, body, y, student_ids)
        k = st['kpis']
        if not k['candidates']:
            continue
        out.append({'year': y, 'candidates': k['candidates'], 'avg_pct': k['avg_pct'],
                    'benchmark_rate': k['benchmark_rate'], 'core_credit_rate': k['core_credit_rate'],
                    'subject_credit_rate': k['subject_credit_rate'],
                    'subject_pass_rate': k['subject_pass_rate'],
                    'avg_credits': k['avg_credits'], 'admission_rate': k['admission_rate'],
                    'avg_total': k['avg_total']})
    return out


def subject_trend(level, body, subject, student_ids=None):
    scheme = get_scheme(level, body)
    out = []
    for y in sorted(years_for(level, body)):
        res, _ = load(level, body, y, student_ids)
        rows = [r for r in subject_rows(scheme, res) if r['subject'] == subject]
        if rows:
            r = rows[0]
            out.append({'year': y, 'entries': r['entries'], 'credit_rate': r['credit_rate'],
                        'pass_rate': r['pass_rate'], 'mean_pct': r['mean_pct']})
    return out


def subject_detail(level, body, year, subject, student_ids=None):
    """Drill-down for one subject in one year: grade spread, per-grade candidate
    lists, arm / gender comparison and trend."""
    scheme = get_scheme(level, body)
    results, _ = load(level, body, year, student_ids)
    rs = [r for r in results if r.subject == subject]
    if not rs:
        return None
    row = subject_rows(scheme, rs)[0]
    arms = student_arm_map(level, {r.student_id for r in rs})
    by_grade = {g: [] for g in scheme.grades}
    groups_arm, groups_gender = defaultdict(list), defaultdict(list)
    for r in sorted(rs, key=lambda r: (-(r.score or -1), r.student.full_name)):
        by_grade.setdefault(r.grade, []).append(r)
        groups_arm[arms.get(r.student_id) or 'Unassigned'].append(r)
        groups_gender[(r.student.gender or 'Unknown').title()].append(r)

    def _grp(groups):
        out = []
        for name, items in groups.items():
            sr = subject_rows(scheme, items)[0]
            out.append({'group': name, 'entries': sr['entries'], 'credit_rate': sr['credit_rate'],
                        'pass_rate': sr['pass_rate'], 'mean_pct': sr['mean_pct']})
        return sorted(out, key=lambda r: (-r['credit_rate'], r['group']))

    # This subject vs the candidates' average in their other subjects — a
    # positive gap means the subject is a relative strength of the cohort.
    others = defaultdict(list)
    for r in results:
        if r.subject != subject:
            others[r.student_id].append(scheme.grade_points(r.grade))
    gaps = [scheme.grade_points(r.grade) - mean(others[r.student_id])
            for r in rs if others.get(r.student_id)]
    return {'scheme': scheme, 'row': row, 'by_grade': by_grade,
            'by_arm': _grp(groups_arm), 'by_gender': _grp(groups_gender),
            'relative_gap': round(mean(gaps), 2) if gaps else None,
            'trend': subject_trend(level, body, subject, student_ids)}


# --------------------------------------------------------------------------- #
# Cross comparisons
# --------------------------------------------------------------------------- #
def compare_bodies(level, year, student_ids=None):
    """State vs federal for the same year: headline KPIs side-by-side and, for
    candidates who sat both, a per-subject paired comparison + correlation."""
    st = year_stats(level, 'state', year, student_ids)
    fd = year_stats(level, 'federal', year, student_ids)
    if not st['kpis']['candidates'] or not fd['kpis']['candidates']:
        return {'state': st['kpis'], 'federal': fd['kpis'], 'both': 0, 'subjects': [],
                'corr': None, 'state_name': st['scheme'].exam_name,
                'federal_name': fd['scheme'].exam_name}
    sm = {s['id']: s for s in st['candidates']}
    fm = {s['id']: s for s in fd['candidates']}
    both = set(sm) & set(fm)
    xs, ys = [], []
    for sid in both:
        if sm[sid]['avg_points'] and fm[sid]['avg_points']:
            # normalise grade points to 0..1 because the schemes may differ
            xs.append(sm[sid]['avg_points'] / max(1, len(st['scheme'].bands)))
            ys.append(fm[sid]['avg_points'] / max(1, len(fd['scheme'].bands)))
    s_sub = {r['subject']: r for r in st['subjects']}
    f_sub = {r['subject']: r for r in fd['subjects']}
    subjects = []
    for name in sorted(set(s_sub) & set(f_sub)):
        a, b = s_sub[name], f_sub[name]
        subjects.append({'subject': name, 'state_credit': a['credit_rate'],
                         'federal_credit': b['credit_rate'],
                         'diff': round(a['credit_rate'] - b['credit_rate'], 1),
                         'state_mean': a['mean_pct'], 'federal_mean': b['mean_pct']})
    return {'state': st['kpis'], 'federal': fd['kpis'], 'both': len(both),
            'subjects': subjects, 'corr': _corr(xs, ys),
            'state_name': st['scheme'].exam_name, 'federal_name': fd['scheme'].exam_name}


def internal_vs_external(level, summaries):
    """Correlate each candidate's internal (school) average in the level class
    with their external average %. Shows whether school assessment predicts
    the external exam, and flags the biggest over/under-performers."""
    from models import TermSummary, StudentEnrollment, ClassArmAssignment
    cls_ids = level_class_ids(level)
    ids = [s['id'] for s in summaries if s['avg_pct'] is not None]
    if not cls_ids or not ids:
        return None
    rows = (db.session.query(TermSummary.student_id, TermSummary.average_score, TermSummary.term_id)
            .join(StudentEnrollment, StudentEnrollment.id == TermSummary.enrollment_id)
            .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
            .filter(ClassArmAssignment.class_id.in_(cls_ids),
                    TermSummary.student_id.in_(ids),
                    TermSummary.average_score.isnot(None)).all())
    internal = defaultdict(list)
    for sid, avg, _tid in rows:
        internal[sid].append(avg)
    pairs = []
    for s in summaries:
        if s['id'] in internal and s['avg_pct'] is not None:
            iv = round(mean(internal[s['id']]), 1)
            pairs.append({'id': s['id'], 'name': s['name'], 'internal': iv,
                          'external': s['avg_pct'], 'gap': round(s['avg_pct'] - iv, 1)})
    if not pairs:
        return None
    pairs.sort(key=lambda p: p['gap'])
    return {
        'n': len(pairs),
        'corr': _corr([p['internal'] for p in pairs], [p['external'] for p in pairs]),
        'avg_internal': round(mean(p['internal'] for p in pairs), 1),
        'avg_external': round(mean(p['external'] for p in pairs), 1),
        'under': pairs[:5],
        'over': list(reversed(pairs[-5:])),
        'points': [[p['internal'], p['external']] for p in pairs],
    }


def level_overview(level):
    """Headline numbers for the level selector card (both bodies, latest year)."""
    out = {}
    for body in BODIES:
        ys = years_for(level, body)
        if not ys:
            out[body] = {'years': [], 'latest': None, 'kpis': None}
            continue
        st = year_stats(level, body, ys[0])
        out[body] = {'years': ys, 'latest': ys[0], 'kpis': st['kpis'],
                     'exam_name': st['scheme'].exam_name}
    return out


# --------------------------------------------------------------------------- #
# CSV / paste import
# --------------------------------------------------------------------------- #
_META_COLS = {
    'student_id': {'student id', 'student_id', 'admission no', 'admission number', 'adm no', 'reg no', 'id'},
    'name': {'name', 'student', 'student name', 'full name', 'candidate', 'candidate name'},
    'exam_number': {'exam number', 'exam no', 'exam_number', 'candidate number', 'examination number'},
    'centre': {'centre', 'center', 'exam centre'},
    'total_score': {'total', 'total score', 'aggregate', 'total_score'},
    'placement': {'placement', 'school offered', 'admission', 'school placed'},
    'admitted': {'admitted'},
    'remarks': {'remark', 'remarks'},
}


def parse_import(scheme, text, students):
    """Parse a pasted / CSV grid: a header row naming columns, then one row per
    candidate. Identifies students by Student ID (preferred) or name; subject
    columns are matched to the configured subjects (case-insensitive). Cells
    may hold a score or a grade letter. Returns (rows, errors, subjects)."""
    import csv
    import io
    text = (text or '').strip()
    if not text:
        return [], ['Nothing to import.'], []
    sample = text.splitlines()[0]
    delim = '\t' if '\t' in sample else (';' if sample.count(';') > sample.count(',') else ',')
    reader = list(csv.reader(io.StringIO(text), delimiter=delim))
    header = [h.strip() for h in reader[0]]
    meta, subj_cols, errors = {}, {}, []
    from utils.quick_results import make_subject_resolver
    from models.models_school_exams import KNOWN_BASIC_SUBJECTS
    resolve = make_subject_resolver(scheme.subjects, KNOWN_BASIC_SUBJECTS)
    for i, h in enumerate(header):
        hl = h.lower()
        mk = next((k for k, names in _META_COLS.items() if hl in names), None)
        if mk:
            meta[mk] = i
        elif h and resolve(h):            # "PVS", "Nat Val", "Eng" → the subject
            subj_cols[i] = resolve(h)
        elif h:
            # Unknown subject column: accept it under the header's own name.
            subj_cols[i] = h.strip()
    if 'student_id' not in meta and 'name' not in meta:
        return [], ['The header row needs a "Student ID" or "Name" column.'], []
    by_code = {(s.student_id or '').strip().lower(): s for s in students}
    by_name = {}
    for s in students:
        by_name[_norm(s.full_name)] = s
        by_name[_norm(f'{s.first_name} {s.surname}')] = s
        by_name[_norm(f'{s.surname} {s.first_name}')] = s
    rows = []
    for ln, raw in enumerate(reader[1:], 2):
        if not any(c.strip() for c in raw):
            continue
        cell = lambda k: raw[meta[k]].strip() if k in meta and meta[k] < len(raw) else ''  # noqa: E731
        st = None
        if cell('student_id'):
            st = by_code.get(cell('student_id').lower())
        if st is None and cell('name'):
            st = by_name.get(_norm(cell('name')))
        label = cell('student_id') or cell('name')
        row_errors = []
        if st is None:
            # Kept as a row (not dropped) so the caller can offer to add the
            # student to the register or move them into the class.
            row_errors.append(f'No {scheme.level.upper()} candidate matches "{label}".')
        subjects = []
        for i, subj in subj_cols.items():
            v = raw[i].strip() if i < len(raw) else ''
            if not v:
                continue
            if _num(v) is not None:
                subjects.append((subj, v, None))
            elif scheme.band_for_grade(v):
                subjects.append((subj, None, v.upper()))
            else:
                errors.append(f'Line {ln}: "{v}" is not a score or a valid grade for {subj}.')
        cand = {k: cell(k) for k in ('exam_number', 'centre', 'total_score', 'placement',
                                       'admitted', 'remarks') if k in meta and cell(k)}
        rows.append({'student': st, 'subjects': subjects, 'candidate': cand, 'line': ln,
                     'name': cell('name') or label, 'code': cell('student_id'), 'errors': row_errors, 'score': 1.0 if st else 0.0,
                     'items': subjects})
    return rows, errors, list(subj_cols.values())


# --------------------------------------------------------------------------- #
# Chart.js configs (colours as var(--sx-*) tokens, resolved client-side)
# --------------------------------------------------------------------------- #
KIND_COLOR = {'distinction': 'var(--sx-dist)', 'credit': 'var(--sx-credit)',
              'pass': 'var(--sx-pass)', 'fail': 'var(--sx-fail)'}
_PCT_AXIS = {'beginAtZero': True, 'max': 100}


class charts:
    """Namespace of chart-config builders used by the templates."""

    @staticmethod
    def grade_dist(stats):
        sc = stats['scheme']
        return {'type': 'bar',
                'data': {'labels': [f"{b['grade']} · {b['label']}" for b in sc.bands],
                         'datasets': [{'label': 'Entries',
                                       'data': [stats['grade_dist'].get(b['grade'], 0) for b in sc.bands],
                                       'backgroundColor': [KIND_COLOR[b['kind']] for b in sc.bands]}]},
                'options': {'plugins': {'legend': {'display': False}},
                            'scales': {'y': {'beginAtZero': True, 'ticks': {'precision': 0}}}}}

    @staticmethod
    def kind_mix(stats):
        kc = stats['kind_counts']
        return {'type': 'doughnut',
                'data': {'labels': [k.title() for k in KINDS],
                         'datasets': [{'data': [kc.get(k, 0) for k in KINDS],
                                       'backgroundColor': [KIND_COLOR[k] for k in KINDS]}]},
                'options': {'cutout': '62%'}}

    @staticmethod
    def trend(rows, series):
        """``series`` = [(key, label), …] — all percentages, so one shared axis."""
        colors = ['var(--sx-s1)', 'var(--sx-s2)']
        return {'type': 'line',
                'data': {'labels': [r['year'] for r in rows],
                         'datasets': [{'label': lab, 'data': [r[key] for r in rows],
                                       'borderColor': colors[i % 2], 'backgroundColor': colors[i % 2]}
                                      for i, (key, lab) in enumerate(series)]},
                'options': {'scales': {'y': dict(_PCT_AXIS)}}}

    @staticmethod
    def subject_stack(subjects):
        """Stacked 100% horizontal bars: each subject's distinction/credit/pass/fail mix."""
        rows = sorted(subjects, key=lambda r: -r['credit_rate'])
        ds = []
        for k in KINDS:
            ds.append({'label': k.title(), 'backgroundColor': KIND_COLOR[k], 'borderRadius': 0,
                       'data': [round(r['kinds'].get(k, 0) / r['entries'] * 100, 1) if r['entries'] else 0
                                for r in rows]})
        return {'type': 'bar',
                'data': {'labels': [r['subject'] for r in rows], 'datasets': ds},
                'options': {'indexAxis': 'y', 'plugins': {'legend': {'display': False}},
                            'scales': {'x': {'stacked': True, 'max': 100, 'beginAtZero': True},
                                       'y': {'stacked': True}}}}

    @staticmethod
    def histogram(items, label_key, value_key, label):
        return {'type': 'bar',
                'data': {'labels': [str(i[label_key]) for i in items],
                         'datasets': [{'label': label, 'data': [i[value_key] for i in items],
                                       'backgroundColor': 'var(--sx-s1)'}]},
                'options': {'plugins': {'legend': {'display': False}},
                            'scales': {'y': {'beginAtZero': True, 'ticks': {'precision': 0}}}}}

    @staticmethod
    def group_bars(groups, keys):
        """Grouped bars per arm / gender for a couple of % measures (one axis)."""
        colors = ['var(--sx-s1)', 'var(--sx-s2)']
        return {'type': 'bar',
                'data': {'labels': [g['group'] for g in groups],
                         'datasets': [{'label': lab, 'data': [g[key] for g in groups],
                                       'backgroundColor': colors[i % 2]}
                                      for i, (key, lab) in enumerate(keys)]},
                'options': {'scales': {'y': dict(_PCT_AXIS)}}}

    @staticmethod
    def scatter(points, xlab, ylab):
        return {'type': 'scatter',
                'data': {'datasets': [{'label': 'Candidates',
                                       'data': [{'x': x, 'y': y} for x, y in points],
                                       'backgroundColor': 'var(--sx-s1)', 'pointRadius': 5}]},
                'options': {'plugins': {'legend': {'display': False}},
                            'scales': {'x': {'title': {'display': True, 'text': xlab}, 'min': 0, 'max': 100},
                                       'y': {'title': {'display': True, 'text': ylab}, 'min': 0, 'max': 100}}}}

    @staticmethod
    def dual_trend(a_rows, b_rows, key, a_label, b_label):
        """One measure (a %) over years for two exams, aligned on a shared year axis."""
        years = sorted({r['year'] for r in a_rows} | {r['year'] for r in b_rows})
        am = {r['year']: r[key] for r in a_rows}
        bm = {r['year']: r[key] for r in b_rows}
        return {'type': 'line',
                'data': {'labels': years, 'datasets': [
                    {'label': a_label, 'data': [am.get(y) for y in years],
                     'borderColor': 'var(--sx-s1)', 'backgroundColor': 'var(--sx-s1)'},
                    {'label': b_label, 'data': [bm.get(y) for y in years],
                     'borderColor': 'var(--sx-s2)', 'backgroundColor': 'var(--sx-s2)'}]},
                'options': {'spanGaps': True, 'scales': {'y': dict(_PCT_AXIS)}}}

    @staticmethod
    def paired_bars(rows, label_key, a_key, b_key, a_label, b_label):
        return {'type': 'bar',
                'data': {'labels': [r[label_key] for r in rows], 'datasets': [
                    {'label': a_label, 'data': [r[a_key] for r in rows], 'backgroundColor': 'var(--sx-s1)'},
                    {'label': b_label, 'data': [r[b_key] for r in rows], 'backgroundColor': 'var(--sx-s2)'}]},
                'options': {'scales': {'y': dict(_PCT_AXIS)}}}


# --------------------------------------------------------------------------- #
# Broadsheet (grade matrix) — same shape as the WAEC broadsheet, so the WAEC
# print-PDF builder and the shared export helpers render it unchanged.
# --------------------------------------------------------------------------- #
def broadsheet(level, body, year, arms=None, subjects=None, order='name'):
    """Grade matrix for one level / exam body / year.

    ``arms``: only candidates in these arm labels; ``subjects``: only these
    columns; ``order``: 'name' (register order) or 'position' (best first).
    Cells read "A (72)" when a score is known, else just the grade."""
    st = year_stats(level, body, year)
    scheme = st['scheme']
    cands = st['candidates']
    if arms:
        want = {a.lower() for a in arms}
        cands = [c for c in cands if (c.get('arm') or 'Unassigned').lower() in want]
    present = {r.subject for c in cands for r in c['results']}
    ordered = [s for s in scheme.subjects if s in present] + sorted(present - set(scheme.subjects))
    if subjects:
        ordered = [s for s in ordered if s in set(subjects)] or ordered
    if order == 'position':
        cands = sorted(cands, key=lambda c: c['position'])
    else:
        cands = sorted(cands, key=lambda c: c['name'].lower())
    rows = []
    for c in cands:
        s = c['student']
        cells = {}
        for r in c['results']:
            cells[r.subject] = f'{r.grade} ({r.score:g})' if r.score is not None else r.grade
        rows.append({
            'student': {'id': s.id, 'full_name': s.full_name, 'surname': s.surname or '',
                        'first_name': s.first_name or '', 'middle_name': s.middle_name or '',
                        'arm': c.get('arm') or ''},
            'cells': cells, 'grades': {r.subject: r.grade for r in c['results']},
            'credits': c['credits'], 'distinctions': c['distinctions'],
            'avg_grade': '' if c['avg_pct'] is None else f"{c['avg_pct']:g}%",
            'position': c['position'], 'total': c['total'],
            'meets_benchmark': c['meets_benchmark'],
        })
    srows = {r['subject']: r for r in subject_rows(scheme, [x for c in cands for x in c['results']])}
    summary = {}
    for subj in ordered:
        r = srows.get(subj)
        summary[subj] = {'offered': r['entries'] if r else 0, 'passed': r['passes'] if r else 0,
                         'failed': r['fails'] if r else 0,
                         'avg_grade': (f"{r['mean_pct']:g}%" if r and r['mean_pct'] is not None
                                       else (f"{r['credit_rate']:g}% cr" if r else ''))}
    arm_names = sorted({(c.get('arm') or 'Unassigned') for c in st['candidates']})
    return {'subjects': ordered, 'rows': rows, 'subject_summary': summary,
            'scheme': scheme, 'kpis': _kpis_from(cands), 'arms': arm_names,
            'grade_dist': st['grade_dist']}


# --------------------------------------------------------------------------- #
# Per-student views (student page + the consolidated exam report)
# --------------------------------------------------------------------------- #
def student_sittings(student, levels=('jss3', 'basic6')):
    """Every BECE / Common Entrance sitting of ``student``: one dict per
    (level, body, year) with the scheme, the candidate summary (credits,
    distinctions, avg %, position …) and the cohort size. Newest first."""
    out = []
    for level in levels:
        for body in BODIES:
            years = ({r[0] for r in db.session.query(SchoolExamResult.exam_year).filter_by(
                student_id=student.id, level=level, body=body).distinct()}
                | {r[0] for r in db.session.query(SchoolExamCandidate.exam_year).filter_by(
                    student_id=student.id, level=level, body=body).distinct()})
            if not years:
                continue
            scheme = get_scheme(level, body)
            for y in sorted(years, reverse=True):
                res, cands = load(level, body, y)
                summ = candidate_summaries(scheme, res, cands)
                me = next((s for s in summ if s['id'] == student.id), None)
                if me is None:          # outside the viewer's branch scope
                    continue
                me['cohort'] = len(summ)
                out.append({'level': level, 'body': body, 'year': y, 'scheme': scheme,
                            'name': scheme.exam_name, 's': me})
    out.sort(key=lambda x: (-x['year'], x['level'], x['body']))
    return out


def student_exam_level(student):
    """'sss3', 'jss3', 'basic6' (Common Entrance class per the setting) or
    None — from the student's class this term (latest active enrolment)."""
    from models import ClassArmAssignment, StudentEnrollment
    from utils.helpers import get_sss3_class, get_active_term
    term = get_active_term()
    q = (db.session.query(ClassArmAssignment.class_id)
         .join(StudentEnrollment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
         .filter(StudentEnrollment.student_id == student.id, StudentEnrollment.is_active == True))  # noqa: E712
    if term is not None:
        row = q.filter(ClassArmAssignment.term_id == term.id).first()
        row = row or q.order_by(ClassArmAssignment.term_id.desc()).first()
    else:
        row = q.order_by(ClassArmAssignment.term_id.desc()).first()
    if not row:
        return None
    cid = row[0]
    sss3 = get_sss3_class()
    if sss3 is not None and cid == sss3.id:
        return 'sss3'
    for level in ('jss3', 'basic6'):
        if cid in level_class_ids(level):
            return level
    return None


# Subject families for the (guidance-only) SSS stream suggestion after BECE.
_SCIENCE = ('mathematics', 'basic science', 'basic technology', 'basic science and technology',
            'computer', 'basic digital literacy', 'agricultural science')
_COMMERCIAL = ('business studies', 'mathematics', 'pre-vocational studies', 'home economics')
_ARTS = ('english', 'social studies', 'civic education', 'national values', 'christian religious',
         'islamic', 'cultural and creative arts', 'history', 'french', 'literature', 'arabic',
         'edo', 'yoruba', 'igbo', 'hausa')


def _family_score(results, scheme, family):
    pts = [scheme.grade_points(r.grade) / max(1, len(scheme.bands))
           for r in results if any(r.subject.lower().startswith(f) for f in family)]
    return (sum(pts) / len(pts), len(pts)) if pts else (None, 0)


def readiness_after(sitting):
    """What a BECE / Common Entrance result means for the next step.

    JSS3 → SSS1 readiness: benchmark (N credits incl. English & Maths) met or
    not, what is missing, strongest / weakest subjects and a suggested SSS
    stream (guidance only). Basic 5/6 → JSS1 placement: cut-off and outcome."""
    s, scheme = sitting['s'], sitting['scheme']
    rows = s['results']
    ranked = sorted(rows, key=lambda r: (-scheme.grade_points(r.grade), -(r.score or 0), r.subject))
    missing_core = []
    has = {core_key(r.subject): scheme.is_credit(r.grade) for r in rows if core_key(r.subject)}
    for key, label in (('english', 'English'), ('mathematics', 'Mathematics')):
        if not has.get(key):
            missing_core.append(label)
    bench = scheme.benchmark_credits
    out = {
        'meets': s['meets_benchmark'], 'benchmark': bench, 'credits': s['credits'],
        'credits_short': max(0, (bench or 0) - s['credits']), 'missing_core': missing_core,
        'strongest': [r for r in ranked if scheme.is_credit(r.grade)][:3],
        'weakest': [r for r in reversed(ranked) if not scheme.is_credit(r.grade)][:3],
        'above_cutoff': s['above_cutoff'], 'cutoff': scheme.cutoff, 'total': s['total'],
        'admitted': s['admitted'], 'placement': s['placement'],
    }
    if sitting['level'] == 'jss3':
        fams = {'Science': _family_score(rows, scheme, _SCIENCE),
                'Commercial': _family_score(rows, scheme, _COMMERCIAL),
                'Arts': _family_score(rows, scheme, _ARTS)}
        scored = [(k, v[0]) for k, v in fams.items() if v[0] is not None and v[1] >= 2]
        if scored:
            best = max(scored, key=lambda kv: kv[1])
            # Science needs a Maths credit — otherwise suggest the next best.
            if best[0] == 'Science' and not has.get('mathematics'):
                others = [kv for kv in scored if kv[0] != 'Science']
                best = max(others, key=lambda kv: kv[1]) if others else best
            out['stream'] = best[0]
            out['stream_scores'] = {k: round(v * 100) for k, v in scored}
    return out
