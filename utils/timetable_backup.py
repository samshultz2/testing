"""Snapshot / restore helpers for the per-class timetables (ClassTimetable).

A backup is a JSON snapshot of every ClassTimetable entry for a term, stored in
``timetable_backups``. Applying a generated batch (or restoring) takes a snapshot
first, so an in-use timetable can always be recovered.
"""
import json

from flask import session

from models import db, ClassTimetable, ClassArmAssignment, TimetableBackup


def _caa_ids_for_term(term_id):
    return [c.id for c in ClassArmAssignment.query.filter_by(term_id=term_id).all()]


def snapshot_term(term_id, label, skip_if_empty=True):
    """Capture the current ClassTimetable for ``term_id`` into a TimetableBackup.

    Returns the backup (flushed, not committed) or ``None`` when there is nothing
    to back up and ``skip_if_empty`` is set.
    """
    caa_ids = _caa_ids_for_term(term_id)
    entries = (ClassTimetable.query
               .filter(ClassTimetable.class_arm_assignment_id.in_(caa_ids or [-1]))
               .all())
    if skip_if_empty and not entries:
        return None
    data = [{'caa_id': e.class_arm_assignment_id, 'slot_id': e.slot_id,
             'day_of_week': e.day_of_week, 'subject_id': e.subject_id,
             'teacher_name': e.teacher_name, 'room': e.room,
             'is_active': e.is_active} for e in entries]
    backup = TimetableBackup(term_id=term_id, label=label[:200],
                             entry_count=len(data), data=json.dumps(data),
                             created_by_id=session.get('user_id'))
    db.session.add(backup)
    db.session.flush()
    return backup


def restore_backup(backup):
    """Restore a snapshot: replace current entries for the classes it covers with
    the saved ones. Returns the number of entries restored."""
    data = json.loads(backup.data or '[]')
    caa_ids = sorted({d['caa_id'] for d in data})
    if caa_ids:
        (ClassTimetable.query
         .filter(ClassTimetable.class_arm_assignment_id.in_(caa_ids))
         .delete(synchronize_session=False))
    for d in data:
        db.session.add(ClassTimetable(
            class_arm_assignment_id=d['caa_id'], slot_id=d['slot_id'],
            day_of_week=d['day_of_week'], subject_id=d.get('subject_id'),
            teacher_name=d.get('teacher_name'), room=d.get('room'),
            is_active=d.get('is_active', True)))
    return len(data)
