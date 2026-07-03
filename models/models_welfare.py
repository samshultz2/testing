"""Student welfare — discipline/incident log and sick bay (clinic) visits.

Both are simple per-student logs that appear on the student profile. Each row
carries the branch (for scoping) and who recorded it.
"""
from datetime import date

from models.models import db, local_now, EncryptedString


class DisciplineRecord(db.Model):
    """A behaviour/discipline incident and the action taken."""
    __tablename__ = 'discipline_records'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(50))            # Lateness, Fighting, Uniform, etc.
    description = db.Column(EncryptedString(), nullable=False)   # encrypted at rest
    action_taken = db.Column(EncryptedString())                 # encrypted at rest
    severity = db.Column(db.String(20))            # Minor / Major
    reported_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student', backref=db.backref(
        'discipline_records', lazy='dynamic', cascade='all, delete-orphan'))


class ClinicVisit(db.Model):
    """A sick bay / clinic visit."""
    __tablename__ = 'clinic_visits'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    date = db.Column(db.Date, nullable=False, default=date.today)
    complaint = db.Column(EncryptedString(), nullable=False)    # medical — encrypted at rest
    treatment = db.Column(EncryptedString())                    # medical — encrypted at rest
    parent_notified = db.Column(db.Boolean, default=False)
    attended_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student', backref=db.backref(
        'clinic_visits', lazy='dynamic', cascade='all, delete-orphan'))
