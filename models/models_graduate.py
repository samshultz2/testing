"""Graduate Management — status lifecycle + structured audit trail.

A graduated student keeps their full student record (nothing is deleted); this
module adds a graduate *lifecycle status* and a tamper-evident audit log of every
post-graduation change (who, when, old value, new value, reason).
"""
from models.models import db, local_now


# The canonical graduate lifecycle. Order is roughly chronological; the UI offers
# them as a dropdown. 'Deceased' is sensitive — kept last.
GRADUATE_STATUSES = [
    'Graduation Pending',
    'Graduated',
    'Certificate Issued',
    'Alumni Active',
    'Transcript Requested',
    'Transcript Issued',
    'Employment Verification Completed',
    'Further Education Recorded',
    'Alumni Ambassador',
    'Deceased',
]

# Statuses only high-privilege users should be able to set (sensitive/irreversible).
RESTRICTED_STATUSES = {'Deceased'}


class GraduateAudit(db.Model):
    """One immutable record of a post-graduation modification. Generic on purpose
    (field/old/new) so it covers status changes now and other graduate-record edits
    later. Append-only — rows are never updated or deleted in normal use."""
    __tablename__ = 'graduate_audits'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    field = db.Column(db.String(40), nullable=False)      # e.g. 'graduate_status'
    old_value = db.Column(db.String(160))
    new_value = db.Column(db.String(160))
    reason = db.Column(db.String(300))
    actor = db.Column(db.String(80))                      # username who made the change
    created_at = db.Column(db.DateTime, default=local_now, index=True)

    student = db.relationship('Student')
