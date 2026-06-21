"""Forward-looking exam insights that combine WAEC + JAMB and their mocks.

Where :func:`utils.admission.assess_admission` judges a student on *actual*
results, these helpers project the likely outcome from the Mock WAEC / Mock JAMB
trajectory, so SSS3 students get an actionable readiness picture *before* they
sit the real exams. Everything prefers actual results when they exist (a real
sitting beats a mock) and degrades gracefully when a signal is missing.
"""
from models.mock_waec import CORE_SUBJECTS          # single source of truth
from utils.admission import COURSE_CATEGORIES, PASS_GRADES

JAMB_BASELINE = 180          # the cut-off many courses accept as a floor

# O'level grade -> points for a typical 50/50 post-UTME aggregate (A1=6 … C6=1).
OLEVEL_POINTS = {'A1': 6, 'B2': 5, 'B3': 4, 'C4': 3, 'C5': 2, 'C6': 1}


def _split_subjects(raw):
    """Parse a stored comma-joined subject string into a clean list."""
    if not raw:
        return []
    return [s.strip() for s in raw.split(',') if s.strip()]


def _jamb_band(score):
    if score >= 250:
        return 'Highly competitive'
    if score >= 200:
        return 'Competitive'
    if score >= JAMB_BASELINE:
        return 'Eligible for many courses'
    if score > 0:
        return 'Below common cut-offs'
    return 'No score yet'


# --------------------------------------------------------------------------- #
# Per-student outlooks
# --------------------------------------------------------------------------- #
def projected_waec(student, session_id=None):
    """Best available WAEC outlook for a student.

    Prefers actual WAEC (best year by credit count); otherwise projects from the
    Mock WAEC trajectory. Returns a dict with ``credits``, ``credited_subjects``,
    ``credited_grades``, ``missing_core``, ``meets_ssc`` and ``source`` — or
    ``None`` when there is no WAEC signal at all."""
    by_year = {}
    for r in student.waec_results.all():
        by_year.setdefault(r.exam_year, {})[r.subject] = r.grade
    if by_year:
        best = max(by_year.values(),
                   key=lambda subs: sum(1 for g in subs.values() if g in PASS_GRADES))
        credited = {s: g for s, g in best.items() if g in PASS_GRADES}
        missing_core = [s for s in CORE_SUBJECTS if s not in credited]
        return {
            'source': 'actual',
            'credits': len(credited),
            'credited_subjects': sorted(credited),
            'credited_grades': list(credited.values()),
            'missing_core': missing_core,
            'meets_ssc': len(credited) >= 5 and not missing_core,
            'confidence': 100,
        }

    # Fall back to the Mock WAEC projection + the latest sitting's subject grades.
    from models.mock_waec import (MockWAECAnalytics, MockWAECExam, MockWAECResult,
                                  PASS_GRADES as W_PASS)
    pred = MockWAECAnalytics.predict_waec(student.id, session_id)
    if not pred:
        return None
    q = MockWAECResult.query.filter_by(student_id=student.id).join(MockWAECExam)
    if session_id:
        q = q.filter(MockWAECExam.session_id == session_id)
    latest = q.order_by(MockWAECExam.exam_number.desc(), MockWAECResult.id.desc()).all()
    seen, credited = set(), {}
    for r in latest:                       # rows are newest-first; keep the latest per subject
        if r.subject in seen:
            continue
        seen.add(r.subject)
        if r.grade in W_PASS:
            credited[r.subject] = r.grade
    return {
        'source': 'mock',
        'credits': pred['predicted_credits'],
        'credited_subjects': sorted(credited),
        'credited_grades': list(credited.values()),
        'missing_core': pred['missing_core'],
        'meets_ssc': pred['meets_minimum_incl_core'],
        'quality': pred['quality'],
        'confidence': pred['confidence'],
    }


