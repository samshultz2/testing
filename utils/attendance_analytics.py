"""Attendance analytics — school/branch/class insights for a term, computed in a
single batched pass and cached (per-tenant AnalyticsCache, short TTL, invalidated
when marks change). Read-only; never touches the marking write path.

Derived status matches the profile: both sessions present = present, one = late,
neither/none on a school day = absent.
"""
from datetime import timedelta

from models import (db, Attendance, StudentEnrollment, ClassArmAssignment, Term,
                    Week, Holiday, Branch)
from utils.attendance_profile import _term_school_days, warning_threshold, marked_class_ids
from utils import timeutil

CRITICAL_PCT = 50.0
_TTL = 900   # 15 minutes


def _cache_key(term_id, caa_ids):
    sig = 'all' if caa_ids is None else str(hash(tuple(sorted(caa_ids))) & 0xffffffff)
    return f'att_analytics|{term_id}|v2|{sig}'


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
    return round(present / opened * 100, 2) if opened else 0.0


def _present_by_enrollment(enrollment_ids, week_ids, school_days):
    """Present sessions per enrollment, counting only real school days.

    A register row on a weekend, a holiday or a day that hasn't happened yet
    isn't in the denominator (``school_days``), so counting it in the
    numerator pushed students past 100%. Duplicate rows for the same day
    are merged (a session counts once)."""
    present = {eid: 0 for eid in enrollment_ids}
    if not week_ids or not present:
        return present
    days = set(school_days)
    seen = {}
    for a in Attendance.query.filter(
            Attendance.enrollment_id.in_(list(present)),
            Attendance.week_id.in_(week_ids)).all():
        if a.enrollment_id not in present or a.date not in days:
            continue
        k = (a.enrollment_id, a.date)
        m, n = seen.get(k, (False, False))
        seen[k] = (m or bool(a.morning_present), n or bool(a.afternoon_present))
    for (eid, _d), (m, n) in seen.items():
        present[eid] += int(m) + int(n)
    return present


def _student_pct_map(caa_ids, week_ids, school_days):
    """(enrollments, {enrollment_id: present_sessions}, opened) for a set of classes."""
    enrollments = (StudentEnrollment.query
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids or [-1]),
                           StudentEnrollment.is_active == True,  # noqa: E712
                           StudentEnrollment.student.has(is_active=True))  # exclude departed
                   .all())
    present = _present_by_enrollment([e.id for e in enrollments], week_ids, school_days)
    opened = len(school_days) * 2
    return enrollments, present, opened


