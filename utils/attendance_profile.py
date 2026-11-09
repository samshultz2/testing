"""Student attendance profile — aggregates one student's attendance across every
term they've been enrolled, for the definitive per-student profile page.

Nothing here touches the marking write path; it only reads Attendance rows and
derives status. The model stores morning/afternoon booleans (no late/excused
column), so status is *derived*:

    both sessions present   -> 'present'
    exactly one present     -> 'late'      (arrived late / left early)
    neither / no record     -> 'absent'    (on a school day)
"""
from datetime import timedelta

from models import (db, Student, StudentEnrollment, ClassArmAssignment, Term,
                    AcademicSession, Week, Holiday, Attendance)
from utils import timeutil


def _term_school_days(term_id, up_to=None):
    """Ordered list of school weekdays (Mon–Fri minus holidays) in a term.

    Terms are set up with every week of the calendar already created (see
    academics.generate_weeks), including ones far in the future — so the
    unfiltered list mixes days that have actually happened with days that
    haven't. A day with no register yet isn't an absence, it just hasn't
    occurred, so every percentage/day-count consumer needs the bounded list:
    this defaults to capping at today. Pass ``up_to=False`` for the full
    term (past AND future) — only a calendar/preview display should ever
    want that."""
    weeks = Week.query.filter_by(term_id=term_id).order_by(Week.week_number).all()
    if not weeks:
        return []
    holiday_dates = {h.date for h in Holiday.query.filter_by(term_id=term_id).all()}
    days = []
    for w in weeks:
        d = w.start_date
        while d <= w.end_date:
            if d.weekday() < 5 and d not in holiday_dates:
                days.append(d)
            d += timedelta(days=1)
    if up_to is not False:
        cutoff = up_to or timeutil.today()
        days = [d for d in days if d <= cutoff]
    return days


def marked_class_ids(term_id, caa_ids):
    """The classes (of ``caa_ids``) that have marked attendance at least once in
    the term. A class whose register has never been taken has no data — its
    students aren't 0%, they're unknown — so every analytics / alert /
    intervention consumer leaves those classes out rather than counting them
    as absent all term."""
    caa_ids = [c for c in (caa_ids or []) if c is not None]
    if not caa_ids or not term_id:
        return set()
    week_ids = [w.id for w in Week.query.filter_by(term_id=term_id).all()]
    if not week_ids:
        return set()
    rows = (db.session.query(StudentEnrollment.class_arm_assignment_id)
            .join(Attendance, Attendance.enrollment_id == StudentEnrollment.id)
            .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids),
                    Attendance.week_id.in_(week_ids))
            .distinct().all())
    return {r[0] for r in rows}


def _status_of(rec):
    if rec is None:
        return 'absent'          # school day with no register row for this student
    m, a = bool(rec.morning_present), bool(rec.afternoon_present)
    if m and a:
        return 'present'
    if m or a:
        return 'late'
    return 'absent'


def warning_threshold():
    from models import SchoolSettings
    try:
        return float(SchoolSettings.get('attendance_warning_threshold', 75) or 75)
    except (ValueError, TypeError):
        return 75.0


def _term_stats(enrollment, term_id, want_calendar=False):
    """Per-term attendance for one enrollment. Percentage and day counts only
    ever look at school days up to today (via _term_school_days' default) —
    a day that hasn't happened yet has no register row, and counting it as
    absent would understate attendance for any term still in progress. The
    optional calendar (for display) still spans the whole term including
    future days — they simply show as 'unmarked', same as an untaken
    register, since there's nothing to distinguish them by yet."""
    school_days = _term_school_days(term_id)
    if not school_days:
        return None
    recs = {r.date: r for r in Attendance.query.filter(
        Attendance.enrollment_id == enrollment.id,
        Attendance.date.in_(school_days)).all()}
    total_opened = len(school_days) * 2
    present_sessions = full_days = late_days = absent_days = 0
    for d in school_days:
        rec = recs.get(d)
        st = _status_of(rec)
        present_sessions += (int(bool(rec.morning_present)) + int(bool(rec.afternoon_present))) if rec else 0
        if st == 'present':
            full_days += 1
        elif st == 'late':
            late_days += 1
        else:
            absent_days += 1
    pct = round(present_sessions / total_opened * 100, 2) if total_opened else 0.0
    out = {'present_sessions': present_sessions, 'total_opened': total_opened,
           'absent_sessions': total_opened - present_sessions,
           'school_days': len(school_days), 'full_days': full_days,
           'late_days': late_days, 'absent_days': absent_days, 'percentage': pct}
    if want_calendar:
        full_term_days = _term_school_days(term_id, up_to=False)
        calendar = []
        for d in full_term_days:
            rec = recs.get(d)
            st = _status_of(rec)
            calendar.append({'date': d.isoformat(), 'status': ('unmarked' if rec is None else st),
                             'm': bool(rec.morning_present) if rec else None,
                             'a': bool(rec.afternoon_present) if rec else None})
        out['calendar'] = calendar
    return out


def student_term_percentage(student_id, term_id):
    """A single student's attendance % for one term (None if not enrolled / no
    school days). Used by the intervention tracker to compare against a baseline."""
    if not term_id:
        return None
    enr = (StudentEnrollment.query
           .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
           .filter(StudentEnrollment.student_id == student_id,
                   ClassArmAssignment.term_id == term_id).first())
    if enr and enr.class_arm_assignment_id not in marked_class_ids(term_id, [enr.class_arm_assignment_id]):
        return None   # class register never taken this term — no data, not 0%
    if not enr:
        return None
    stats = _term_stats(enr, term_id)
    return stats['percentage'] if stats else None