def projected_jamb(student, session_id=None):
    """Best available JAMB outlook. Prefers the best actual JAMB score; otherwise
    the Mock JAMB prediction. Returns a dict with ``score``/``band`` or None."""
    actual = [r.total_score for r in student.jamb_results.all() if r.total_score is not None]
    if actual:
        score = max(actual)
        return {'source': 'actual', 'score': score, 'confidence': 100,
                'band': _jamb_band(score)}
    if not session_id:
        return None
    from models.mock_jamb import MockJAMBAnalytics
    pred = MockJAMBAnalytics.predict_real_jamb(student.id, session_id)
    if not pred:
        return None
    score = pred['predicted_score']
    return {'source': 'mock', 'score': score,
            'confidence': pred.get('confidence_level'),
            'range': pred.get('predicted_range'), 'band': _jamb_band(score)}


def post_utme_aggregate(jamb_score, grades):
    """A representative 50/50 post-UTME aggregate (out of 100).

    Schemes vary by institution; this is the widely-used model: UTME scaled to 50
    (score/400×50) plus O'level best-five grade points scaled to 50 (A1=6 … C6=1,
    max 30 → ×50/30). Returns the two components and the total."""
    utme = round((jamb_score or 0) / 400 * 50, 1)
    pts = sorted((OLEVEL_POINTS.get(g, 0) for g in (grades or [])), reverse=True)[:5]
    olevel = round(sum(pts) / 30 * 50, 1)
    return {'utme_component': utme, 'olevel_component': olevel,
            'aggregate': round(utme + olevel, 1), 'scheme': '50/50 UTME+O’level'}


_UNSET = object()


def admission_readiness(student, session_id=None, waec=_UNSET, jamb=_UNSET):
    """Combine the projected WAEC + JAMB outlook into a single readiness verdict
    with specific, actionable blockers.

    ``status`` is one of READY / CONDITIONAL / AT_RISK / NOT_READY / NO_DATA.
    Also returns the broad course categories the student is projected to qualify
    for (5 credits incl. English & Maths, the category's required subject credits,
    and the category JAMB cut-off all met).

    ``waec`` / ``jamb`` may be passed pre-computed (e.g. from a batched cohort
    pass) to avoid per-student queries; omit them for the single-student path."""
    if waec is _UNSET:
        waec = projected_waec(student, session_id)
    if jamb is _UNSET:
        jamb = projected_jamb(student, session_id)
    if not waec and not jamb:
        return {'status': 'NO_DATA', 'blockers': [], 'waec': None, 'jamb': None,
                'eligible_categories': [], 'aggregate': None, 'source': None}

    credits = waec['credits'] if waec else 0
    missing_core = waec['missing_core'] if waec else list(CORE_SUBJECTS)
    meets_ssc = bool(waec and waec['meets_ssc'])
    credited = set(waec['credited_subjects']) if waec else set()
    jamb_score = jamb['score'] if jamb else 0

    blockers = []
    if waec:
        if credits < 5:
            blockers.append(f'Projected {credits} credits — needs 5')
        for s in missing_core:
            blockers.append(f'No {s} credit projected')
    else:
        blockers.append('No WAEC signal yet (no results or mocks)')
    if jamb:
        if jamb_score < JAMB_BASELINE:
            blockers.append(f'Projected JAMB {jamb_score} below {JAMB_BASELINE}')
    else:
        blockers.append('No JAMB signal yet (no results or mocks)')

    eligible = []
    for c in COURSE_CATEGORIES:
        subjects_ok = all(s in credited for s in c['required'])
        if meets_ssc and subjects_ok and jamb_score >= c['jamb']:
            eligible.append(c['name'])

    if meets_ssc and jamb_score >= JAMB_BASELINE:
        status = 'READY'
    elif (meets_ssc and jamb_score >= 150) or \
         (credits >= 5 and len(missing_core) <= 1 and jamb_score >= JAMB_BASELINE):
        status = 'CONDITIONAL'
    elif credits >= 4 or jamb_score >= 150:
        status = 'AT_RISK'
    else:
        status = 'NOT_READY'

    aggregate = post_utme_aggregate(jamb_score, waec['credited_grades']) if waec else None

    return {'status': status, 'blockers': blockers, 'waec': waec, 'jamb': jamb,
            'eligible_categories': eligible, 'aggregate': aggregate,
            'source': (waec or jamb)['source']}


