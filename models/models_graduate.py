"""Graduate Management — status lifecycle + structured audit trail.

A graduated student keeps their full student record (nothing is deleted); this
module adds a graduate *lifecycle status* and a tamper-evident audit log of every
post-graduation change (who, when, old value, new value, reason).
"""
import secrets

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


# Document types the school can issue to a graduate (Phase 2).
GRADUATE_DOC_TYPES = {
    'slc': 'School Leaving Certificate',
    'statement': 'Statement of Result',
    'transcript': 'Academic Transcript',
    'testimonial': 'Testimonial / Character Certificate',
    'recommendation': 'Recommendation Letter',
    'conduct': 'Conduct Report',
    'notification': 'Result Notification Slip',
}
_DOC_ABBR = {'slc': 'SLC', 'statement': 'SOR', 'transcript': 'TRN', 'testimonial': 'TST',
             'recommendation': 'REC', 'conduct': 'CDT', 'notification': 'RNS'}


class GraduateDocument(db.Model):
    """An issued graduate document (leaving certificate / transcript / etc.). We
    store the issue metadata + a public verification code; the PDF is rendered on
    demand from the permanent record. One row per (student, doc_type); re-issuing
    the same type increments ``reprint_count`` and keeps the same document number
    and verification code so a previously-verified document stays valid."""
    __tablename__ = 'graduate_documents'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    doc_type = db.Column(db.String(40), nullable=False)
    document_number = db.Column(db.String(50), unique=True, nullable=False)
    verification_code = db.Column(db.String(24), unique=True, nullable=False, index=True)
    issued_by = db.Column(db.String(80))
    reprint_count = db.Column(db.Integer, default=0)      # 0 = original; +1 each reprint
    revoked = db.Column(db.Boolean, default=False)        # a revoked doc verifies as invalid
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    student = db.relationship('Student')

    __table_args__ = (
        db.UniqueConstraint('student_id', 'doc_type', name='uq_graduate_document'),
    )

    @property
    def label(self):
        return GRADUATE_DOC_TYPES.get(self.doc_type, self.doc_type)

    @staticmethod
    def new_code():
        return secrets.token_hex(5).upper()              # 10 hex chars, human-readable

    @staticmethod
    def make_number(doc_type, student, year):
        return f"{_DOC_ABBR.get(doc_type, 'DOC')}/{year}/{(student.student_id or student.id)}"
