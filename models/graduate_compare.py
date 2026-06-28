"""
Graduate vs current-SSS3 comparison analytics.

Schools want to know how the cohort that just graduated actually performed in
their real WAEC / JAMB, how that compared with their mocks, and — crucially —
how the *current* SSS3 class is tracking against them on the same yardsticks
(the mocks both cohorts have sat). Real WAEC/JAMB exists only for graduates, so
those columns are graduate-only; the mock columns are the apples-to-apples
comparison, and the graduates' mock->real pattern is the benchmark used to read
the current class's mocks.

Everything here works off explicit student-id lists supplied by the caller, so
branch / section scoping (and the "only admins, SSS3 form teachers and central
admins" gate) is enforced once at the route, not re-implemented here.
"""
from models.models import db, WAECResult, JAMBResult
from models.mock_waec import (
    MockWAECResult, MockWAECExam,
    PASS_GRADES, DISTINCTION_GRADES, GRADE_POINTS, CORE_SUBJECTS,
)
from models.mock_jamb import MockJAMBResult, MockJAMBExam


# JAMB score bands shared by real and mock JAMB aggregates.
_JAMB_BANDS = [
    ('excellent', 300, 'High (300+)'),
    ('good', 250, 'Good (250-299)'),
    ('fair', 200, 'Fair (200-249)'),
    ('weak', 180, 'Weak (180-199)'),
    ('poor', 0, 'Below 180'),
]
JAMB_ADMISSION_FLOOR = 180   # typical minimum competitive JAMB score


def _jamb_band(score):
    for key, floor, _ in _JAMB_BANDS:
        if score >= floor:
            return key
    return 'poor'


def _pct(n, d):
    return round(n / d * 100, 1) if d else 0.0


# ---------------------------------------------------------------------------
# Per-cohort WAEC-style aggregation (works for both real and mock WAEC)
# ---------------------------------------------------------------------------

def _summarise_waec_grades(grades):
    """credits / distinctions / core-credit flags from a list of letter grades.

    `grades` is a {subject: grade} mapping for one student's single sitting."""
    credits = sum(1 for g in grades.values() if g in PASS_GRADES)
    distinctions = sum(1 for g in grades.values() if g in DISTINCTION_GRADES)
    credited = {s for s, g in grades.items() if g in PASS_GRADES}
    missing_core = [s for s in CORE_SUBJECTS if s not in credited]
    return {
        'credits': credits,
        'distinctions': distinctions,
        'has_5_credits': credits >= 5,
        'has_5_incl_core': credits >= 5 and not missing_core,
    }


def _waec_cohort(per_student):
    """Aggregate {student_id: {subject: grade}} into cohort WAEC metrics."""
    summaries, grade_dist = [], {g: 0 for g in GRADE_POINTS}
    subj_total, subj_pass = {}, {}
    for grades in per_student.values():
        if not grades:
            continue
        summaries.append(_summarise_waec_grades(grades))
        for subj, g in grades.items():
            grade_dist[g] = grade_dist.get(g, 0) + 1
            subj_total[subj] = subj_total.get(subj, 0) + 1
            if g in PASS_GRADES:
                subj_pass[subj] = subj_pass.get(subj, 0) + 1
    n = len(summaries)
    subject_pass_rates = sorted(
        ({'subject': s, 'sat': subj_total[s], 'passed': subj_pass.get(s, 0),
          'pass_rate': _pct(subj_pass.get(s, 0), subj_total[s])}
         for s in subj_total),
        key=lambda r: r['pass_rate'], reverse=True)
    return {
        'n': n,
        'avg_credits': round(sum(s['credits'] for s in summaries) / n, 2) if n else 0,
        'avg_distinctions': round(sum(s['distinctions'] for s in summaries) / n, 2) if n else 0,
        'pct_5_credits': _pct(sum(1 for s in summaries if s['has_5_credits']), n),
        'pct_5_incl_core': _pct(sum(1 for s in summaries if s['has_5_incl_core']), n),
        'grade_distribution': grade_dist,
        'subject_pass_rates': subject_pass_rates,
    }