# UTME subject combinations differ from O'level requirements (English is the
# compulsory 4th UTME subject, and e.g. Medicine takes Bio/Chem/Phys — not Maths).
# These are the non-English UTME subjects typically required per category.
JAMB_COMBOS = [
    ('Medicine & Health Sciences', ['Biology', 'Chemistry', 'Physics']),
    ('Engineering & Technology', ['Mathematics', 'Physics', 'Chemistry']),
    ('Physical & Computer Sciences', ['Mathematics', 'Physics']),
    ('Agricultural & Biological Sciences', ['Biology', 'Chemistry']),
    ('Law', ['Literature in English', 'Government']),
    ('Social Sciences & Management', ['Economics', 'Mathematics']),
    ('Arts & Humanities', ['Literature in English', 'Government']),
    ('Education', ['Mathematics']),
]


def jamb_subject_combo_check(student):
    """Validate the student's intended JAMB subjects against typical UTME
    combinations. English is compulsory in the UTME, so only the other
    (science/arts) requirements are checked. Returns a per-category fit list —
    useful for catching a wrong subject combination early, while it can still be
    changed."""
    intended = set(_split_subjects(student.jamb_subjects))
    if not intended:
        return {'intended': [], 'categories': []}
    out = []
    for name, needed in JAMB_COMBOS:
        missing = [s for s in needed if s not in intended]
        out.append({'name': name, 'missing': missing, 'fits': not missing})
    out.sort(key=lambda x: (not x['fits'], x['name']))
    return {'intended': sorted(intended), 'categories': out}


# --------------------------------------------------------------------------- #
# Cohort funnel
# --------------------------------------------------------------------------- #
STATUSES = ('READY', 'CONDITIONAL', 'AT_RISK', 'NOT_READY', 'NO_DATA')


def cohort_readiness(students, session_id=None):
    """Aggregate :func:`admission_readiness` across an iterable of students into a
    funnel: status counts, plus how many are projected to get 5 credits incl.
    core, to clear the JAMB baseline, and to clear *both* (admission-ready)."""
    students = list(students)
    ids = [s.id for s in students]
    # Project the whole cohort with a fixed handful of bulk queries, then build
    # each verdict from the pre-computed projections (no per-student queries).
    waec_map = _batch_projected_waec(ids, session_id)
    jamb_map = _batch_projected_jamb(ids, session_id)

    counts = {k: 0 for k in STATUSES}
    proj_core = proj_jamb = proj_both = assessed = 0
    rows = []
    for st in students:
        r = admission_readiness(st, session_id,
                                waec=waec_map.get(st.id), jamb=jamb_map.get(st.id))
        counts[r['status']] += 1
        meets_ssc = bool(r['waec'] and r['waec']['meets_ssc'])
        jamb_ok = bool(r['jamb'] and r['jamb']['score'] >= JAMB_BASELINE)
        if r['status'] != 'NO_DATA':
            assessed += 1
        proj_core += meets_ssc
        proj_jamb += jamb_ok
        proj_both += meets_ssc and jamb_ok
        rows.append({'student': st, 'readiness': r})
    total = len(rows)
    pct = lambda n: round(n / total * 100, 1) if total else 0.0
    return {
        'total': total,
        'assessed': assessed,
        'counts': counts,
        'projected_5_incl_core': proj_core,
        'projected_5_incl_core_pct': pct(proj_core),
        'projected_jamb_ok': proj_jamb,
        'projected_jamb_ok_pct': pct(proj_jamb),
        'projected_both': proj_both,
        'projected_both_pct': pct(proj_both),
        'rows': rows,
    }


