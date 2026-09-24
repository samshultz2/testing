"""Attendance intervention workflow — open, follow up, resolve, and track whether
a struggling student's attendance recovers. Read/writes only the intervention
tables; never the attendance marking path."""
from datetime import datetime
from utils import timeutil

from models import (db, AttendanceIntervention, InterventionNote, Student,
                    StudentEnrollment, ClassArmAssignment)
from utils.attendance_profile import student_term_percentage, warning_threshold, bulk_term_percentages

IMPROVE_DELTA = 5.0   # ≥ +5 pts vs baseline counts as "improving"
_UNSET = object()      # distinguishes "no bulk value passed" from "bulk value is None"


def _class_for(student_id, term_id):
    caa = (ClassArmAssignment.query
           .join(StudentEnrollment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
           .filter(StudentEnrollment.student_id == student_id,
                   ClassArmAssignment.term_id == term_id).first())
    return caa.display_name if caa else ''


def _bulk_class_for(student_ids, term_id):
    """_class_for() for many students in one query, with school_class/arm
    (both lazy many-to-ones behind .display_name) eager-loaded so building
    the name doesn't re-add its own N+1 on top."""
    if not student_ids:
        return {}
    from sqlalchemy.orm import joinedload
    rows = (db.session.query(StudentEnrollment.student_id, ClassArmAssignment)
            .join(ClassArmAssignment, StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
            .filter(StudentEnrollment.student_id.in_(student_ids),
                    ClassArmAssignment.term_id == term_id)
            .options(joinedload(ClassArmAssignment.school_class),
                     joinedload(ClassArmAssignment.arm))
            .all())
    out = {}
    for sid, caa in rows:
        out.setdefault(sid, caa.display_name)
    return out


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
        intervention.resolved_at = timeutil.now()
        term = intervention.term_id
        intervention.resolved_pct = student_term_percentage(intervention.student_id, term)
    db.session.commit()
    return True


def _row(iv, *, current=_UNSET, class_name=None, notes=None):
    """Build one dashboard row. Bulk callers (dashboard()) pass the
    already-batched current %, class name and notes so this does zero extra
    queries per row; single-item callers (student_interventions()) leave
    them unset and fall back to the (slower, but fine at that scale)
    per-item lookups."""
    if current is _UNSET:
        current = student_term_percentage(iv.student_id, iv.term_id)
    if class_name is None:
        class_name = _class_for(iv.student_id, iv.term_id)
    if notes is None:
        notes = iv.notes.order_by(InterventionNote.created_at.desc()).all()
    base = iv.baseline_pct
    delta = round((current - base), 1) if (current is not None and base is not None) else None
    direction = 'flat'
    if delta is not None:
        direction = 'up' if delta >= IMPROVE_DELTA else ('down' if delta < 0 else 'flat')
    return {
        'id': iv.id, 'student_id': iv.student_id,
        'name': iv.student.full_name if iv.student else '—',
        'class': class_name,
        'reason': iv.reason or '', 'status': iv.status,
        'baseline': base, 'current': current, 'delta': delta, 'direction': direction,
        'opened': iv.created_at.strftime('%d %b %Y') if iv.created_at else '',
        'opened_by': iv.opened_by or '',
        'outcome': iv.outcome or '',
        'notes': [{'kind': n.kind, 'body': n.body or '', 'next_action': n.next_action or '',
                   'next_date': n.next_date.strftime('%d %b %Y') if n.next_date else '',
                   'author': n.author or '',
                   'date': n.created_at.strftime('%d %b %Y') if n.created_at else ''}
                  for n in notes],
        'note_url': None,
    }


def student_interventions(student_id):
    ivs = (AttendanceIntervention.query.filter_by(student_id=student_id)
           .order_by(AttendanceIntervention.created_at.desc()).all())
    return [_row(iv) for iv in ivs]


def recommendations(term, caa_ids, threshold=None):
    """Students below the warning threshold in the given classes who have no open
    intervention — candidates to open one for. Batched: one query each for the
    student rows, current percentages and class names, regardless of how many
    candidates there are (previously one query of each per candidate)."""
    from utils.attendance_notify import _low_attendance_student_ids
    threshold = threshold if threshold is not None else warning_threshold()
    low_ids = _low_attendance_student_ids(term, caa_ids, threshold)
    if not low_ids:
        return []
    open_ids = {r[0] for r in db.session.query(AttendanceIntervention.student_id).filter(
        AttendanceIntervention.student_id.in_(low_ids),
        AttendanceIntervention.term_id == term.id,
        AttendanceIntervention.status.in_(['Open', 'In progress', 'Escalated'])).all()}
    candidate_ids = [sid for sid in low_ids if sid not in open_ids]
    if not candidate_ids:
        return []
    smap = {s.id: s for s in Student.query.filter(Student.id.in_(candidate_ids)).all()}
    pct_map = bulk_term_percentages(candidate_ids, term.id)
    class_map = _bulk_class_for(candidate_ids, term.id)
    out = []
    for sid in candidate_ids:
        s = smap.get(sid)
        if not s:
            continue
        out.append({'student_id': sid, 'name': s.full_name, 'student_id_str': s.student_id,
                    'class': class_map.get(sid, ''),
                    'percentage': pct_map.get(sid)})
    out.sort(key=lambda x: (x['percentage'] if x['percentage'] is not None else 0))
    return out


def dashboard(term, caa_ids):
    """Intervention dashboard for a term over the given classes: active cases
    bucketed by direction (improving / declining / steady) plus recommendations.

    Batched throughout (student, current %, class name and notes are all
    fetched in one query each for every intervention row) so this doesn't
    scale query count with the number of open interventions."""
    from sqlalchemy.orm import contains_eager
    student_ids = [r[0] for r in db.session.query(StudentEnrollment.student_id)
                   .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids or [-1])).all()]
    ivs = (AttendanceIntervention.query
           .filter(AttendanceIntervention.term_id == term.id,
                   AttendanceIntervention.student_id.in_(student_ids or [-1]))
           .join(AttendanceIntervention.student)
           .options(contains_eager(AttendanceIntervention.student))
           .order_by(AttendanceIntervention.created_at.desc()).all())

    iv_student_ids = [iv.student_id for iv in ivs]
    pct_map = bulk_term_percentages(iv_student_ids, term.id)
    class_map = _bulk_class_for(iv_student_ids, term.id)
    notes_by_iv = {}
    if ivs:
        for n in (InterventionNote.query
                  .filter(InterventionNote.intervention_id.in_([iv.id for iv in ivs]))
                  .order_by(InterventionNote.created_at.desc()).all()):
            notes_by_iv.setdefault(n.intervention_id, []).append(n)

    # improved/declining are never sent as their own row lists — every field
    # a client needs (including `direction`) is already on each `active` row,
    # so a separate copy would just double the payload for no reader; only
    # their counts are used (the stat-card totals).
    active, resolved = [], []
    n_improved = n_declining = 0
    for iv in ivs:
        row = _row(iv, current=pct_map.get(iv.student_id),
                   class_name=class_map.get(iv.student_id, ''),
                   notes=notes_by_iv.get(iv.id, []))
        if iv.status in ('Resolved', 'Closed'):
            resolved.append(row)
            continue
        active.append(row)
        if row['direction'] == 'up':
            n_improved += 1
        elif row['direction'] == 'down':
            n_declining += 1
    return {
        'term': {'id': term.id, 'name': term.name},
        'threshold': warning_threshold(),
        'active': active,
        'resolved': resolved[:20],
        'recommendations': recommendations(term, caa_ids),
        'counts': {'active': len(active), 'improved': n_improved,
                   'declining': n_declining, 'resolved': len(resolved)},
    }
