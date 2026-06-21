"""Persistent-absence alerts.

Bell admins when a student is absent several consecutive school days in a row.
Internal notifications only — student records are phone-first, so there's no
parent email to send here. Best-effort: never breaks the attendance save that
triggers it.
"""
import logging

from models import db, Attendance, StudentEnrollment

_log = logging.getLogger('posyhub.attendance')


def _consecutive_absences(enrollment_id):
    """Most-recent run of consecutive full-day absences for an enrollment. A day
    counts as absent only when neither session was present."""
    rows = (Attendance.query
            .filter_by(enrollment_id=enrollment_id)
            .order_by(Attendance.date.desc())
            .limit(60).all())
    streak = 0
    for r in rows:
        if r.morning_present or r.afternoon_present:
            break
        streak += 1
    return streak


def check_absence_alerts(enrollment_ids, threshold=None):
    """Bell admins for any given enrollment whose latest attendance shows at least
    ``threshold`` consecutive absences. De-duplicated: skips a student who already
    has an unread attendance alert, so admins aren't spammed daily. Returns the
    number of alerts created."""
    from config import Config
    if threshold is None:
        threshold = int(getattr(Config, 'ABSENCE_ALERT_DAYS', 3) or 0)
    if threshold <= 0 or not enrollment_ids:
        return 0

    from models import Notification
    from utils.notify import notify_admins

    created = 0
    for eid in set(enrollment_ids):
        try:
            streak = _consecutive_absences(eid)
            if streak < threshold:
                continue
            enr = db.session.get(StudentEnrollment, eid)
            student = enr.student if enr else None
            if not student:
                continue
            title = f'Attendance alert: {student.full_name}'
            # Don't re-alert while an earlier alert for this student is unread.
            if Notification.query.filter_by(role='admin', is_read=False,
                                            title=title).first():
                continue
            if notify_admins(title,
                             f'{student.full_name} has been absent {streak} school '
                             f'days in a row.', category='attendance'):
                created += 1
        except Exception as exc:
            _log.warning('absence alert check failed for enrollment %s: %s', eid, exc)
    return created
