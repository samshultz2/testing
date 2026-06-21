"""Forward-looking exam insights that combine WAEC + JAMB and their mocks.

Where :func:`utils.admission.assess_admission` judges a student on *actual*
results, these helpers project the likely outcome from the Mock WAEC / Mock JAMB
trajectory, so SSS3 students get an actionable readiness picture *before* they
sit the real exams. Everything prefers actual results when they exist (a real
sitting beats a mock) and degrades gracefully when a signal is missing.
"""
from utils.admission import COURSE_CATEGORIES, PASS_GRADES

CORE_SUBJECTS = ('English Language', 'Mathematics')
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


def admission_readiness(student, session_id=None):
    """Combine the projected WAEC + JAMB outlook into a single readiness verdict
    with specific, actionable blockers.

    ``status`` is one of READY / CONDITIONAL / AT_RISK / NOT_READY / NO_DATA.
    Also returns the broad course categories the student is projected to qualify
    for (5 credits incl. English & Maths, the category's required subject credits,
    and the category JAMB cut-off all met)."""
    waec = projected_waec(student, session_id)
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
    counts = {k: 0 for k in STATUSES}
    proj_core = proj_jamb = proj_both = assessed = 0
    rows = []
    for st in students:
        r = admission_readiness(st, session_id)
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
# Mock -> real calibration
# --------------------------------------------------------------------------- #
def _student_pool(students):
    if students is not None:
        return students
    from models import Student
    return Student.query.all()


def jamb_calibration(students=None):
    """Measure how well the Mock JAMB predictor matched reality for students who
    have both mocks and an actual JAMB score. Returns ``n``, ``mae`` (mean
    absolute error), ``bias`` (mean predicted − actual; +ve = over-predicts) and
    ``within_20_pct``. A consistent bias is the signal to recalibrate."""
    from models.mock_jamb import MockJAMBAnalytics, MockJAMBResult, MockJAMBExam
    errors, n = [], 0
    for s in _student_pool(students):
        real = [r.total_score for r in s.jamb_results.all() if r.total_score is not None]
        if not real:
            continue
        latest = (MockJAMBResult.query.filter_by(student_id=s.id).join(MockJAMBExam)
                  .order_by(MockJAMBExam.exam_number.desc()).first())
        if not latest:
            continue
        pred = MockJAMBAnalytics.predict_real_jamb(s.id, latest.exam.session_id)
        if not pred:
            continue
        errors.append(pred['predicted_score'] - max(real))
        n += 1
    return _error_summary(errors, n, tol=20)


def waec_calibration(students=None):
    """As :func:`jamb_calibration` but for predicted vs actual WAEC *credit count*
    (error tolerance ±1 credit)."""
    from models.mock_waec import (MockWAECAnalytics, MockWAECResult, MockWAECExam,
                                  PASS_GRADES as W_PASS)
    errors, n = [], 0
    for s in _student_pool(students):
        by_year = {}
        for r in s.waec_results.all():
            by_year.setdefault(r.exam_year, {})[r.subject] = r.grade
        if not by_year:
            continue
        actual = max(len({sub for sub, g in subs.items() if g in W_PASS})
                     for subs in by_year.values())
        latest = (MockWAECResult.query.filter_by(student_id=s.id).join(MockWAECExam)
                  .order_by(MockWAECExam.exam_number.desc()).first())
        if not latest:
            continue
        pred = MockWAECAnalytics.predict_waec(s.id, latest.exam.session_id)
        if not pred:
            continue
        errors.append(pred['predicted_credits'] - actual)
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