def bulk_term_percentages(student_ids, term_id):
    """Attendance % for many students in one term, batched — the intervention
    dashboard's equivalent of calling student_term_percentage() per student,
    without the N+1 (one shared school-days lookup, one enrollment query and
    one Attendance query for the whole cohort instead of 2-4 queries each)."""
    if not student_ids or not term_id:
        return {}
    school_days = _term_school_days(term_id)
    if not school_days:
        return {}
    total_opened = len(school_days) * 2
    enrollments = (StudentEnrollment.query
                   .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                   .filter(StudentEnrollment.student_id.in_(student_ids),
                           ClassArmAssignment.term_id == term_id).all())
    enr_by_student = {}
    for e in enrollments:
        enr_by_student.setdefault(e.student_id, e)   # first match, same as student_term_percentage()'s .first()
    # Students whose class has never marked attendance this term have no %.
    marked = marked_class_ids(term_id, list({e.class_arm_assignment_id for e in enr_by_student.values()}))
    enr_by_student = {sid: e for sid, e in enr_by_student.items() if e.class_arm_assignment_id in marked}
    present = {e.id: 0 for e in enr_by_student.values()}
    if present:
        for a in Attendance.query.filter(Attendance.enrollment_id.in_(list(present)),
                                         Attendance.date.in_(school_days)).all():
            if a.enrollment_id in present:
                present[a.enrollment_id] += (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
    return {sid: round(present[e.id] / total_opened * 100, 2)
            for sid, e in enr_by_student.items()}


def build_student_profile(student_id, focus_term_id=None):
    """The full cross-term attendance profile for a student, or None if unknown.
    ``focus_term_id`` selects which term's calendar is expanded (default: latest)."""
    student = db.session.get(Student, student_id)
    if not student:
        return None
    from sqlalchemy.orm import contains_eager, joinedload
    enrollments = (StudentEnrollment.query
                   .filter_by(student_id=student_id)
                   .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                   .options(
                       contains_eager(StudentEnrollment.class_arm_assignment)
                       .joinedload(ClassArmAssignment.term).joinedload(Term.session),
                       contains_eager(StudentEnrollment.class_arm_assignment)
                       .joinedload(ClassArmAssignment.school_class),
                       contains_eager(StudentEnrollment.class_arm_assignment)
                       .joinedload(ClassArmAssignment.arm))
                   .all())
    # Order by term (session, term number) newest-first.
    def _term_key(e):
        t = e.class_arm_assignment.term if e.class_arm_assignment else None
        return (t.session_id or 0, t.term_number or 0) if t else (0, 0)
    enrollments.sort(key=_term_key, reverse=True)

    marked_by_term = {}
    for e in enrollments:
        if e.class_arm_assignment:
            marked_by_term.setdefault(e.class_arm_assignment.term_id, []).append(e.class_arm_assignment_id)
    marked = set()
    for tid, ids in marked_by_term.items():
        marked |= marked_class_ids(tid, ids)
    term_rows = []
    for e in enrollments:
        caa = e.class_arm_assignment
        term = caa.term if caa else None
        if not term:
            continue
        if caa.id not in marked:
            continue   # register never taken for this class/term — no data
        stats = _term_stats(e, term.id)
        if stats is None:
            continue
        term_rows.append({'enrollment_id': e.id, 'term_id': term.id,
                          'term': term.name, 'session': (term.session.name if term.session else ''),
                          'class': caa.display_name, **stats})

    # Overall aggregates across all terms.
    tot_open = sum(r['total_opened'] for r in term_rows)
    tot_present = sum(r['present_sessions'] for r in term_rows)
    overall_pct = round(tot_present / tot_open * 100, 2) if tot_open else 0.0
    thresh = warning_threshold()

    # Focus term: the requested one, else the latest with data.
    focus = None
    if term_rows:
        focus_row = next((r for r in term_rows if r['term_id'] == focus_term_id), term_rows[0])
        focus_enr = db.session.get(StudentEnrollment, focus_row['enrollment_id'])
        focus = _term_stats(focus_enr, focus_row['term_id'], want_calendar=True)
        focus.update({'term_id': focus_row['term_id'], 'term': focus_row['term'],
                      'class': focus_row['class']})

    # Trend: percentage per term, oldest→newest, for the sparkline.
    trend = [{'label': f"{r['term']}", 'percentage': r['percentage']} for r in reversed(term_rows)]

    return {
        'student': {'id': student.id, 'name': student.full_name,
                    'student_id': student.student_id, 'gender': student.gender or '',
                    'photo_url': getattr(student, 'photo_url', '') or ''},
        'overall': {'percentage': overall_pct, 'present_sessions': tot_present,
                    'total_opened': tot_open, 'absent_sessions': tot_open - tot_present,
                    'full_days': sum(r['full_days'] for r in term_rows),
                    'late_days': sum(r['late_days'] for r in term_rows),
                    'absent_days': sum(r['absent_days'] for r in term_rows),
                    'terms': len(term_rows)},
        'threshold': thresh,
        'warning': bool(term_rows) and overall_pct < thresh,
        'terms': term_rows,
        'focus': focus,
        'trend': trend,
    }