# --------------------------------------------------------------------------- #
# Batched projections (one set of bulk queries for a whole cohort)
# --------------------------------------------------------------------------- #
def _batch_projected_jamb(ids, session_id):
    """{student_id -> projected_jamb dict} for the cohort, mirroring
    :func:`projected_jamb`. Prefers actual JAMB; else the Mock JAMB prediction.
    Two queries (actual + mocks) regardless of cohort size."""
    from collections import defaultdict
    from sqlalchemy.orm import contains_eager
    from models import db, JAMBResult
    from models.mock_jamb import MockJAMBAnalytics, MockJAMBResult, MockJAMBExam
    out = {}
    if not ids:
        return out
    actual = {}
    for sid, score in (db.session.query(JAMBResult.student_id, JAMBResult.total_score)
                       .filter(JAMBResult.student_id.in_(ids),
                               JAMBResult.total_score.isnot(None)).all()):
        actual[sid] = max(actual.get(sid, score), score)
    for sid, score in actual.items():
        out[sid] = {'source': 'actual', 'score': score, 'confidence': 100,
                    'band': _jamb_band(score)}

    remaining = [i for i in ids if i not in actual]
    if remaining and session_id:
        by_student = defaultdict(list)
        rows = (MockJAMBResult.query.join(MockJAMBExam)
                .options(contains_eager(MockJAMBResult.exam))
                .filter(MockJAMBResult.student_id.in_(remaining),
                        MockJAMBExam.session_id == session_id)
                .order_by(MockJAMBResult.student_id, MockJAMBExam.exam_number).all())
        for r in rows:
            by_student[r.student_id].append(r)
        for sid, srows in by_student.items():
            pred = MockJAMBAnalytics._predict_from_progress(
                MockJAMBAnalytics._progress_from_results(sid, srows))
            if pred:
                score = pred['predicted_score']
                out[sid] = {'source': 'mock', 'score': score,
                            'confidence': pred.get('confidence_level'),
                            'range': pred.get('predicted_range'), 'band': _jamb_band(score)}
    return out


def _batch_projected_waec(ids, session_id):
    """{student_id -> projected_waec dict} for the cohort, mirroring
    :func:`projected_waec`. Prefers actual WAEC; else the Mock WAEC projection."""
    from collections import defaultdict
    from sqlalchemy.orm import contains_eager
    from models import db, WAECResult
    from models.mock_waec import (MockWAECAnalytics, MockWAECResult, MockWAECExam,
                                  PASS_GRADES as W_PASS)
    out = {}
    if not ids:
        return out

    # Actual WAEC — best year by credit count.
    by_student_year = defaultdict(lambda: defaultdict(dict))    # sid -> year -> {subject: grade}
    for sid, year, subj, grade in (db.session.query(
            WAECResult.student_id, WAECResult.exam_year, WAECResult.subject, WAECResult.grade)
            .filter(WAECResult.student_id.in_(ids)).all()):
        by_student_year[sid][year][subj] = grade
    for sid, years in by_student_year.items():
        best = max(years.values(), key=lambda subs: sum(1 for g in subs.values() if g in PASS_GRADES))
        credited = {s: g for s, g in best.items() if g in PASS_GRADES}
        missing_core = [s for s in CORE_SUBJECTS if s not in credited]
        out[sid] = {'source': 'actual', 'credits': len(credited),
                    'credited_subjects': sorted(credited),
                    'credited_grades': list(credited.values()),
                    'missing_core': missing_core,
                    'meets_ssc': len(credited) >= 5 and not missing_core, 'confidence': 100}

    remaining = [i for i in ids if i not in out]
    if remaining and session_id:
        by_student = defaultdict(list)
        rows = (MockWAECResult.query.join(MockWAECExam)
                .options(contains_eager(MockWAECResult.exam))
                .filter(MockWAECResult.student_id.in_(remaining),
                        MockWAECExam.session_id == session_id)
                .order_by(MockWAECResult.student_id, MockWAECExam.exam_number).all())
        for r in rows:
            by_student[r.student_id].append(r)
        for sid, srows in by_student.items():
            pred = MockWAECAnalytics._predict_from_progress(
                MockWAECAnalytics._progress_from_rows(sid, srows))
            if not pred:
                continue
            # Most recent grade per subject across the student's sittings.
            seen, credited = set(), {}
            for r in sorted(srows, key=lambda r: (r.exam.exam_number, r.id), reverse=True):
                if r.subject in seen:
                    continue
                seen.add(r.subject)
                if r.grade in W_PASS:
                    credited[r.subject] = r.grade
            out[sid] = {'source': 'mock', 'credits': pred['predicted_credits'],
                        'credited_subjects': sorted(credited),
                        'credited_grades': list(credited.values()),
                        'missing_core': pred['missing_core'],
                        'meets_ssc': pred['meets_minimum_incl_core'],
                        'quality': pred['quality'], 'confidence': pred['confidence']}
    return out