def _class_names(caas):
    """{caa_id: label}. Two arms that display the same (e.g. two 'SSS3 Gold'
    in different branches) get the branch — or a number — added so the
    rankings don't show what look like duplicate rows."""
    names = {c.id: c.display_name for c in caas}
    seen = {}
    for c in caas:
        seen.setdefault(names[c.id], []).append(c)
    dup = [grp for grp in seen.values() if len(grp) > 1]
    if dup:
        bname = {b.id: b.name for b in Branch.query.all()}
        for grp in dup:
            branches = {c.branch_id for c in grp}
            for i, c in enumerate(sorted(grp, key=lambda x: x.id), 1):
                base = names[c.id]
                names[c.id] = (f'{base} · {bname.get(c.branch_id, "Unassigned")}'
                               if len(branches) == len(grp) else f'{base} ({i})')
    return names


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

    # Only classes that have marked attendance at least once this term count —
    # an untaken register is "no data", not "everyone absent". The rest are
    # listed separately so the office can chase them.
    marked = marked_class_ids(term.id, caa_ids)
    unmarked = sorted((c for c in accessible_caas if c.id not in marked), key=lambda c: c.display_name)
    enrollments, present, opened_per_student = _student_pct_map(
        [cid for cid in caa_ids if cid in marked], week_ids, school_days)
    caa_by_id = {c.id: c for c in accessible_caas}
    cname = _class_names(accessible_caas)
    unmarked_rows = []
    if unmarked:
        counts = dict(db.session.query(StudentEnrollment.class_arm_assignment_id, db.func.count(StudentEnrollment.id))
                      .filter(StudentEnrollment.class_arm_assignment_id.in_([c.id for c in unmarked]),
                              StudentEnrollment.is_active == True)  # noqa: E712
                      .group_by(StudentEnrollment.class_arm_assignment_id).all())
        unmarked_rows = [{'class': cname[c.id], 'caa_id': c.id, 'students': counts.get(c.id, 0)}
                         for c in unmarked if counts.get(c.id, 0)]

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
                            'class': cname[e.class_arm_assignment_id],
                            'percentage': pct})
    chronic.sort(key=lambda x: x['percentage'])

    # Every student below the warning threshold (chronic + at risk), lowest first.
    below = []
    cls_below, cls_chronic = {}, {}
    for eid, pres in present.items():
        pct = _pct(pres, opened_per_student)
        if pct < thresh:
            e = id_to_enr[eid]
            cid = e.class_arm_assignment_id
            cls_below[cid] = cls_below.get(cid, 0) + 1
            if pct < CRITICAL_PCT:
                cls_chronic[cid] = cls_chronic.get(cid, 0) + 1
            below.append({'id': e.student.id, 'name': e.student.full_name,
                          'student_id': e.student.student_id, 'gender': e.student.gender,
                          'class': cname[cid], 'caa_id': cid, 'percentage': pct})
    below.sort(key=lambda x: (x['percentage'], x['name']))

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
    day_set = set(school_days)
    if week_ids and enrollments:
        for a in Attendance.query.filter(
                Attendance.enrollment_id.in_([e.id for e in enrollments]),
                Attendance.week_id.in_(week_ids)).all():
            if a.date not in day_set:
                continue
            s = (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
            if a.week_id in week_present:
                week_present[a.week_id] += s
            if a.date.weekday() < 5:
                weekday_present[a.date.weekday()] += s

    # Weeks are all pre-created for the whole term up front (generate_weeks),
    # so excluding ones that haven't started yet keeps this from padding the
    # trend with 0%-because-it-hasn't-happened-yet future weeks.
    today = timeutil.today()
    trend = [{'label': f'W{w.week_number}',
              'percentage': _pct(week_present[w.id], week_days[w.id] * 2 * n_students)}
             for w in weeks if week_days[w.id] > 0 and w.start_date <= today]

    DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    heatmap = [{'label': DOW[i],
                'percentage': _pct(weekday_present[i], weekday_days[i] * 2 * n_students)}
               for i in range(5)]

    # Class ranking.
    class_rank = []
    for cid, students in class_students.items():
        op = students * opened_per_student
        class_rank.append({'class': cname[cid],
                           'students': students, 'percentage': _pct(class_present.get(cid, 0), op),
                           'caa_id': cid, 'below': cls_below.get(cid, 0), 'chronic': cls_chronic.get(cid, 0)})
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

    # Change vs the previous term for the same students (same % the profile
    # shows: school days only, untaken registers left out).
    improved, declined = [], []
    prev_overall = None
    prev = _prev_term(term)
    if prev and enrollments:
        from utils.attendance_profile import bulk_term_percentages
        prev_by_student = bulk_term_percentages(list({e.student_id for e in enrollments}), prev.id)
        if prev_by_student:
            prev_overall = round(sum(prev_by_student.values()) / len(prev_by_student), 2)
        for e in enrollments:
            if e.student_id in prev_by_student:
                cur = _pct(present.get(e.id, 0), opened_per_student)
                delta = round(cur - prev_by_student[e.student_id], 2)
                row = {'id': e.student.id, 'name': e.student.full_name,
                       'class': cname[e.class_arm_assignment_id],
                       'from': prev_by_student[e.student_id], 'to': cur, 'delta': delta}
                if delta > 0:
                    improved.append(row)
                elif delta < 0:
                    declined.append(row)
        improved.sort(key=lambda x: -x['delta'])
        declined.sort(key=lambda x: x['delta'])
        improved, declined = improved[:15], declined[:15]

    payload = {
        'term': {'id': term.id, 'name': term.name},
        'kpis': {'overall': overall, 'students': n_students, 'classes': len(class_students),
                 'present_sessions': total_present, 'total_opened': total_opened,
                 'chronic': len(chronic), 'below_threshold': len(below),
                 'classes_unmarked': len(unmarked_rows), 'prev_overall': prev_overall,
                 'best_class': class_rank[0]['class'] if class_rank else '—',
                 'worst_class': class_rank[-1]['class'] if class_rank else '—',
                 'school_days': n_days},
        'threshold': thresh, 'critical': CRITICAL_PCT,
        'trend': trend, 'heatmap': heatmap, 'distribution': dist,
        'class_rank': class_rank, 'branch_rank': branch_rank,
        'chronic_list': chronic[:20], 'most_improved': improved, 'most_declined': declined,
        'below_list': below[:400],
        'unmarked_classes': unmarked_rows,
        'prev_term': (prev.name if prev else None),
    }
    if use_cache:
        AnalyticsCache.set(key, payload, ttl_seconds=_TTL)
    return payload
