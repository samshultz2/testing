"""School-level exam trend analytics that use data we already capture but didn't
previously analyse: subject-level JAMB performance, Mock WAEC subject
value-added across sittings, and the attendance <-> results correlation.
"""


def _pearson(xs, ys):
    """Pearson correlation of two equal-length sequences, or None when it's
    undefined (fewer than 2 points or a flat series)."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def _mean_sd(xs):
    """Population mean and standard deviation, or (mean, None) when SD is
    undefined (fewer than 2 points)."""
    n = len(xs)
    if n == 0:
        return None, None
    m = sum(xs) / n
    if n < 2:
        return m, None
    var = sum((x - m) ** 2 for x in xs) / n
    return m, var ** 0.5


def standardized_mock_jamb_progress(student_id, session_id=None):
    """The student's standing in each Mock JAMB sitting expressed as a z-score and
    percentile relative to that sitting's cohort.

    A raw 220 on a hard mock is not the same as 220 on an easy one; standardizing
    against each sitting's mean/SD makes the trend reflect *relative* movement,
    robust to a sitting being unusually hard or easy. Returns None if the student
    sat no mocks in scope."""
    from models.mock_jamb import MockJAMBExam
    q = MockJAMBExam.query
    if session_id:
        q = q.filter_by(session_id=session_id)
    points = []
    for ex in q.order_by(MockJAMBExam.exam_number).all():
        results = ex.results.all()
        scores = [r.total_score for r in results]
        mine = next((r.total_score for r in results if r.student_id == student_id), None)
        if mine is None:
            continue
        m, sd = _mean_sd(scores)
        points.append({
            'exam': ex.display_name, 'exam_number': ex.exam_number, 'score': mine,
            'cohort_mean': round(m, 1) if m is not None else None,
            'cohort_size': len(scores),
            'z': round((mine - m) / sd, 2) if sd else None,
            'percentile': round(sum(1 for s in scores if s <= mine) / len(scores) * 100) if scores else None,
        })
    if not points:
        return None
    zs = [p['z'] for p in points if p['z'] is not None]
    return {'points': points, 'latest': points[-1],
            'z_trend': round(zs[-1] - zs[0], 2) if len(zs) >= 2 else None}


def _strength(r):
    if r is None:
        return 'insufficient data'
    a = abs(r)
    band = ('negligible' if a < 0.2 else 'weak' if a < 0.4 else
            'moderate' if a < 0.6 else 'strong' if a < 0.8 else 'very strong')
    if a < 0.2:
        return band
    return f'{band} {"positive" if r > 0 else "negative"}'


# --------------------------------------------------------------------------- #
# Subject-level JAMB performance (captured but previously unused)
# --------------------------------------------------------------------------- #
def jamb_subject_breakdown(branch_id=None, exam_year=None):
    """Per-subject average JAMB score across the school. Returns a list sorted by
    average descending."""
    from models import JAMBResult, Student
    q = JAMBResult.query
    if exam_year:
        q = q.filter(JAMBResult.exam_year == exam_year)
    if branch_id is not None:
        q = q.join(Student).filter(Student.branch_id == branch_id)
    agg = {}
    for r in q.all():
        for subj, sc in ((r.subject1, r.subject1_score), (r.subject2, r.subject2_score),
                         (r.subject3, r.subject3_score), (r.subject4, r.subject4_score)):
            if subj and sc is not None:
                agg.setdefault(subj, []).append(sc)
    out = [{'subject': s, 'count': len(v), 'average': round(sum(v) / len(v), 1),
            'max': max(v), 'min': min(v)} for s, v in agg.items()]
    out.sort(key=lambda x: x['average'], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Mock WAEC subject value-added (first sitting vs latest)
# --------------------------------------------------------------------------- #
def mock_waec_subject_gains(session_id):
    """Average score in the first vs the latest Mock WAEC sitting per subject, and
    the gain — which subjects are improving across the term and which are stuck.
    Returns {} when there are fewer than two sittings."""
    from models.mock_waec import MockWAECExam, MockWAECResult
    exams = (MockWAECExam.query.filter_by(session_id=session_id)
             .order_by(MockWAECExam.exam_number).all())
    if len(exams) < 2:
        return {}
    first, last = exams[0], exams[-1]

    def avgs(exam_id):
        d = {}
        for r in MockWAECResult.query.filter_by(mock_exam_id=exam_id).all():
            if r.score is not None:
                d.setdefault(r.subject, []).append(r.score)
        return {s: sum(v) / len(v) for s, v in d.items()}

    a0, a1 = avgs(first.id), avgs(last.id)
    subjects = [{'subject': s, 'first': round(a0[s], 1), 'latest': round(a1[s], 1),
                 'gain': round(a1[s] - a0[s], 1)} for s in (set(a0) & set(a1))]
    subjects.sort(key=lambda x: x['gain'])     # weakest movers first
    return {'first_exam': first.display_name, 'latest_exam': last.display_name,
            'subjects': subjects}


# --------------------------------------------------------------------------- #
# Attendance <-> results correlation
# --------------------------------------------------------------------------- #
def _attendance_rate(student):
    """Student's attendance rate (%) across all marked days, or None if none."""
    from models import Attendance, StudentEnrollment
    rows = (Attendance.query
            .join(StudentEnrollment, Attendance.enrollment_id == StudentEnrollment.id)
            .filter(StudentEnrollment.student_id == student.id).all())
    if not rows:
        return None
    present = sum(int(bool(r.morning_present)) + int(bool(r.afternoon_present)) for r in rows)
    return present / (2 * len(rows)) * 100


def _perf_metric(student, metric):
    from models.mock_waec import PASS_GRADES as W_PASS
    if metric == 'jamb':
        scores = [r.total_score for r in student.jamb_results.all() if r.total_score is not None]
        return max(scores) if scores else None
    # waec credits (best year)
    by_year = {}
    for r in student.waec_results.all():
        by_year.setdefault(r.exam_year, {})[r.subject] = r.grade
    if not by_year:
        return None
    return max(len({s for s, g in subs.items() if g in W_PASS}) for subs in by_year.values())


def attendance_performance_correlation(students, metric='jamb'):
    """Pearson correlation between attendance rate and exam performance (best
    JAMB score, or best-year WAEC credit count). Returns the coefficient, sample
    size and a plain-language strength label."""
    xs, ys = [], []
    for s in students:
        rate = _attendance_rate(s)
        if rate is None:
            continue
        perf = _perf_metric(s, metric)
        if perf is None:
            continue
        xs.append(rate)
        ys.append(perf)
    r = _pearson(xs, ys)
    return {'n': len(xs), 'metric': metric,
            'coefficient': round(r, 2) if r is not None else None,
            'strength': _strength(r)}