def _real_waec_per_student(student_ids):
    """{student_id: {subject: grade}} for each student's most recent WAEC year."""
    out = {}
    if not student_ids:
        return out
    rows = WAECResult.query.filter(WAECResult.student_id.in_(student_ids)).all()
    latest_year = {}
    for r in rows:
        if r.student_id not in latest_year or r.exam_year > latest_year[r.student_id]:
            latest_year[r.student_id] = r.exam_year
    for r in rows:
        if r.exam_year == latest_year.get(r.student_id):
            out.setdefault(r.student_id, {})[r.subject] = r.grade
    return out


def _mock_waec_per_student(student_ids):
    """{student_id: {subject: grade}} from each student's latest mock WAEC sitting."""
    out = {}
    if not student_ids:
        return out
    rows = (MockWAECResult.query
            .filter(MockWAECResult.student_id.in_(student_ids))
            .join(MockWAECExam, MockWAECResult.mock_exam_id == MockWAECExam.id)
            .order_by(MockWAECExam.exam_date.asc(), MockWAECExam.id.asc())
            .all())
    # Last sitting wins (rows ordered oldest->newest, so overwrite as we go).
    latest_exam = {}
    for r in rows:
        latest_exam[r.student_id] = r.mock_exam_id
    for r in rows:
        if r.mock_exam_id == latest_exam.get(r.student_id) and r.grade:
            out.setdefault(r.student_id, {})[r.subject] = r.grade
    return out


# ---------------------------------------------------------------------------
# Per-cohort JAMB aggregation (real and mock)
# ---------------------------------------------------------------------------

def _jamb_cohort(scores):
    bands = {key: 0 for key, _, _ in _JAMB_BANDS}
    for sc in scores:
        bands[_jamb_band(sc)] += 1
    n = len(scores)
    return {
        'n': n,
        'avg_score': round(sum(scores) / n, 1) if n else 0,
        'max_score': max(scores) if scores else 0,
        'min_score': min(scores) if scores else 0,
        'pct_above_floor': _pct(sum(1 for s in scores if s >= JAMB_ADMISSION_FLOOR), n),
        'bands': bands,
        'band_labels': [(key, label) for key, _, label in _JAMB_BANDS],
    }


def _real_jamb_scores(student_ids):
    """Best (highest) real JAMB total per student -> {student_id: score}."""
    out = {}
    if not student_ids:
        return out
    for r in JAMBResult.query.filter(JAMBResult.student_id.in_(student_ids)).all():
        if r.total_score is not None and r.total_score > out.get(r.student_id, -1):
            out[r.student_id] = r.total_score
    return out


def _mock_jamb_scores(student_ids):
    """Best (highest) mock JAMB total per student -> {student_id: score}."""
    out = {}
    if not student_ids:
        return out
    rows = (MockJAMBResult.query
            .filter(MockJAMBResult.student_id.in_(student_ids)).all())
    for r in rows:
        if r.total_score is not None and r.total_score > out.get(r.student_id, -1):
            out[r.student_id] = r.total_score
    return out


# ---------------------------------------------------------------------------
# Mock -> real "pattern" (graduates only): how well the mock predicted reality
# ---------------------------------------------------------------------------

