"""
Admissions models — prospective-student pipeline from inquiry to enrolment.

An ``Applicant`` moves through a status pipeline (Inquiry → Applied → Screening →
Offered → Accepted → Admitted / Rejected / Waitlisted). On admission it can be
converted, in one click, into a real ``Student`` (plus a parent contact and an
optional class-arm enrolment), linking the two records.
"""
from datetime import date

from models.models import db, local_now


class Applicant(db.Model):
    __tablename__ = 'applicants'

    id = db.Column(db.Integer, primary_key=True)
    application_no = db.Column(db.String(20), unique=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))

    # Bio
    first_name = db.Column(db.String(60), nullable=False)
    surname = db.Column(db.String(60), nullable=False)
    middle_name = db.Column(db.String(60))
    gender = db.Column(db.String(10))
    date_of_birth = db.Column(db.Date)
    photo_url = db.Column(db.String(255))

    # Application
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'))
    intended_class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'))
    previous_school = db.Column(db.String(150))
    source = db.Column(db.String(60))          # how they heard about the school
    status = db.Column(db.String(20), default='Inquiry')
    entrance_score = db.Column(db.Float)
    applied_date = db.Column(db.Date, default=date.today)
    decision_date = db.Column(db.Date)

    # Parent / guardian
    parent_name = db.Column(db.String(100))
    parent_phone = db.Column(db.String(20))
    parent_email = db.Column(db.String(120))
    relationship = db.Column(db.String(40))
    address = db.Column(db.String(255))

    notes = db.Column(db.Text)
    admitted_student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    session = db.relationship('AcademicSession')
    intended_class = db.relationship('SchoolClass')
    admitted_student = db.relationship('Student')

    @property
    def full_name(self):
        return ' '.join(p for p in [self.surname, self.first_name, self.middle_name] if p)

    @property
    def display_name(self):
        return ' '.join(p for p in [self.first_name, self.surname] if p)

    @staticmethod
    def generate_application_no():
        yr = date.today().year
        prefix = f'APP{yr}-'
        last = (Applicant.query.filter(Applicant.application_no.like(f'{prefix}%'))
                .order_by(Applicant.id.desc()).first())
        n = 1
        if last and last.application_no:
            try:
                n = int(last.application_no.split('-')[-1]) + 1
            except ValueError:
                n = Applicant.query.count() + 1
        return f'{prefix}{n:04d}'

    def __repr__(self):
        return f'<Applicant {self.application_no} {self.full_name} {self.status}>'
