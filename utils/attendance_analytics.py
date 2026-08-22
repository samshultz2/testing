"""Attendance analytics — school/branch/class insights for a term, computed in a
single batched pass and cached (per-tenant AnalyticsCache, short TTL, invalidated
when marks change). Read-only; never touches the marking write path.

Derived status matches the profile: both sessions present = present, one = late,
neither/none on a school day = absent.
"""
from datetime import timedelta

from models import (db, Attendance, StudentEnrollment, ClassArmAssignment, Term,
                    Week, Holiday, Branch)
from utils.attendance_profile import _term_school_days, warning_threshold

CRITICAL_PCT = 50.0
_TTL = 900   # 15 minutes


def _cache_key(term_id, caa_ids):
    sig = 'all' if caa_ids is None else str(hash(tuple(sorted(caa_ids))) & 0xffffffff)
    return f'att_analytics|{term_id}|{sig}'


def invalidate_term(term_id):
    """Drop any cached analytics for a term (called after marks change)."""
    from models.analytics_models import AnalyticsCache
    try:
        AnalyticsCache.query.filter(
            AnalyticsCache.cache_key.like(f'att_analytics|{term_id}|%')).delete(
            synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _pct(present, opened):
    return round(present / opened * 100, 1) if opened else 0.0


def _student_pct_map(caa_ids, week_ids, school_days_count):
    """{enrollment_id: (present_sessions, student_id, caa_id)} for a set of classes."""
    enrollments = (StudentEnrollment.query
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids or [-1]),
                           StudentEnrollment.is_active == True,  # noqa: E712
                           StudentEnrollment.student.has(is_active=True))  # exclude departed
                   .all())
    present = {e.id: 0 for e in enrollments}
    if week_ids:
        for a in Attendance.query.filter(
                Attendance.enrollment_id.in_(list(present) or [-1]),
                Attendance.week_id.in_(week_ids)).all():
            if a.enrollment_id in present:
                present[a.enrollment_id] += (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
    opened = school_days_count * 2
    return enrollments, present, opened


def _prev_term(term):
    """The term immediately before ``term`` (same session earlier number, else the
    latest term of the previous session)."""
    if not term:
        return None
    q = (Term.query.filter(Term.session_id == term.session_id,
                           Term.term_number < (term.term_number or 0))
         .order_by(Term.term_number.desc()))
    prev = q.first()
    if prev:
        return prev
    # fall back to the last term of the previous session
    from models import AcademicSession
    sess = db.session.get(AcademicSession, term.session_id)
    if not sess:
        return None
    prev_sessions = (AcademicSession.query.filter(AcademicSession.id < sess.id)
                     .order_by(AcademicSession.id.desc()).first())
    if not prev_sessions:
        return None
    return (Term.query.filter_by(session_id=prev_sessions.id)
            .order_by(Term.term_number.desc()).first())


def build(term, accessible_caas, *, is_central=False, use_cache=True):
    """Full analytics payload for a term over the classes the viewer may see.
    ``accessible_caas`` is the list of ClassArmAssignment the user can view."""
    from models.analytics_models import AnalyticsCache
    caa_ids = [c.id for c in accessible_caas]
    key = _cache_key(term.id, caa_ids)
    if use_cache:
        hit = AnalyticsCache.get(key)
        if hit is not None:
            return hit

    weeks = Week.query.filter_by(term_id=term.id).order_by(Week.week_number).all()
    week_ids = [w.id for w in weeks]
    school_days = _term_school_days(term.id)
    n_days = len(school_days)

    enrollments, present, opened_per_student = _student_pct_map(caa_ids, week_ids, n_days)
    caa_by_id = {c.id: c for c in accessible_caas}

    # Per-class and per-student aggregation.
    class_present, class_students = {}, {}
    for e in enrollments:
        class_students[e.class_arm_assignment_id] = class_students.get(e.class_arm_assignment_id, 0) + 1
        class_present[e.class_arm_assignment_id] = class_present.get(e.class_arm_assignment_id, 0) + present.get(e.id, 0)

    n_students = len(enrollments)
    total_present = sum(present.values())
    total_opened = n_students * opened_per_student
    overall = _pct(total_present, total_opened)

    # Distribution buckets by each student's term %.
    dist = {'excellent': 0, 'good': 0, 'fair': 0, 'poor': 0}
    chronic = []
    thresh = warning_threshold()
    id_to_enr = {e.id: e for e in enrollments}
    for eid, pres in present.items():
        pct = _pct(pres, opened_per_student)
        if pct >= 90:
            dist['excellent'] += 1
        elif pct >= 75:
            dist['good'] += 1
        elif pct >= 50:
            dist['fair'] += 1
        else:
            dist['poor'] += 1
        if pct < CRITICAL_PCT:
            e = id_to_enr[eid]
            chronic.append({'id': e.student.id, 'name': e.student.full_name,
                            'student_id': e.student.student_id,
                            'class': caa_by_id[e.class_arm_assignment_id].display_name,
                            'percentage': pct})
    chronic.sort(key=lambda x: x['percentage'])

    # Weekly trend (per-week % across all students).
    week_days = {}
    holiday_dates = {h.date for h in Holiday.query.filter_by(term_id=term.id).all()}
    for w in weeks:
        d, cnt = w.start_date, 0
        while d <= w.end_date:
            if d.weekday() < 5 and d not in holiday_dates:
                cnt += 1
            d += timedelta(days=1)
        week_days[w.id] = cnt
    week_present = {w.id: 0 for w in weeks}
    weekday_present = {i: 0 for i in range(5)}
    weekday_days = {i: 0 for i in range(5)}
    for d in school_days:
        weekday_days[d.weekday()] += 1
    if week_ids and enrollments:
        for a in Attendance.query.filter(
                Attendance.enrollment_id.in_([e.id for e in enrollments]),
                Attendance.week_id.in_(week_ids)).all():
            s = (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
            if a.week_id in week_present:
                week_present[a.week_id] += s
            if a.date.weekday() < 5:
                weekday_present[a.date.weekday()] += s

    trend = [{'label': f'W{w.week_number}',
              'percentage': _pct(week_present[w.id], week_days[w.id] * 2 * n_students)}
             for w in weeks if week_days[w.id] > 0]

    DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    heatmap = [{'label': DOW[i],
                'percentage': _pct(weekday_present[i], weekday_days[i] * 2 * n_students)}
               for i in range(5)]

    # Class ranking.
    class_rank = []
    for cid, students in class_students.items():
        op = students * opened_per_student
        class_rank.append({'class': caa_by_id[cid].display_name,
                           'students': students, 'percentage': _pct(class_present.get(cid, 0), op),
                           'caa_id': cid})
    class_rank.sort(key=lambda x: -x['percentage'])

    # Branch ranking (central users only — needs multiple branches).
    branch_rank = []
    if is_central:
        bname = {b.id: b.name for b in Branch.query.all()}
        bp, bo = {}, {}
        for cid, students in class_students.items():
            bid = caa_by_id[cid].branch_id
            bp[bid] = bp.get(bid, 0) + class_present.get(cid, 0)
            bo[bid] = bo.get(bid, 0) + students * opened_per_student
        branch_rank = [{'branch': bname.get(bid, 'Unassigned'), 'percentage': _pct(bp[bid], bo[bid])}
                       for bid in bp]
        branch_rank.sort(key=lambda x: -x['percentage'])

    # Most improved vs the previous term (students enrolled in both).
    improved = []
    prev = _prev_term(term)
    if prev and enrollments:
        prev_weeks = Week.query.filter_by(term_id=prev.id).all()
        prev_week_ids = [w.id for w in prev_weeks]
        prev_days = len(_term_school_days(prev.id))
        student_ids = [e.student_id for e in enrollments]
        prev_enr = (StudentEnrollment.query
                    .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                    .filter(ClassArmAssignment.term_id == prev.id,
                            StudentEnrollment.student_id.in_(student_ids)).all())
        prev_by_student = {}
        if prev_enr and prev_week_ids and prev_days:
            prev_present = {e.id: 0 for e in prev_enr}
            for a in Attendance.query.filter(
                    Attendance.enrollment_id.in_(list(prev_present)),
                    Attendance.week_id.in_(prev_week_ids)).all():
                if a.enrollment_id in prev_present:
                    prev_present[a.enrollment_id] += (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
            prev_open = prev_days * 2
            for e in prev_enr:
                prev_by_student[e.student_id] = _pct(prev_present.get(e.id, 0), prev_open)
        for e in enrollments:
            if e.student_id in prev_by_student:
                cur = _pct(present.get(e.id, 0), opened_per_student)
                delta = round(cur - prev_by_student[e.student_id], 1)
                if delta > 0:
                    improved.append({'id': e.student.id, 'name': e.student.full_name,
                                     'class': caa_by_id[e.class_arm_assignment_id].display_name,
                                     'from': prev_by_student[e.student_id], 'to': cur, 'delta': delta})
        improved.sort(key=lambda x: -x['delta'])
        improved = improved[:10]

    payload = {
        'term': {'id': term.id, 'name': term.name},
        'kpis': {'overall': overall, 'students': n_students, 'classes': len(class_students),
                 'present_sessions': total_present, 'total_opened': total_opened,
                 'chronic': len(chronic),
                 'best_class': class_rank[0]['class'] if class_rank else '—',
                 'worst_class': class_rank[-1]['class'] if class_rank else '—',
                 'school_days': n_days},
        'threshold': thresh, 'critical': CRITICAL_PCT,
        'trend': trend, 'heatmap': heatmap, 'distribution': dist,
        'class_rank': class_rank, 'branch_rank': branch_rank,
        'chronic_list': chronic[:20], 'most_improved': improved,
        'prev_term': (prev.name if prev else None),
    }
    if use_cache:
        AnalyticsCache.set(key, payload, ttl_seconds=_TTL)
    return payload
