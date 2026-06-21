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
    from models.mock_jamb import MockJAMBExam, MockJAMBResult
    # Only the sittings this student actually sat — don't load cohorts for exams
    # that can't contribute a point.
    sat_ids = {r.mock_exam_id for r in
               MockJAMBResult.query.filter_by(student_id=student_id).all()}
    if not sat_ids:
        return None
    q = MockJAMBExam.query.filter(MockJAMBExam.id.in_(sat_ids))
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
def attendance_performance_correlation(students, metric='jamb'):
    """Pearson correlation between attendance rate and exam performance (best
    JAMB score, or best-year WAEC credit count). Returns the coefficient, sample
    size and a plain-language strength label.

    Batched: a fixed two queries (attendance + the chosen result table) over the
    whole cohort, rather than per-student lookups."""
    from collections import defaultdict
    from models import db, Attendance, StudentEnrollment, JAMBResult, WAECResult
    from models.mock_waec import PASS_GRADES as W_PASS

    ids = [s.id for s in students]
    if not ids:
        return {'n': 0, 'metric': metric, 'coefficient': None, 'strength': _strength(None)}

    # Attendance rate per student — one query for the whole cohort.
    present, marked = defaultdict(int), defaultdict(int)
    for sid, am, pm in (db.session.query(
            StudentEnrollment.student_id, Attendance.morning_present, Attendance.afternoon_present)
            .join(Attendance, Attendance.enrollment_id == StudentEnrollment.id)
            .filter(StudentEnrollment.student_id.in_(ids)).all()):
        marked[sid] += 1
        present[sid] += int(bool(am)) + int(bool(pm))

    # Performance per student — one query.
    perf = {}
    if metric == 'jamb':
        for sid, score in (db.session.query(JAMBResult.student_id, JAMBResult.total_score)
                           .filter(JAMBResult.student_id.in_(ids),
                                   JAMBResult.total_score.isnot(None)).all()):
            perf[sid] = max(perf.get(sid, score), score)
    else:
        by_year = defaultdict(lambda: defaultdict(set))      # sid -> year -> credited subjects
        for sid, year, subj, grade in (db.session.query(
                WAECResult.student_id, WAECResult.exam_year, WAECResult.subject, WAECResult.grade)
                .filter(WAECResult.student_id.in_(ids)).all()):
            if grade in W_PASS:
                by_year[sid][year].add(subj)
        for sid, years in by_year.items():
            perf[sid] = max(len(s) for s in years.values())

    xs, ys = [], []
    for sid in ids:
        if marked[sid] == 0 or sid not in perf:
            continue
        xs.append(present[sid] / (2 * marked[sid]) * 100)
        ys.append(perf[sid])
    r = _pearson(xs, ys)
    return {'n': len(xs), 'metric': metric,
            'coefficient': round(r, 2) if r is not None else None,
            'strength': _strength(r)}