# --------------------------------------------------------------------------- #
# Mock -> real calibration
# --------------------------------------------------------------------------- #
def _student_ids(students):
    if students is not None:
        return [s.id for s in students]
    from models import Student
    return [sid for (sid,) in db.session.query(Student.id).all()]


def _latest_mock_session(model_result, model_exam, ids):
    """Map student_id -> session_id of their highest-numbered mock sitting, via one
    bulk query (so we don't probe per student)."""
    from models import db
    best = {}
    for sid, session_id, num in (db.session.query(
            model_result.student_id, model_exam.session_id, model_exam.exam_number)
            .join(model_exam, model_result.mock_exam_id == model_exam.id)
            .filter(model_result.student_id.in_(ids)).all()):
        if sid not in best or num > best[sid][0]:
            best[sid] = (num, session_id)
    return {sid: v[1] for sid, v in best.items()}


def jamb_calibration(students=None):
    """Measure how well the Mock JAMB predictor matched reality for students who
    have both mocks and an actual JAMB score. Returns ``n``, ``mae`` (mean
    absolute error), ``bias`` (mean predicted − actual; +ve = over-predicts) and
    ``within_tol_pct``. A consistent bias is the signal to recalibrate.

    Bulk-loads actual scores and each student's latest mock session up front, so
    the (expensive) per-student prediction runs only for students who have both."""
    from models import db, JAMBResult
    from models.mock_jamb import MockJAMBAnalytics, MockJAMBResult, MockJAMBExam
    ids = _student_ids(students)
    if not ids:
        return _error_summary([], 0, tol=20)
    actual = {}
    for sid, score in (db.session.query(JAMBResult.student_id, JAMBResult.total_score)
                       .filter(JAMBResult.student_id.in_(ids),
                               JAMBResult.total_score.isnot(None)).all()):
        actual[sid] = max(actual.get(sid, score), score)
    latest_session = _latest_mock_session(MockJAMBResult, MockJAMBExam, ids)
    errors, n = [], 0
    for sid in ids:
        if sid not in actual or sid not in latest_session:
            continue
        pred = MockJAMBAnalytics.predict_real_jamb(sid, latest_session[sid])
        if not pred:
            continue
        errors.append(pred['predicted_score'] - actual[sid])
        n += 1
    return _error_summary(errors, n, tol=20)


def waec_calibration(students=None):
    """As :func:`jamb_calibration` but for predicted vs actual WAEC *credit count*
    (error tolerance ±1 credit). Same bulk-load-then-predict-valid-pairs shape."""
    from models import db, WAECResult
    from models.mock_waec import (MockWAECAnalytics, MockWAECResult, MockWAECExam,
                                  PASS_GRADES as W_PASS)
    from collections import defaultdict
    ids = _student_ids(students)
    if not ids:
        return _error_summary([], 0, tol=1)
    by_year = defaultdict(lambda: defaultdict(set))        # sid -> year -> credited subjects
    for sid, year, subj, grade in (db.session.query(
            WAECResult.student_id, WAECResult.exam_year, WAECResult.subject, WAECResult.grade)
            .filter(WAECResult.student_id.in_(ids)).all()):
        if grade in W_PASS:
            by_year[sid][year].add(subj)
    actual = {sid: max(len(s) for s in years.values()) for sid, years in by_year.items()}
    latest_session = _latest_mock_session(MockWAECResult, MockWAECExam, ids)
    errors, n = [], 0
    for sid in ids:
        if sid not in actual or sid not in latest_session:
            continue
        pred = MockWAECAnalytics.predict_waec(sid, latest_session[sid])
        if not pred:
            continue
        errors.append(pred['predicted_credits'] - actual[sid])
        n += 1
    return _error_summary(errors, n, tol=1)


def _error_summary(errors, n, tol):
    if not n:
        return {'n': 0}
    mae = round(sum(abs(e) for e in errors) / n, 2)
    bias = round(sum(errors) / n, 2)
    within = round(sum(1 for e in errors if abs(e) <= tol) / n * 100, 1)
    return {'n': n, 'mae': mae, 'bias': bias, 'tolerance': tol, 'within_tol_pct': within}


def calibration_summary(students=None):
    """Both calibration views for the predictions dashboard."""
    return {'jamb': jamb_calibration(students), 'waec': waec_calibration(students)}
