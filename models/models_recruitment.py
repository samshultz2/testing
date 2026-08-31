"""Recruitment / ATS models — job vacancies, applications and interviews.

Kept modular and self-contained: a hire converts a JobApplication into a
StaffMember (the HR record of truth), so recruitment never duplicates the staff
schema — it feeds it."""
from datetime import date

from models.models import db, local_now


class JobVacancy(db.Model):
    __tablename__ = 'job_vacancies'

    STATUSES = ['Open', 'Closed', 'Filled']

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    title = db.Column(db.String(150), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    staff_type = db.Column(db.String(20), default='Teaching')
    employment_type = db.Column(db.String(20), default='Full-time')
    positions = db.Column(db.Integer, default=1)          # openings
    description = db.Column(db.Text)
    requirements = db.Column(db.Text)
    status = db.Column(db.String(12), default='Open')
    posted_date = db.Column(db.Date, default=date.today)
    closing_date = db.Column(db.Date)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    department = db.relationship('Department')
    applications = db.relationship('JobApplication', backref='vacancy',
                                   lazy='dynamic', cascade='all, delete-orphan')

    @property
    def is_open(self):
        return (self.status or 'Open') == 'Open'


class JobApplication(db.Model):
    __tablename__ = 'job_applications'

    # Pipeline stages, in order.
    STATUSES = ['Applied', 'Shortlisted', 'Interview', 'Offered', 'Hired', 'Rejected']

    id = db.Column(db.Integer, primary_key=True)
    vacancy_id = db.Column(db.Integer, db.ForeignKey('job_vacancies.id'), nullable=False, index=True)
    first_name = db.Column(db.String(60), nullable=False)
    surname = db.Column(db.String(60), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    gender = db.Column(db.String(10))
    qualification = db.Column(db.String(200))
    experience_years = db.Column(db.Integer)
    cover_note = db.Column(db.Text)
    resume_id = db.Column(db.Integer, db.ForeignKey('comm_attachments.id'))
    status = db.Column(db.String(12), default='Applied')
    rating = db.Column(db.Integer)                        # 1–5 shortlisting score
    applied_date = db.Column(db.Date, default=date.today)
    hired_staff_id = db.Column(db.Integer, db.ForeignKey('staff_members.id'))
    created_at = db.Column(db.DateTime, default=local_now)

    resume = db.relationship('CommAttachment')
    interviews = db.relationship('Interview', backref='application',
                                 lazy='dynamic', cascade='all, delete-orphan')

    @property
    def full_name(self):
        return ' '.join(p for p in [self.surname, self.first_name] if p)


class Interview(db.Model):
    __tablename__ = 'interviews'

    MODES = ['In-person', 'Phone', 'Video']
    OUTCOMES = ['Pending', 'Passed', 'Failed']

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('job_applications.id'), nullable=False, index=True)
    scheduled_at = db.Column(db.DateTime)
    mode = db.Column(db.String(12), default='In-person')
    location = db.Column(db.String(150))                 # room or meeting link
    interviewer = db.Column(db.String(120))
    notes = db.Column(db.Text)
    outcome = db.Column(db.String(10), default='Pending')
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
