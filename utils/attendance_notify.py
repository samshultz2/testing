"""Attendance → parent notifications.

Reuses the Communication module (``comms.build_campaign``) — this never sends
messages itself, it only assembles a reviewable draft campaign to the parents of
the relevant students. Two triggers:

  * absentees on a given day (both sessions absent), and
  * students below the term attendance warning threshold.

Each is gated by an entry in the Automation Center so schools opt in.
"""
from datetime import timedelta

from models import (db, Attendance, StudentEnrollment, ClassArmAssignment, Week,
                    Holiday, MessageRecipient, Message)

ABSENT_TITLE = 'Attendance: absence notice'
LOW_TITLE = 'Attendance: low attendance notice'

ABSENT_BODY = ('Dear {parent}, our records show {student} was absent from school '
               'today. Please contact the school if this is unexpected. — {school}')
LOW_BODY = ('Dear {parent}, {student}\'s attendance this term has fallen below the '
            'expected level. Please help ensure regular attendance. — {school}')


def default_channel():
    from models import SchoolSettings
    ch = (SchoolSettings.get('att_notify_channel', 'SMS') or 'SMS').strip()
    return 'Email' if ch.lower() == 'email' else 'SMS'


def absentee_student_ids(caa_ids, target_date):
    """Students in the given classes marked absent for BOTH sessions on a date."""
    if not caa_ids:
        return []
    rows = (Attendance.query
            .join(StudentEnrollment, Attendance.enrollment_id == StudentEnrollment.id)
            .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids),
                    StudentEnrollment.is_active == True,          # noqa: E712
                    StudentEnrollment.student.has(is_active=True),  # exclude departed
                    Attendance.date == target_date)
            .all())
    ids = []
    for a in rows:
        if not a.morning_present and not a.afternoon_present:
            en = db.session.get(StudentEnrollment, a.enrollment_id)
            if en:
                ids.append(en.student_id)
    return sorted(set(ids))


def _low_attendance_student_ids(term, caa_ids, threshold):
    """Students in the classes below ``threshold`` % for the term."""
    from utils.attendance_profile import _term_school_days
    if not caa_ids:
        return []
    school_days = _term_school_days(term.id)
    total_opened = len(school_days) * 2
    if not total_opened:
        return []
    week_ids = [w.id for w in Week.query.filter_by(term_id=term.id).all()]
    enrollments = (StudentEnrollment.query
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids),
                           StudentEnrollment.is_active == True,   # noqa: E712
                           StudentEnrollment.student.has(is_active=True))  # exclude departed
                   .all())
    present = {e.id: 0 for e in enrollments}
    if week_ids:
        for a in Attendance.query.filter(Attendance.enrollment_id.in_(list(present) or [-1]),
                                         Attendance.week_id.in_(week_ids)).all():
            if a.enrollment_id in present:
                present[a.enrollment_id] += (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
    out = []
    for e in enrollments:
        pct = present.get(e.id, 0) / total_opened * 100
        if pct < threshold:
            out.append(e.student_id)
    return sorted(set(out))


def _draft(body, title, term, student_ids, channel, created_by):
    if not student_ids:
        return None
    from utils import comms
    return comms.build_campaign(
        body, channel=channel or default_channel(), term=term, title=title,
        spec={'to': 'parents', 'audience': 'students', 'student_ids': student_ids},
        created_by=created_by or 'Attendance')


def draft_absentee_notice(term, target_date, caa_ids, *, channel=None, created_by=None):
    """Draft a parent notice for students absent on ``target_date``. Returns the
    Message (or None if nobody absent / no parent reachable)."""
    return _draft(ABSENT_BODY, ABSENT_TITLE, term,
                  absentee_student_ids(caa_ids, target_date), channel, created_by)


def draft_low_attendance_notice(term, caa_ids, threshold, *, channel=None, created_by=None):
    return _draft(LOW_BODY, LOW_TITLE, term,
                  _low_attendance_student_ids(term, caa_ids, threshold), channel, created_by)


def student_notification_history(student_id, limit=20):
    """Attendance-related messages whose recipients included this student, newest
    first — for the notification-history section of the profile."""
    rows = (db.session.query(Message, MessageRecipient)
            .join(MessageRecipient, MessageRecipient.message_id == Message.id)
            .filter(MessageRecipient.student_id == student_id,
                    Message.title.in_([ABSENT_TITLE, LOW_TITLE]))
            .order_by(Message.created_at.desc())
            .limit(limit).all())
    out = []
    for msg, rec in rows:
        out.append({'title': msg.title, 'channel': msg.channel,
                    'date': msg.created_at.strftime('%d %b %Y') if msg.created_at else '',
                    'status': rec.status or msg.status,
                    'to': rec.parent_name or '', 'message_status': msg.status})
    return out
