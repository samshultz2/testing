"""SQLAlchemy models — student (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


class Student(db.Model):
    """Core student information model"""
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    first_name = db.Column(db.String(50), nullable=False)
    middle_name = db.Column(db.String(50))
    surname = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(10), nullable=False)  # Male/Female
    date_of_birth = db.Column(db.Date)
    religion = db.Column(db.String(30))
    home_address = db.Column(db.Text)
    hobbies = db.Column(db.Text)
    photo_url = db.Column(db.String(255))
    # Optional external-exam enrolment (comma-separated subject names).
    # Used to auto-populate the WAEC / JAMB result-entry subject fields.
    waec_subjects = db.Column(db.Text)
    jamb_subjects = db.Column(db.Text)
    # Academic stream / track: 'Science', 'Arts' or 'Commercial'.
    stream = db.Column(db.String(20))
    # Target JAMB score the student is aiming for (0-400).
    jamb_target = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Graduation fields
    is_graduated = db.Column(db.Boolean, default=False)
    graduation_date = db.Column(db.Date)
    graduation_session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'))

    # CBT / student portal login password — stored HASH-ONLY (one-way scrypt).
    # The raw PIN is shown/printed once at generation and is NOT recoverable:
    # there is deliberately no plaintext/encrypted copy kept. To re-issue a lost
    # PIN, an admin regenerates it (Student Passwords UI). The legacy
    # `portal_password_plain` column is no longer mapped here and is nulled by
    # scripts/clear_portal_passwords.py.
    portal_password_hash = db.Column(db.String(256))

    # Relationships
    parent_contacts = db.relationship('ParentContact', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    enrollments = db.relationship('StudentEnrollment', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    waec_results = db.relationship('WAECResult', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    jamb_results = db.relationship('JAMBResult', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    graduation_session = db.relationship('AcademicSession', foreign_keys=[graduation_session_id])
    
    @property
    def full_name(self):
        """Return full name of student"""
        if self.middle_name:
            return f"{self.surname} {self.first_name} {self.middle_name}"
        return f"{self.surname} {self.first_name}"
    
    @property
    def waec_subject_list(self):
        """Subjects the student is enrolled to sit for WAEC."""
        return [s.strip() for s in (self.waec_subjects or '').split(',') if s.strip()]

    @property
    def jamb_subject_list(self):
        """Subjects the student is enrolled to sit for JAMB."""
        return [s.strip() for s in (self.jamb_subjects or '').split(',') if s.strip()]

    @property
    def age(self):
        """Calculate student's age"""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None
    
    def set_portal_password(self, password):
        # Hash-only: keep the one-way hash for login verification, never a
        # recoverable copy. The caller shows/prints the raw PIN once.
        self.portal_password_hash = generate_password_hash(password)

    def check_portal_password(self, password):
        # Cap length before hashing — scrypt on an unbounded value is a worker DoS.
        from utils.security import MAX_PASSWORD_LEN
        if not password or len(password) > MAX_PASSWORD_LEN:
            return False
        return bool(self.portal_password_hash) and check_password_hash(self.portal_password_hash, password)

    @staticmethod
    def generate_student_id():
        """Generate a unique STU##### id (robust to legacy/non-conforming ids)."""
        nums = []
        for (sid,) in db.session.query(Student.student_id).all():
            if sid and sid.startswith('STU'):
                try:
                    nums.append(int(sid[3:]))
                except (ValueError, TypeError):
                    continue
        return f"STU{(max(nums) if nums else 0) + 1:05d}"
    
    def __repr__(self):
        return f'<Student {self.full_name}>'


class ParentContact(db.Model):
    """Parent/Guardian contact information"""
    __tablename__ = 'parent_contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    phone_number = db.Column(db.String(15), nullable=False)
    relationship = db.Column(db.String(20))  # Father, Mother, Guardian, etc.
    name = db.Column(db.String(100))
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)
    
    def __repr__(self):
        return f'<ParentContact {self.phone_number}>'