def _mock_to_real_pattern(grad_ids, mock_waec, real_waec, mock_jamb, real_jamb):
    """For graduates with BOTH a mock and a real result, how the real outcome
    moved relative to the mock. This is the benchmark the current class's mocks
    are read against ("last year's mocks under-predicted credits by ~1")."""
    waec_pairs = []   # (mock_credits, real_credits)
    for sid in grad_ids:
        if sid in mock_waec and sid in real_waec:
            mc = _summarise_waec_grades(mock_waec[sid])['credits']
            rc = _summarise_waec_grades(real_waec[sid])['credits']
            waec_pairs.append((mc, rc))
    jamb_pairs = [(mock_jamb[sid], real_jamb[sid])
                  for sid in grad_ids if sid in mock_jamb and sid in real_jamb]

    def _delta(pairs):
        if not pairs:
            return None
        deltas = [r - m for m, r in pairs]
        avg = sum(deltas) / len(deltas)
        improved = sum(1 for d in deltas if d > 0)
        return {
            'n': len(pairs),
            'avg_delta': round(avg, 2),
            'pct_improved': _pct(improved, len(pairs)),
            'direction': ('improved' if avg > 0.05 else
                          'declined' if avg < -0.05 else 'held steady'),
        }
    return {'waec_credits': _delta(waec_pairs), 'jamb_score': _delta(jamb_pairs)}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compare_cohorts(grad_ids, sss3_ids):
    """Build the full graduate-vs-SSS3 comparison payload.

    `grad_ids` / `sss3_ids` are already branch/section-scoped student-id lists.
    Real WAEC/JAMB is graduate-only; mock columns cover both cohorts; the
    graduates' mock->real pattern projects the current class.
    """
    grad_ids = list(grad_ids or [])
    sss3_ids = list(sss3_ids or [])

    g_real_waec = _real_waec_per_student(grad_ids)
    g_mock_waec = _mock_waec_per_student(grad_ids)
    s_mock_waec = _mock_waec_per_student(sss3_ids)
    g_real_jamb = _real_jamb_scores(grad_ids)
    g_mock_jamb = _mock_jamb_scores(grad_ids)
    s_mock_jamb = _mock_jamb_scores(sss3_ids)

    pattern = _mock_to_real_pattern(grad_ids, g_mock_waec, g_real_waec,
                                    g_mock_jamb, g_real_jamb)

    # Project the current class's likely real outcome by applying the graduates'
    # observed mock->real shift to the current cohort's mock averages.
    s_mock_waec_agg = _waec_cohort(s_mock_waec)
    s_mock_jamb_agg = _jamb_cohort(list(s_mock_jamb.values()))
    projection = _project_current(s_mock_waec_agg, s_mock_jamb_agg, pattern)

    return {
        'cohorts': {
            'graduates': {'label': 'Graduates (last cohort)', 'total': len(grad_ids)},
            'sss3': {'label': 'Current SSS3', 'total': len(sss3_ids)},
        },
        'real_waec': {
            'graduates': _waec_cohort(g_real_waec),
            'sss3': None,   # current class has no real WAEC yet
        },
        'mock_waec': {
            'graduates': _waec_cohort(g_mock_waec),
            'sss3': s_mock_waec_agg,
        },
        'real_jamb': {
            'graduates': _jamb_cohort(list(g_real_jamb.values())),
            'sss3': None,
        },
        'mock_jamb': {
            'graduates': _jamb_cohort(list(g_mock_jamb.values())),
            'sss3': s_mock_jamb_agg,
        },
        'pattern': pattern,
        'projection': projection,
        'grade_order': list(GRADE_POINTS),
    }


def _project_current(sss3_mock_waec, sss3_mock_jamb, pattern):
    """Apply the graduates' mock->real shift to the current class's mock averages
    to get a data-grounded projection of where the current class may land."""
    out = {'waec': None, 'jamb': None}
    pw = pattern.get('waec_credits')
    if pw and sss3_mock_waec['n']:
        projected = max(0, round(sss3_mock_waec['avg_credits'] + pw['avg_delta'], 2))
        out['waec'] = {
            'mock_avg_credits': sss3_mock_waec['avg_credits'],
            'shift': pw['avg_delta'],
            'projected_avg_credits': projected,
            'basis_n': pw['n'],
        }
    pj = pattern.get('jamb_score')
    if pj and sss3_mock_jamb['n']:
        projected = max(0, round(sss3_mock_jamb['avg_score'] + pj['avg_delta'], 1))
        out['jamb'] = {
            'mock_avg_score': sss3_mock_jamb['avg_score'],
            'shift': pj['avg_delta'],
            'projected_avg_score': projected,
            'basis_n': pj['n'],
        }
    return out
