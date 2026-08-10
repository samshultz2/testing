"""University-aspiration reference data.

Powers the student "university choice" fields: which University a student wants to
attend, the Course (with its department) and the competitive JAMB cut-off that
becomes the student's target. Course carries the nationally-standard JAMB/WAEC
subject requirements + a base competitive cut-off; a University can carry a small
"bump" (competitive schools run higher), and a UniversityCourse row can pin an
explicit cut-off for a specific university+course pair (admin-editable).
"""
from models.models import db, local_now


class University(db.Model):
    __tablename__ = 'universities'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    abbreviation = db.Column(db.String(20))
    state = db.Column(db.String(60))
    ownership = db.Column(db.String(20))          # Federal / State / Private
    # Added to a course's base cut-off for this school (competitive federals run
    # higher). Effective target = course.base_cutoff + this (unless overridden).
    cutoff_bump = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    def as_dict(self):
        return {'id': self.id, 'name': self.name, 'abbreviation': self.abbreviation or '',
                'state': self.state or '', 'ownership': self.ownership or '',
                'cutoff_bump': self.cutoff_bump or 0, 'is_active': bool(self.is_active),
                'label': f'{self.name}' + (f' ({self.abbreviation})' if self.abbreviation else '')}

    def __repr__(self):
        return f'<University {self.abbreviation or self.name}>'


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    department = db.Column(db.String(120))
    # Representative competitive JAMB score for this course nationally (a score
    # that would put a candidate in strong contention for admission).
    base_cutoff = db.Column(db.Integer, default=180)
    # Nationally-standard requirements (comma-separated subject names). JAMB is
    # English (compulsory) + three others; WAEC is the credit subjects needed.
    jamb_subjects = db.Column(db.Text)
    waec_subjects = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    @property
    def jamb_subject_list(self):
        return [s.strip() for s in (self.jamb_subjects or '').split(',') if s.strip()]

    @property
    def waec_subject_list(self):
        return [s.strip() for s in (self.waec_subjects or '').split(',') if s.strip()]

    def as_dict(self):
        return {'id': self.id, 'name': self.name, 'department': self.department or '',
                'base_cutoff': self.base_cutoff or 180,
                'jamb_subjects': self.jamb_subject_list, 'waec_subjects': self.waec_subject_list,
                'is_active': bool(self.is_active), 'label': self.name}

    def __repr__(self):
        return f'<Course {self.name}>'


class UniversityCourse(db.Model):
    """Optional explicit cut-off override for a specific university+course pair."""
    __tablename__ = 'university_courses'

    id = db.Column(db.Integer, primary_key=True)
    university_id = db.Column(db.Integer, db.ForeignKey('universities.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False, index=True)
    jamb_cutoff = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    __table_args__ = (db.UniqueConstraint('university_id', 'course_id', name='uq_university_course'),)

    university = db.relationship('University')
    course = db.relationship('Course')

    def __repr__(self):
        return f'<UniversityCourse u{self.university_id} c{self.course_id} {self.jamb_cutoff}>'


class StudentScholarship(db.Model):
    """A scholarship / financial-aid record a student is pursuing or holds."""
    __tablename__ = 'student_scholarships'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    provider = db.Column(db.String(160))
    amount = db.Column(db.Float)
    status = db.Column(db.String(20))            # Prospective / Applied / Awarded / Declined
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)

    def as_dict(self):
        return {'id': self.id, 'name': self.name, 'provider': self.provider or '',
                'amount': self.amount, 'status': self.status or '', 'notes': self.notes or ''}

    def __repr__(self):
        return f'<StudentScholarship {self.name} s{self.student_id}>'


def effective_cutoff(university, course):
    """The competitive JAMB target for a university+course: an explicit
    UniversityCourse override if present, else the course base + the university's
    bump, capped at 400. Course base alone when no university is chosen yet."""
    if course is None:
        return None
    base = course.base_cutoff or 180
    if university is None:
        return min(base, 400)
    row = UniversityCourse.query.filter_by(
        university_id=university.id, course_id=course.id, is_active=True).first()
    if row and row.jamb_cutoff:
        return min(int(row.jamb_cutoff), 400)
    return min(base + (university.cutoff_bump or 0), 400)
