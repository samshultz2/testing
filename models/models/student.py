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
    home_address = db.Column(EncryptedString())   # encrypted at rest (never searched)
    hobbies = db.Column(db.Text)
    photo_url = db.Column(db.String(255))

    # Optional pastoral fields (school-configurable; never required).
    house = db.Column(db.String(40))                    # boarding/sports house
    boarding_status = db.Column(db.String(10))          # 'Day' | 'Boarding'

    # Optional identity records. NIN/JAMB numbers stay plain so they remain
    # searchable (a registrar looks students up by them); they are not secrets in
    # the way a password is.
    nin = db.Column(db.String(20), index=True)
    jamb_reg_number = db.Column(db.String(30), index=True)
    jamb_profile_code = db.Column(db.String(30))
    # WAEC/NECO examination registration number + the candidate's serial number,
    # shown on statements of result, transcripts and testimonials.
    waec_reg_number = db.Column(db.String(30), index=True)
    serial_number = db.Column(db.String(30))
    waec_epin = db.Column(db.String(30))                # WAEC e-PIN (registration/result PIN)

    # Optional medical record. Structured fields stay plain (shown on ID cards /
    # needed fast in an emergency); the free-text notes are encrypted at rest.
    blood_group = db.Column(db.String(6))
    genotype = db.Column(db.String(6))                  # AA/AS/SS/AC…
    allergies = db.Column(db.Text)
    medical_conditions = db.Column(db.Text)
    disabilities = db.Column(db.Text)
    medications = db.Column(db.Text)
    medical_notes = db.Column(EncryptedString())        # sensitive free text
    emergency_medical = db.Column(EncryptedString())    # emergency instructions
    # Optional external-exam enrolment (comma-separated subject names).
    # Used to auto-populate the WAEC / JAMB result-entry subject fields.
    waec_subjects = db.Column(db.Text)
    jamb_subjects = db.Column(db.Text)
    # Academic stream / track: 'Science', 'Arts' or 'Commercial'.
    stream = db.Column(db.String(20))
    # Target JAMB score the student is aiming for (0-400). Auto-filled from the
    # chosen university+course's competitive cut-off, but editable.
    jamb_target = db.Column(db.Integer)
    # University aspiration: where the student wants to study, what course and in
    # which department. Drives the JAMB target + subject requirements auto-fill
    # and feeds admission-readiness/predictions (see utils.exam_insights).
    target_university_id = db.Column(db.Integer, db.ForeignKey('universities.id'))
    target_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    target_department = db.Column(db.String(120))
    # Backup (2nd choice) aspiration — mirrors JAMB's 1st/2nd choice.
    target2_university_id = db.Column(db.Integer, db.ForeignKey('universities.id'))
    target2_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    # Intended career (informs course alignment).
    career_goal = db.Column(db.String(120))
    # Admission outcome tracking (applied → offered → admitted → declined), and
    # where the student was actually admitted (may differ from the target).
    admission_status = db.Column(db.String(20))
    admitted_university_id = db.Column(db.Integer, db.ForeignKey('universities.id'))
    admitted_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Graduation fields
    is_graduated = db.Column(db.Boolean, default=False)
    graduation_date = db.Column(db.Date)
    graduation_session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'))
    # Graduate lifecycle status (see models_graduate.GRADUATE_STATUSES). NULL until
    # graduated; set to 'Graduated' when marked, then advanced by admins (logged).
    graduate_status = db.Column(db.String(40))

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
    target_university = db.relationship('University', foreign_keys=[target_university_id])
    target_course = db.relationship('Course', foreign_keys=[target_course_id])
    target2_university = db.relationship('University', foreign_keys=[target2_university_id])
    target2_course = db.relationship('Course', foreign_keys=[target2_course_id])
    admitted_university = db.relationship('University', foreign_keys=[admitted_university_id])
    admitted_course = db.relationship('Course', foreign_keys=[admitted_course_id])
    scholarships = db.relationship('StudentScholarship', backref='student',
                                   lazy='dynamic', cascade='all, delete-orphan')

    @property
    def target_university_name(self):
        u = self.target_university
        return u.name if u else None

    @property
    def target_course_name(self):
        c = self.target_course
        return c.name if c else None

    @property
    def target2_university_name(self):
        return self.target2_university.name if self.target2_university else None

    @property
    def target2_course_name(self):
        return self.target2_course.name if self.target2_course else None

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
    def has_medical(self):
        """True if any medical field is populated (so the profile can hide the
        section entirely for schools that don't use it)."""
        return any([self.blood_group, self.genotype, self.allergies,
                    self.medical_conditions, self.disabilities, self.medications,
                    self.medical_notes, self.emergency_medical])

    @property
    def has_identity(self):
        return any([self.nin, self.jamb_reg_number, self.jamb_profile_code,
                    self.waec_reg_number, self.serial_number, self.waec_epin])

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


class StudentPhoto(db.Model):
    """A student's passport photo, stored in the school's own tenant DB (durable
    across restarts) in its own table so the hot ``students`` table stays lean —
    the blob is loaded only when a photo is actually shown or printed. One row per
    student; re-uploading replaces the bytes. Served only behind login + branch
    scope (it is PII), never via the public site-media route."""
    __tablename__ = 'student_photos'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'),
                           nullable=False, unique=True, index=True)
    data = db.Column(db.LargeBinary, nullable=False)
    mime = db.Column(db.String(40), nullable=False, default='image/jpeg')
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    bytes = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    student = db.relationship('Student', backref=db.backref('photo', uselist=False,
                                                            cascade='all, delete-orphan'))


class ParentContact(db.Model):
    """Parent/Guardian contact information"""
    __tablename__ = 'parent_contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    # Indexed: parents are looked up by student on every student-profile load and
    # joined in the students search; without this the FK lookup scans the table.
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    phone_number = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(120))        # optional — enables email reminders
    relationship = db.Column(db.String(20))  # Father, Mother, Guardian, etc.
    name = db.Column(db.String(100))
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)
    
    def __repr__(self):
        return f'<ParentContact {self.phone_number}>'
