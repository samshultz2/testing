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


def _term_school_days(term_id):
    """Ordered list of school weekdays (Mon–Fri minus holidays) in a term."""
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
    return days


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
    """Per-term attendance for one enrollment."""
    school_days = _term_school_days(term_id)
    if not school_days:
        return None
    recs = {r.date: r for r in Attendance.query.filter(
        Attendance.enrollment_id == enrollment.id,
        Attendance.date.in_(school_days)).all()}
    total_opened = len(school_days) * 2
    present_sessions = full_days = late_days = absent_days = 0
    calendar = []
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
        if want_calendar:
            calendar.append({'date': d.isoformat(), 'status': ('unmarked' if rec is None else st),
                             'm': bool(rec.morning_present) if rec else None,
                             'a': bool(rec.afternoon_present) if rec else None})
    pct = round(present_sessions / total_opened * 100, 1) if total_opened else 0.0
    out = {'present_sessions': present_sessions, 'total_opened': total_opened,
           'absent_sessions': total_opened - present_sessions,
           'school_days': len(school_days), 'full_days': full_days,
           'late_days': late_days, 'absent_days': absent_days, 'percentage': pct}
    if want_calendar:
        out['calendar'] = calendar
    return out


def build_student_profile(student_id, focus_term_id=None):
    """The full cross-term attendance profile for a student, or None if unknown.
    ``focus_term_id`` selects which term's calendar is expanded (default: latest)."""
    student = db.session.get(Student, student_id)
    if not student:
        return None
    enrollments = (StudentEnrollment.query
                   .filter_by(student_id=student_id)
                   .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                   .all())
    # Order by term (session, term number) newest-first.
    def _term_key(e):
        t = e.class_arm_assignment.term if e.class_arm_assignment else None
        return (t.session_id or 0, t.term_number or 0) if t else (0, 0)
    enrollments.sort(key=_term_key, reverse=True)

    term_rows = []
    for e in enrollments:
        caa = e.class_arm_assignment
        term = caa.term if caa else None
        if not term:
            continue
        stats = _term_stats(e, term.id)
        if stats is None:
            continue
        term_rows.append({'enrollment_id': e.id, 'term_id': term.id,
                          'term': term.name, 'session': (term.session.name if term.session else ''),
                          'class': caa.display_name, **stats})

    # Overall aggregates across all terms.
    tot_open = sum(r['total_opened'] for r in term_rows)
    tot_present = sum(r['present_sessions'] for r in term_rows)
    overall_pct = round(tot_present / tot_open * 100, 1) if tot_open else 0.0
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
