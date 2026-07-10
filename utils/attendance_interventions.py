"""Attendance intervention workflow — open, follow up, resolve, and track whether
a struggling student's attendance recovers. Read/writes only the intervention
tables; never the attendance marking path."""
from datetime import datetime

from models import (db, AttendanceIntervention, InterventionNote, Student,
                    StudentEnrollment, ClassArmAssignment)
from utils.attendance_profile import student_term_percentage, warning_threshold

IMPROVE_DELTA = 5.0   # ≥ +5 pts vs baseline counts as "improving"


def _class_for(student_id, term_id):
    caa = (ClassArmAssignment.query
           .join(StudentEnrollment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
           .filter(StudentEnrollment.student_id == student_id,
                   ClassArmAssignment.term_id == term_id).first())
    return caa.display_name if caa else ''


def open_intervention(student_id, term, reason=None, opened_by=None):
    """Open an intervention, snapshotting the student's current term % as baseline.
    Idempotent per (student, term): returns the existing open one if present."""
    existing = (AttendanceIntervention.query
                .filter(AttendanceIntervention.student_id == student_id,
                        AttendanceIntervention.term_id == (term.id if term else None),
                        AttendanceIntervention.status.in_(['Open', 'In progress', 'Escalated']))
                .first())
    if existing:
        return existing, False
    baseline = student_term_percentage(student_id, term.id) if term else None
    iv = AttendanceIntervention(
        student_id=student_id, term_id=(term.id if term else None),
        reason=reason or 'Low attendance', status='Open',
        baseline_pct=baseline, opened_by=opened_by or 'Attendance')
    db.session.add(iv)
    db.session.commit()
    return iv, True


def add_note(intervention, *, kind='Note', body=None, next_action=None,
             next_date=None, author=None):
    note = InterventionNote(intervention_id=intervention.id, kind=kind, body=body,
                            next_action=next_action, next_date=next_date, author=author)
    # A logged follow-up moves an Open case to "In progress".
    if intervention.status == 'Open':
        intervention.status = 'In progress'
    db.session.add(note)
    db.session.commit()
    return note


def set_status(intervention, status, *, outcome=None):
    if status not in AttendanceIntervention.STATUSES:
        return False
    intervention.status = status
    if outcome:
        intervention.outcome = outcome
    if status in ('Resolved', 'Closed'):
        intervention.resolved_at = datetime.now()
        term = intervention.term_id
        intervention.resolved_pct = student_term_percentage(intervention.student_id, term)
    db.session.commit()
    return True


def _row(iv):
    current = student_term_percentage(iv.student_id, iv.term_id)
    base = iv.baseline_pct
    delta = round((current - base), 1) if (current is not None and base is not None) else None
    direction = 'flat'
    if delta is not None:
        direction = 'up' if delta >= IMPROVE_DELTA else ('down' if delta < 0 else 'flat')
    return {
        'id': iv.id, 'student_id': iv.student_id,
        'name': iv.student.full_name if iv.student else '—',
        'class': _class_for(iv.student_id, iv.term_id),
        'reason': iv.reason or '', 'status': iv.status,
        'baseline': base, 'current': current, 'delta': delta, 'direction': direction,
        'opened': iv.created_at.strftime('%d %b %Y') if iv.created_at else '',
        'opened_by': iv.opened_by or '',
        'outcome': iv.outcome or '',
        'notes': [{'kind': n.kind, 'body': n.body or '', 'next_action': n.next_action or '',
                   'next_date': n.next_date.strftime('%d %b %Y') if n.next_date else '',
                   'author': n.author or '',
                   'date': n.created_at.strftime('%d %b %Y') if n.created_at else ''}
                  for n in iv.notes.order_by(InterventionNote.created_at.desc()).all()],
        'note_url': None,
    }


def student_interventions(student_id):
    ivs = (AttendanceIntervention.query.filter_by(student_id=student_id)
           .order_by(AttendanceIntervention.created_at.desc()).all())
    return [_row(iv) for iv in ivs]


def recommendations(term, caa_ids, threshold=None):
    """Students below the warning threshold in the given classes who have no open
    intervention — candidates to open one for."""
    from utils.attendance_notify import _low_attendance_student_ids
    threshold = threshold if threshold is not None else warning_threshold()
    low_ids = _low_attendance_student_ids(term, caa_ids, threshold)
    if not low_ids:
        return []
    open_ids = {r[0] for r in db.session.query(AttendanceIntervention.student_id).filter(
        AttendanceIntervention.student_id.in_(low_ids),
        AttendanceIntervention.term_id == term.id,
        AttendanceIntervention.status.in_(['Open', 'In progress', 'Escalated'])).all()}
    out = []
    smap = {s.id: s for s in Student.query.filter(Student.id.in_(low_ids)).all()}
    for sid in low_ids:
        if sid in open_ids:
            continue
        s = smap.get(sid)
        if not s:
            continue
        out.append({'student_id': sid, 'name': s.full_name, 'student_id_str': s.student_id,
                    'class': _class_for(sid, term.id),
                    'percentage': student_term_percentage(sid, term.id)})
    out.sort(key=lambda x: (x['percentage'] if x['percentage'] is not None else 0))
    return out


def dashboard(term, caa_ids):
    """Intervention dashboard for a term over the given classes: active cases
    bucketed by direction (improving / declining / steady) plus recommendations."""
    student_ids = [r[0] for r in db.session.query(StudentEnrollment.student_id)
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids or [-1])).all()]
    ivs = (AttendanceIntervention.query
           .filter(AttendanceIntervention.term_id == term.id,
                   AttendanceIntervention.student_id.in_(student_ids or [-1]))
           .order_by(AttendanceIntervention.created_at.desc()).all())
    active, improved, declining, resolved = [], [], [], []
    for iv in ivs:
        row = _row(iv)
        if iv.status in ('Resolved', 'Closed'):
            resolved.append(row)
            continue
        active.append(row)
        if row['direction'] == 'up':
            improved.append(row)
        elif row['direction'] == 'down':
            declining.append(row)
    return {
        'term': {'id': term.id, 'name': term.name},
        'threshold': warning_threshold(),
        'active': active, 'improved': improved, 'declining': declining,
        'resolved': resolved[:20],
        'recommendations': recommendations(term, caa_ids),
        'counts': {'active': len(active), 'improved': len(improved),
                   'declining': len(declining), 'resolved': len(resolved)},
    }
