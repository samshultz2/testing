"""
Database models for the Student Management System
All models use SQLAlchemy ORM for database operations
"""
import os
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def local_now():
    """Current datetime in the configured site timezone (naive wall-clock)."""
    try:
        from utils.timeutil import now as _now
        return _now()
    except Exception:
        return datetime.now()


# ============================================================================
# STUDENT MODELS
# ============================================================================

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

    # CBT / student portal login password (plaintext kept so it can be
    # re-printed/exported by class — these are low-sensitivity exam passwords).
    portal_password_hash = db.Column(db.String(256))
    portal_password_plain = db.Column(db.String(60))

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
        self.portal_password_hash = generate_password_hash(password)
        self.portal_password_plain = password

    def check_portal_password(self, password):
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


# ============================================================================
# ACADEMIC STRUCTURE MODELS
# ============================================================================

class AcademicSession(db.Model):
    """Academic session (e.g., 2023/2024)"""
    __tablename__ = 'academic_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)  # e.g., "2023/2024"
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    terms = db.relationship('Term', backref='session', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AcademicSession {self.name}>'


class Term(db.Model):
    """Academic term within a session"""
    __tablename__ = 'terms'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=False)
    term_number = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    name = db.Column(db.String(20), nullable=False)  # First Term, Second Term, Third Term
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=False)
    # When True, term results are released to the student/parent result-checker portal.
    results_published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)

    # Relationships
    weeks = db.relationship('Week', backref='term', lazy='dynamic', cascade='all, delete-orphan')
    holidays = db.relationship('Holiday', backref='term', lazy='dynamic', cascade='all, delete-orphan')
    class_arm_assignments = db.relationship('ClassArmAssignment', backref='term', lazy='dynamic')
    
    @property
    def full_name(self):
        """Return term name with session"""
        return f"{self.name} - {self.session.name}"
    
    def __repr__(self):
        return f'<Term {self.name} - {self.session.name}>'


class SchoolClass(db.Model):
    """School class (JSS1, JSS2, etc.)"""
    __tablename__ = 'school_classes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    level = db.Column(db.Integer, nullable=False)  # 1-6 for ordering
    description = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    assignments = db.relationship('ClassArmAssignment', backref='school_class', lazy='dynamic')
    
    def __repr__(self):
        return f'<SchoolClass {self.name}>'


class ClassArm(db.Model):
    """Class arm (Rose, Lily, etc.)"""
    __tablename__ = 'class_arms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    description = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    assignments = db.relationship('ClassArmAssignment', backref='arm', lazy='dynamic')
    
    def __repr__(self):
        return f'<ClassArm {self.name}>'


class ClassArmAssignment(db.Model):
    """Links class + arm + session + term with form teacher"""
    __tablename__ = 'class_arm_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    arm_id = db.Column(db.Integer, db.ForeignKey('class_arms.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    form_teacher_name = db.Column(db.String(100))
    form_teacher_phone = db.Column(db.String(15))
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    enrollments = db.relationship('StudentEnrollment', backref='class_arm_assignment', lazy='dynamic', cascade='all, delete-orphan')
    
    # Unique constraint: one class-arm combo per term
    __table_args__ = (
        db.UniqueConstraint('class_id', 'arm_id', 'term_id', name='unique_class_arm_term'),
    )
    
    @property
    def display_name(self):
        """Return formatted name like 'JSS1 Rose'"""
        return f"{self.school_class.name} {self.arm.name}"
    
    @property
    def full_display_name(self):
        """Return full name with term"""
        return f"{self.school_class.name} {self.arm.name} - {self.term.full_name}"
    
    def __repr__(self):
        return f'<ClassArmAssignment {self.display_name}>'


class StudentEnrollment(db.Model):
    """Student enrollment in a specific class arm for a term"""
    __tablename__ = 'student_enrollments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=local_now)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    attendance_records = db.relationship('Attendance', backref='enrollment', lazy='dynamic', cascade='all, delete-orphan')
    
    # Unique constraint: one enrollment per student per term
    __table_args__ = (
        db.UniqueConstraint('student_id', 'class_arm_assignment_id', name='unique_student_enrollment'),
    )
    
    def __repr__(self):
        return f'<StudentEnrollment {self.student.full_name} in {self.class_arm_assignment.display_name}>'


# ============================================================================
# ATTENDANCE MODELS
# ============================================================================

class Week(db.Model):
    """Week within a term"""
    __tablename__ = 'weeks'
    
    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)  # Monday
    end_date = db.Column(db.Date, nullable=False)  # Friday
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    attendance_records = db.relationship('Attendance', backref='week', lazy='dynamic')
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('term_id', 'week_number', name='unique_week_in_term'),
    )
    
    def __repr__(self):
        return f'<Week {self.week_number} of Term {self.term_id}>'


class Holiday(db.Model):
    """Public holidays and mid-term breaks"""
    __tablename__ = 'holidays'
    
    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    holiday_type = db.Column(db.String(30))  # Public Holiday, Mid-term Break
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('term_id', 'date', name='unique_holiday_date'),
    )
    
    def __repr__(self):
        return f'<Holiday {self.date} - {self.reason}>'


class Attendance(db.Model):
    """Daily attendance record for a student"""
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('student_enrollments.id'), nullable=False)
    week_id = db.Column(db.Integer, db.ForeignKey('weeks.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    morning_present = db.Column(db.Boolean, default=True)
    afternoon_present = db.Column(db.Boolean, default=True)
    marked_by = db.Column(db.String(100))
    marked_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('enrollment_id', 'date', name='unique_attendance_per_day'),
    )
    
    @property
    def total_present(self):
        """Return total sessions present (0, 1, or 2)"""
        return int(self.morning_present or 0) + int(self.afternoon_present or 0)
    
    def __repr__(self):
        return f'<Attendance {self.date} - {self.enrollment.student.full_name}>'


# ============================================================================
# RESULTS MODELS
# ============================================================================

class WAECResult(db.Model):
    """WAEC examination results"""
    __tablename__ = 'waec_results'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    exam_year = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(2), nullable=False)  # A1, B2, B3, C4, C5, C6, D7, E8, F9
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('student_id', 'exam_year', 'subject', name='unique_waec_result'),
    )
    
    # Valid WAEC grades
    VALID_GRADES = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
    
    @staticmethod
    def grade_to_points(grade):
        """Convert grade to points for calculations"""
        grade_points = {
            'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5, 
            'C6': 6, 'D7': 7, 'E8': 8, 'F9': 9
        }
        return grade_points.get(grade, 9)
    
    @staticmethod
    def is_pass(grade):
        """Check if grade is a pass (C6 or better)"""
        return grade in ['A1', 'B2', 'B3', 'C4', 'C5', 'C6']
    
    def __repr__(self):
        return f'<WAECResult {self.student.full_name} - {self.subject}: {self.grade}>'


class JAMBResult(db.Model):
    """JAMB examination results"""
    __tablename__ = 'jamb_results'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    exam_year = db.Column(db.Integer, nullable=False)
    total_score = db.Column(db.Integer, nullable=False)  # 0-400
    subject1 = db.Column(db.String(50))
    subject1_score = db.Column(db.Integer)
    subject2 = db.Column(db.String(50))
    subject2_score = db.Column(db.Integer)
    subject3 = db.Column(db.String(50))
    subject3_score = db.Column(db.Integer)
    subject4 = db.Column(db.String(50))
    subject4_score = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Unique constraint
    __table_args__ = (
        db.UniqueConstraint('student_id', 'exam_year', name='unique_jamb_result'),
    )
    
    def __repr__(self):
        return f'<JAMBResult {self.student.full_name} - {self.total_score}>'


# ============================================================================
# SCHOOL SETTINGS & CONFIGURATION
# ============================================================================

class SchoolSettings(db.Model):
    """Flexible key-value configuration for school settings"""
    __tablename__ = 'school_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    value_type = db.Column(db.String(20), default='string')  # string, int, float, bool, json
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    @staticmethod
    def get(key, default=None):
        """Get a setting value by key"""
        setting = SchoolSettings.query.filter_by(key=key).first()
        if not setting:
            return default
        
        # Convert based on type
        if setting.value_type == 'int':
            return int(setting.value)
        elif setting.value_type == 'float':
            return float(setting.value)
        elif setting.value_type == 'bool':
            return setting.value.lower() in ('true', '1', 'yes')
        elif setting.value_type == 'json':
            import json
            return json.loads(setting.value)
        return setting.value
    
    @staticmethod
    def set(key, value, value_type='string', description=None):
        """Set a setting value"""
        import json
        setting = SchoolSettings.query.filter_by(key=key).first()
        
        # Convert value to string for storage
        if value_type == 'json':
            str_value = json.dumps(value)
        elif value_type == 'bool':
            str_value = 'true' if value else 'false'
        else:
            str_value = str(value)
        
        if setting:
            setting.value = str_value
            setting.value_type = value_type
            if description:
                setting.description = description
        else:
            setting = SchoolSettings(
                key=key, 
                value=str_value, 
                value_type=value_type,
                description=description
            )
            db.session.add(setting)
        
        db.session.commit()
        return setting
    
    def __repr__(self):
        return f'<SchoolSettings {self.key}={self.value}>'


class GradeScale(db.Model):
    """Grading scale configuration"""
    __tablename__ = 'grade_scales'
    
    id = db.Column(db.Integer, primary_key=True)
    grade = db.Column(db.String(5), nullable=False)  # A+, A, B, C, F
    min_score = db.Column(db.Integer, nullable=False)
    max_score = db.Column(db.Integer, nullable=False)
    remark = db.Column(db.String(50))  # Excellent, Very Good, etc.
    points = db.Column(db.Float, default=0)  # For GPA calculation if needed
    order = db.Column(db.Integer, default=0)  # Display order
    created_at = db.Column(db.DateTime, default=local_now)
    
    @staticmethod
    def get_grade(score):
        """Get grade for a given score"""
        grade = GradeScale.query.filter(
            GradeScale.min_score <= score,
            GradeScale.max_score >= score
        ).first()
        return grade.grade if grade else 'F'
    
    @staticmethod
    def get_remark(score):
        """Get remark for a given score"""
        grade = GradeScale.query.filter(
            GradeScale.min_score <= score,
            GradeScale.max_score >= score
        ).first()
        return grade.remark if grade else 'Fail'
    
    def __repr__(self):
        return f'<GradeScale {self.grade} ({self.min_score}-{self.max_score})>'


# ============================================================================
# SUBJECTS & ASSESSMENT SYSTEM
# ============================================================================

class Subject(db.Model):
    """Subjects taught in the school"""
    __tablename__ = 'subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(20))  # e.g., "ENG" for English
    category = db.Column(db.String(50))  # Science, Arts, Commercial, General
    # Whether this subject has a Midterm/Practical (P/ME). When false the
    # Midterm column is dropped and the Theory paper is worth 50 instead of 40.
    has_practical = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)

    # Relationships
    class_subjects = db.relationship('ClassSubject', backref='subject', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Subject {self.name}>'


class ClassSubject(db.Model):
    """Links subjects to class levels with teacher assignment"""
    __tablename__ = 'class_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    arm_id = db.Column(db.Integer, db.ForeignKey('class_arms.id'), nullable=True)  # NULL = all arms
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    teacher_name = db.Column(db.String(100))  # Teacher for this subject in this class
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    school_class = db.relationship('SchoolClass', backref='class_subjects')
    arm = db.relationship('ClassArm', backref='class_subjects')
    term = db.relationship('Term', backref='class_subjects')
    scores = db.relationship('StudentScore', backref='class_subject', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def display_name(self):
        """Display name with class info"""
        arm_str = f" ({self.arm.name})" if self.arm else ""
        return f"{self.subject.name} - {self.school_class.name}{arm_str}"
    
    __table_args__ = (
        db.UniqueConstraint('subject_id', 'class_id', 'arm_id', 'term_id', name='unique_class_subject'),
    )
    
    def __repr__(self):
        return f'<ClassSubject {self.display_name}>'


class AssessmentType(db.Model):
    """Types of assessments (CA components)"""
    __tablename__ = 'assessment_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "1st CA", "Midterm", "Theory Exam"
    short_name = db.Column(db.String(20))  # e.g., "CA1", "MID", "EXAM"
    max_score = db.Column(db.Integer, nullable=False)  # e.g., 5, 10, 40
    order = db.Column(db.Integer, default=0)  # Display/calculation order
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    scores = db.relationship('StudentScore', backref='assessment_type', lazy='dynamic')
    overrides = db.relationship('SubjectAssessmentOverride', backref='assessment_type', lazy='dynamic')
    
    def __repr__(self):
        return f'<AssessmentType {self.name} (max: {self.max_score})>'


class SubjectAssessmentOverride(db.Model):
    """Override assessment max scores for specific subjects"""
    __tablename__ = 'subject_assessment_overrides'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    assessment_type_id = db.Column(db.Integer, db.ForeignKey('assessment_types.id'), nullable=False)
    max_score = db.Column(db.Integer, nullable=False)  # Override max score
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subject = db.relationship('Subject', backref='assessment_overrides')
    
    __table_args__ = (
        db.UniqueConstraint('subject_id', 'assessment_type_id', name='unique_subject_assessment_override'),
    )
    
    def __repr__(self):
        return f'<SubjectAssessmentOverride {self.subject.name} - {self.assessment_type.name}: {self.max_score}>'


class StudentScore(db.Model):
    """Student scores for assessments"""
    __tablename__ = 'student_scores'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    class_subject_id = db.Column(db.Integer, db.ForeignKey('class_subjects.id'), nullable=False)
    assessment_type_id = db.Column(db.Integer, db.ForeignKey('assessment_types.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    marked_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='scores')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'class_subject_id', 'assessment_type_id', name='unique_student_score'),
    )
    
    def __repr__(self):
        return f'<StudentScore {self.student.full_name} - {self.class_subject.subject.name}: {self.score}>'


class TermResult(db.Model):
    """Aggregated term results for students"""
    __tablename__ = 'term_results'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    class_subject_id = db.Column(db.Integer, db.ForeignKey('class_subjects.id'), nullable=False)
    total_score = db.Column(db.Float)  # Sum of all CA + Exams
    grade = db.Column(db.String(5))
    remark = db.Column(db.String(50))
    position_in_subject = db.Column(db.Integer)  # Rank in this subject
    teacher_comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='term_results')
    term = db.relationship('Term', backref='term_results')
    class_subject = db.relationship('ClassSubject', backref='term_results')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'term_id', 'class_subject_id', name='unique_term_result'),
    )
    
    def __repr__(self):
        return f'<TermResult {self.student.full_name} - {self.class_subject.subject.name}: {self.total_score}>'


class TermSummary(db.Model):
    """Overall term summary for a student"""
    __tablename__ = 'term_summaries'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('student_enrollments.id'), nullable=False)
    total_subjects = db.Column(db.Integer)
    subjects_passed = db.Column(db.Integer)
    subjects_failed = db.Column(db.Integer)
    total_score = db.Column(db.Float)
    average_score = db.Column(db.Float)
    position_in_class = db.Column(db.Integer)
    position_in_arm = db.Column(db.Integer)
    attendance_percentage = db.Column(db.Float)
    teacher_comment = db.Column(db.Text)  # Form teacher comment
    principal_comment = db.Column(db.Text)
    promoted = db.Column(db.Boolean, default=None)  # NULL = pending, True/False = decided
    next_class = db.Column(db.String(50))  # For tracking promotion destination
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='term_summaries')
    term = db.relationship('Term', backref='term_summaries')
    enrollment = db.relationship('StudentEnrollment', backref='term_summary')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'term_id', name='unique_term_summary'),
    )
    
    def __repr__(self):
        return f'<TermSummary {self.student.full_name} - {self.term.name}: {self.average_score}>'


# ============================================================================
# TIMETABLE SYSTEM
# ============================================================================

class TimetableSlot(db.Model):
    """Period/slot definitions for the school day"""
    __tablename__ = 'timetable_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    slot_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3...
    name = db.Column(db.String(50))  # "Period 1", "Break", etc.
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_break = db.Column(db.Boolean, default=False)
    duration_minutes = db.Column(db.Integer)  # Auto-calculated or manual
    order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    timetable_entries = db.relationship('ClassTimetable', backref='slot', lazy='dynamic')
    
    def __repr__(self):
        return f'<TimetableSlot {self.name} ({self.start_time}-{self.end_time})>'


class ClassTimetable(db.Model):
    """Timetable entries for each class arm"""
    __tablename__ = 'class_timetables'
    
    id = db.Column(db.Integer, primary_key=True)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('timetable_slots.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 1=Tuesday, ..., 4=Friday
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)  # NULL for breaks
    teacher_name = db.Column(db.String(100))
    room = db.Column(db.String(50))  # Optional room/venue
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    class_arm_assignment = db.relationship('ClassArmAssignment', backref='timetable_entries')
    subject = db.relationship('Subject', backref='timetable_entries')
    
    @property
    def day_name(self):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[self.day_of_week] if 0 <= self.day_of_week < 7 else 'Unknown'
    
    __table_args__ = (
        db.UniqueConstraint('class_arm_assignment_id', 'slot_id', 'day_of_week', name='unique_timetable_entry'),
    )
    
    def __repr__(self):
        return f'<ClassTimetable {self.class_arm_assignment.display_name} - {self.day_name} {self.slot.name}>'


# ============================================================================
# PROMOTION SYSTEM
# ============================================================================

class PromotionRule(db.Model):
    """Promotion rules and stream criteria"""
    __tablename__ = 'promotion_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    from_class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    to_class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    stream_name = db.Column(db.String(50))  # "Science", "Arts", "Social Sciences", NULL for basic
    min_average = db.Column(db.Float, nullable=False)  # Minimum average score
    required_subjects = db.Column(db.Text)  # JSON list of subject IDs to consider
    priority = db.Column(db.Integer, default=0)  # Higher = checked first (Science before Arts)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    from_class = db.relationship('SchoolClass', foreign_keys=[from_class_id], backref='promotion_rules_from')
    to_class = db.relationship('SchoolClass', foreign_keys=[to_class_id], backref='promotion_rules_to')
    
    def get_required_subjects(self):
        """Get list of required subject IDs"""
        import json
        if self.required_subjects:
            return json.loads(self.required_subjects)
        return []
    
    def set_required_subjects(self, subject_ids):
        """Set required subject IDs"""
        import json
        self.required_subjects = json.dumps(subject_ids)
    
    def __repr__(self):
        stream = f" ({self.stream_name})" if self.stream_name else ""
        return f'<PromotionRule {self.from_class.name} → {self.to_class.name}{stream}>'


class PromotionRecord(db.Model):
    """Record of student promotions"""
    __tablename__ = 'promotion_records'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    from_session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=False)
    to_session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=False)
    from_class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    to_class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'), nullable=False)
    stream = db.Column(db.String(50))  # Science, Arts, etc.
    average_score = db.Column(db.Float)
    status = db.Column(db.String(20))  # "promoted", "repeated", "graduated", "withdrawn"
    is_manual = db.Column(db.Boolean, default=False)  # Admin override
    promoted_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='promotion_records')
    from_session = db.relationship('AcademicSession', foreign_keys=[from_session_id])
    to_session = db.relationship('AcademicSession', foreign_keys=[to_session_id])
    from_class = db.relationship('SchoolClass', foreign_keys=[from_class_id])
    to_class = db.relationship('SchoolClass', foreign_keys=[to_class_id])
    
    def __repr__(self):
        return f'<PromotionRecord {self.student.full_name}: {self.from_class.name} → {self.to_class.name}>'


# ============================================================================
# USER AUTHENTICATION
# ============================================================================

class User(db.Model):
    """Enhanced User accounts for the system with role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='teacher')  # super_admin, admin, teacher, staff, readonly
    # JSON list of module keys this (non-admin) user may access. Empty/None =>
    # fall back to the role's default module set. Admins ignore this (see all).
    allowed_modules = db.Column(db.Text)
    # When True, the user may browse but cannot create/edit/delete anything
    # (enforced globally for unsafe HTTP methods). The 'readonly' role implies this too.
    view_only = db.Column(db.Boolean, default=False)
    # Multi-branch scope: 'central' users see every branch (Director of Studies,
    # Exams & Standards, IT); 'branch' users are limited to their own branch_id.
    scope = db.Column(db.String(10), default='branch')
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    teacher_profile = db.relationship('Teacher', backref='user', uselist=False, cascade='all, delete-orphan')
    created_by = db.relationship('User', remote_side=[id], backref='created_users')
    branch = db.relationship('Branch')

    @property
    def is_central(self):
        """A central user sees across all branches (not limited to branch_id)."""
        return self.scope == 'central' or self.role in ('super_admin', 'admin')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    @property
    def module_list(self):
        """The explicit module keys granted to this user (may be empty)."""
        import json
        if not self.allowed_modules:
            return []
        try:
            v = json.loads(self.allowed_modules)
            return v if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []

    def set_modules(self, keys):
        import json
        self.allowed_modules = json.dumps(list(keys)) if keys else None

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'
    
    @property
    def is_admin(self):
        return self.role in ('super_admin', 'admin')
    
    @property
    def is_teacher(self):
        return self.role == 'teacher'
    
    @property
    def can_manage_users(self):
        return self.role in ('super_admin', 'admin')
    
    def get_display_role(self):
        """Human-readable role name"""
        roles = {
            'super_admin': 'Super Admin',
            'admin': 'Admin', 
            'teacher': 'Teacher',
            'readonly': 'View Only'
        }
        return roles.get(self.role, self.role.title())
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Teacher(db.Model):
    """Teacher profile linked to User"""
    __tablename__ = 'teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    employee_id = db.Column(db.String(20), unique=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'))

    # Permissions
    can_mark_attendance = db.Column(db.Boolean, default=True)
    can_enter_results = db.Column(db.Boolean, default=False)
    can_edit_results = db.Column(db.Boolean, default=False)
    can_view_student_details = db.Column(db.Boolean, default=True)
    can_print_reports = db.Column(db.Boolean, default=True)
    
    # Additional info
    qualification = db.Column(db.String(200))
    date_joined = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    class_assignments = db.relationship('TeacherClassAssignment', backref='teacher', 
                                        lazy='dynamic', cascade='all, delete-orphan')
    subject_assignments = db.relationship('TeacherSubjectAssignment', backref='teacher', 
                                          lazy='dynamic', cascade='all, delete-orphan')
    
    @staticmethod
    def generate_employee_id():
        """Generate unique employee ID"""
        last = Teacher.query.order_by(Teacher.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f"TCH{num:04d}"
    
    def can_access_class(self, class_arm_assignment_id):
        """Check if teacher can access this class"""
        if self.class_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            is_active=True
        ).first():
            return True
        return self.subject_assignments.filter_by(
            class_arm_assignment_id=class_arm_assignment_id,
            is_active=True
        ).first() is not None
    
    def __repr__(self):
        return f'<Teacher {self.user.full_name if self.user else "Unknown"}>'


class TeacherClassAssignment(db.Model):
    """Assign teacher as form teacher of a class"""
    __tablename__ = 'teacher_class_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    is_form_teacher = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    class_arm_assignment = db.relationship('ClassArmAssignment')
    
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_arm_assignment_id', name='uq_teacher_class'),
    )


class TeacherSubjectAssignment(db.Model):
    """Assign teacher to teach a subject in a specific class"""
    __tablename__ = 'teacher_subject_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    class_arm_assignment = db.relationship('ClassArmAssignment')
    subject = db.relationship('Subject')
    
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'class_arm_assignment_id', 'subject_id', 
                          name='uq_teacher_subject_class'),
    )


class AuditLog(db.Model):
    """Records who performed sensitive/administrative actions."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100))
    role = db.Column(db.String(30))
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user}>'


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _ensure_student_exam_columns():
    """
    Lightweight migration: add the optional WAEC/JAMB enrolment columns to the
    existing ``students`` table if they are not present yet. ``db.create_all()``
    only creates missing tables, never missing columns, so older databases need
    this ALTER TABLE to pick up new fields.
    """
    from sqlalchemy import inspect, text
    try:
        existing = {c['name'] for c in inspect(db.engine).get_columns('students')}
    except Exception:
        return
    statements = []
    if 'waec_subjects' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN waec_subjects TEXT')
    if 'jamb_subjects' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN jamb_subjects TEXT')
    if 'stream' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN stream VARCHAR(20)')
    if 'jamb_target' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN jamb_target INTEGER')
    if 'portal_password_hash' not in existing:
        statements.append('ALTER TABLE students ADD COLUMN portal_password_hash VARCHAR(256)')
    try:
        subj_cols = {c['name'] for c in inspect(db.engine).get_columns('subjects')}
        if 'has_practical' not in subj_cols:
            statements.append('ALTER TABLE subjects ADD COLUMN has_practical BOOLEAN DEFAULT 1')
    except Exception:
        pass

    # message_recipients.error (added with the SMS gateway).
    try:
        mr_cols = {c['name'] for c in inspect(db.engine).get_columns('message_recipients')}
        if 'error' not in mr_cols:
            statements.append('ALTER TABLE message_recipients ADD COLUMN error TEXT')
    except Exception:
        pass

    # messages.status / scheduled_at (added with scheduled sends).
    try:
        m_cols = {c['name'] for c in inspect(db.engine).get_columns('messages')}
        if 'status' not in m_cols:
            statements.append("ALTER TABLE messages ADD COLUMN status VARCHAR(15) DEFAULT 'Draft'")
        if 'scheduled_at' not in m_cols:
            statements.append('ALTER TABLE messages ADD COLUMN scheduled_at DATETIME')
    except Exception:
        pass

    # cbt_exams time window + scaled total (added after initial release).
    try:
        ce_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_exams')}
        if 'start_time' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN start_time VARCHAR(5)')
        if 'end_time' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN end_time VARCHAR(5)')
        if 'max_score' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN max_score FLOAT')
        if 'strict_mode' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN strict_mode BOOLEAN DEFAULT 1')
        if 'violation_limit' not in ce_cols:
            statements.append('ALTER TABLE cbt_exams ADD COLUMN violation_limit INTEGER DEFAULT 3')
    except Exception:
        pass

    # cbt_attempts raw score columns.
    try:
        ca_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_attempts')}
        if 'raw_score' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN raw_score FLOAT DEFAULT 0')
        if 'raw_total' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN raw_total FLOAT DEFAULT 0')
        if 'violations' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN violations INTEGER DEFAULT 0')
        if 'paused_until' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN paused_until DATETIME')
        if 'last_seen' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN last_seen DATETIME')
        if 'ip_address' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN ip_address VARCHAR(50)')
        if 'user_agent' not in ca_cols:
            statements.append('ALTER TABLE cbt_attempts ADD COLUMN user_agent VARCHAR(255)')
    except Exception:
        pass

    # students.portal_password_plain (export student portal passwords later).
    try:
        if 'portal_password_plain' not in existing:
            statements.append('ALTER TABLE students ADD COLUMN portal_password_plain VARCHAR(60)')
    except Exception:
        pass

    # users.allowed_modules (fine-grained module permissions).
    try:
        u_cols = {c['name'] for c in inspect(db.engine).get_columns('users')}
        if 'allowed_modules' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN allowed_modules TEXT')
        if 'view_only' not in u_cols:
            statements.append('ALTER TABLE users ADD COLUMN view_only BOOLEAN DEFAULT 0')
    except Exception:
        pass

    # terms.results_published (release results to the parent/student portal).
    try:
        t_cols = {c['name'] for c in inspect(db.engine).get_columns('terms')}
        if 'results_published' not in t_cols:
            statements.append('ALTER TABLE terms ADD COLUMN results_published BOOLEAN DEFAULT 0')
    except Exception:
        pass

    # cbt question image columns (figures in questions).
    for tbl in ('cbt_questions', 'question_bank'):
        try:
            cols = {c['name'] for c in inspect(db.engine).get_columns(tbl)}
            if 'image_url' not in cols:
                statements.append(f'ALTER TABLE {tbl} ADD COLUMN image_url VARCHAR(300)')
        except Exception:
            pass

    # cbt_login_events.device_model (device name, e.g. Redmi 13C).
    try:
        le_cols = {c['name'] for c in inspect(db.engine).get_columns('cbt_login_events')}
        if 'device_model' not in le_cols:
            statements.append('ALTER TABLE cbt_login_events ADD COLUMN device_model VARCHAR(80)')
    except Exception:
        pass

    # payslips.attendance_deduction (separates auto attendance vs manual deductions).
    try:
        ps_cols = {c['name'] for c in inspect(db.engine).get_columns('payslips')}
        if 'attendance_deduction' not in ps_cols:
            statements.append('ALTER TABLE payslips ADD COLUMN attendance_deduction FLOAT DEFAULT 0')
    except Exception:
        pass

    # Multi-branch: branch_id on branch-owned tables + users.scope (Stage 1).
    for tbl in ('students', 'teachers', 'class_arm_assignments', 'staff_members', 'users'):
        try:
            cols = {c['name'] for c in inspect(db.engine).get_columns(tbl)}
            if 'branch_id' not in cols:
                statements.append(f'ALTER TABLE {tbl} ADD COLUMN branch_id INTEGER')
        except Exception:
            pass
    try:
        u_cols = {c['name'] for c in inspect(db.engine).get_columns('users')}
        if 'scope' not in u_cols:
            statements.append("ALTER TABLE users ADD COLUMN scope VARCHAR(10) DEFAULT 'branch'")
    except Exception:
        pass

    if statements:
        with db.engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))


def _seed_branches():
    """Create the default branch and assign any unbranched data to it.

    Idempotent: only seeds the branch once, only backfills NULL branch_ids.
    Existing admins become 'central' so they keep seeing every branch.
    """
    from sqlalchemy import text
    from models.models_branch import Branch
    try:
        default = Branch.get_default()
        if default is None:
            # POSYHUB_DEFAULT_BRANCH lets a fresh install name its first branch;
            # this install's existing data belongs to the "Jemila" branch.
            name = os.environ.get('POSYHUB_DEFAULT_BRANCH', 'Jemila')
            default = Branch(name=name, is_default=True, is_active=True)
            db.session.add(default)
            db.session.commit()
        bid = default.id
        with db.engine.begin() as conn:
            for tbl in ('students', 'teachers', 'class_arm_assignments',
                        'staff_members', 'users'):
                conn.execute(text(
                    f'UPDATE {tbl} SET branch_id = :bid WHERE branch_id IS NULL'),
                    {'bid': bid})
            # Existing admins keep cross-branch visibility.
            conn.execute(text(
                "UPDATE users SET scope = 'central' "
                "WHERE role IN ('super_admin', 'admin')"))
    except Exception:
        db.session.rollback()


def init_db(app):
    """Initialize database with default data"""
    with app.app_context():
        db.create_all()
        _ensure_student_exam_columns()
        _seed_branches()

        # Seed standard course admission requirements (idempotent).
        try:
            from models.analytics_models import UniversityCutoff
            from utils.cutoff_seed import seed_cutoffs
            seed_cutoffs(db, UniversityCutoff)
        except Exception:
            db.session.rollback()

        # Create default classes if none exist
        if SchoolClass.query.count() == 0:
            default_classes = [
                ('JSS1', 1, 'Junior Secondary School 1'),
                ('JSS2', 2, 'Junior Secondary School 2'),
                ('JSS3', 3, 'Junior Secondary School 3'),
                ('SSS1', 4, 'Senior Secondary School 1'),
                ('SSS2', 5, 'Senior Secondary School 2'),
                ('SSS3', 6, 'Senior Secondary School 3'),
            ]
            for name, level, desc in default_classes:
                db.session.add(SchoolClass(name=name, level=level, description=desc))
        
        # Create default arms if none exist
        if ClassArm.query.count() == 0:
            default_arms = ['Rose', 'Lily', 'Iris', 'Daisy', 'Ivy', 'Violet']
            for arm_name in default_arms:
                db.session.add(ClassArm(name=arm_name))
        
        # Create default grade scale if none exists
        if GradeScale.query.count() == 0:
            default_grades = [
                ('A+', 80, 100, 'Excellent', 5.0, 1),
                ('A', 70, 79, 'Very Good', 4.0, 2),
                ('B', 60, 69, 'Good', 3.0, 3),
                ('C', 50, 59, 'Fair', 2.0, 4),
                ('F', 0, 49, 'Fail', 0.0, 5),
            ]
            for grade, min_s, max_s, remark, points, order in default_grades:
                db.session.add(GradeScale(
                    grade=grade, min_score=min_s, max_score=max_s,
                    remark=remark, points=points, order=order
                ))
        
        # Create default school settings if none exist
        if SchoolSettings.query.count() == 0:
            default_settings = [
                ('school_name', 'My School', 'string', 'Name of the school'),
                ('school_address', '', 'string', 'School address'),
                ('school_phone', '', 'string', 'School phone number'),
                ('school_email', '', 'string', 'School email'),
                ('school_motto', '', 'string', 'School motto'),
                ('school_day_start', '08:20', 'string', 'School day start time (HH:MM)'),
                ('school_day_end', '14:10', 'string', 'School day end time (HH:MM)'),
                ('period_duration', '40', 'int', 'Duration of each period in minutes'),
                ('break_duration', '30', 'int', 'Duration of break in minutes'),
                ('periods_per_day', '8', 'int', 'Number of periods per day'),
                ('promotion_threshold', '50', 'float', 'Minimum average score for promotion'),
                ('pass_mark', '50', 'int', 'Minimum score to pass a subject'),
            ]
            for key, value, vtype, desc in default_settings:
                db.session.add(SchoolSettings(
                    key=key, value=value, value_type=vtype, description=desc
                ))
        
        # Create default assessment types if none exist
        if AssessmentType.query.count() == 0:
            default_assessments = [
                ('Holiday Assignment', 'HA', 5, 1),
                ('1st CA', 'CA1', 5, 2),
                ('2nd CA', 'CA2', 5, 3),
                ('3rd CA', 'CA3', 5, 4),
                ('Midterm/Practicals', 'MID', 10, 5),
                ('CBT/Objectives', 'CBT', 30, 6),
                ('Theory Exam', 'EXAM', 40, 7),
            ]
            for name, short, max_score, order in default_assessments:
                db.session.add(AssessmentType(
                    name=name, short_name=short, max_score=max_score, order=order
                ))

        # Seed default expense categories for the finance module.
        try:
            from models.models_finance import ExpenseCategory
            if ExpenseCategory.query.count() == 0:
                for cat in ['Salaries & Wages', 'Utilities', 'Maintenance',
                            'Teaching Materials', 'Transport', 'Examinations',
                            'Administration', 'Miscellaneous']:
                    db.session.add(ExpenseCategory(name=cat))
        except Exception:
            db.session.rollback()

        # Seed default HR departments.
        try:
            from models.models_hr import Department
            if Department.query.count() == 0:
                for d in ['Academics', 'Administration', 'Bursary / Finance',
                          'Library', 'ICT', 'Security', 'Support / Cleaning', 'Health']:
                    db.session.add(Department(name=d))
        except Exception:
            db.session.rollback()

        # Seed default parent-communication templates.
        try:
            from models.models_comms import MessageTemplate
            if MessageTemplate.query.count() == 0:
                seed_templates = [
                    ('Fee Reminder', 'Fees',
                     'Dear {parent}, this is a reminder that {first_name} ({class}) '
                     'has an outstanding fee balance of {balance} for {term}. '
                     'Kindly make payment. Thank you. - {school}'),
                    ('Absence Notice', 'Attendance',
                     'Dear {parent}, our records show {first_name} ({class}) was '
                     'absent today. Please contact the school if this is unexpected. - {school}'),
                    ('Resumption Notice', 'General',
                     'Dear Parent, this is to inform you that school resumes on [DATE]. '
                     'Please ensure {first_name} resumes promptly. - {school}'),
                    ('PTA Meeting', 'Event',
                     'Dear Parent of {first_name} ({class}), there will be a PTA '
                     'meeting on [DATE] by [TIME]. Your presence is highly valued. - {school}'),
                    ('Result Notification', 'General',
                     'Dear {parent}, {first_name}\'s {term} result is now available. '
                     'Kindly visit the school to collect the report card. - {school}'),
                ]
                for name, cat, body in seed_templates:
                    db.session.add(MessageTemplate(name=name, category=cat, body=body))
        except Exception:
            db.session.rollback()

        # Create default admin user if none exists
        if User.query.count() == 0:
            admin = User(
                username='admin',
                email='admin@school.com',
                full_name='Administrator',
                role='admin'
            )
            admin.set_password('posyhubcomng')  # Default password
            db.session.add(admin)
        
        db.session.commit()


# ============================================================================
# TIMETABLE GENERATOR MODELS (Separate from main timetable)
# ============================================================================

class GenTeacher(db.Model):
    """Teachers for timetable generation"""
    __tablename__ = 'gen_teachers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    staff_id = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    max_periods_per_day = db.Column(db.Integer, default=6)
    max_periods_per_week = db.Column(db.Integer, default=30)
    preferred_time = db.Column(db.String(20), default='any')  # 'morning', 'afternoon', 'any'
    is_part_time = db.Column(db.Boolean, default=False)
    available_days = db.Column(db.String(20))  # Comma-separated: "0,1,2,3,4" for Mon-Fri
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subjects = db.relationship('GenTeacherSubject', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('GenTeacherAssignment', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    availability = db.relationship('GenTeacherAvailability', backref='teacher', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def available_days_list(self):
        if self.available_days:
            return [int(d) for d in self.available_days.split(',') if d.strip()]
        return [0, 1, 2, 3, 4]  # Default all days
    
    def __repr__(self):
        return f'<GenTeacher {self.name}>'


class GenTeacherAvailability(db.Model):
    """Teacher availability - which periods they're NOT available"""
    __tablename__ = 'gen_teacher_availability'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday to 4=Friday
    period_number = db.Column(db.Integer, nullable=False)
    is_available = db.Column(db.Boolean, default=False)  # False = NOT available
    reason = db.Column(db.String(100))  # Optional reason
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'day_of_week', 'period_number'),)


class GenTeacherSubject(db.Model):
    """Subjects a teacher can teach"""
    __tablename__ = 'gen_teacher_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    
    # Relationship to get subject details
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'subject_id'),)


class GenSubjectConfig(db.Model):
    """Subject configuration for timetable generation - GLOBAL defaults"""
    __tablename__ = 'gen_subject_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)  # Changed to gen_subjects
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    periods_per_week = db.Column(db.Integer, default=4)  # Default periods
    needs_double_period = db.Column(db.Boolean, default=False)
    double_period_count = db.Column(db.Integer, default=0)  # How many double periods
    preferred_time = db.Column(db.String(20), default='any')  # 'morning', 'afternoon', 'any'
    category = db.Column(db.String(20), default='core')  # 'core', 'science', 'arts', 'commercial'
    not_first_period = db.Column(db.Boolean, default=False)
    not_last_period = db.Column(db.Boolean, default=False)
    color = db.Column(db.String(7), default='#4472C4')  # Hex color for display
    room_id = db.Column(db.Integer, db.ForeignKey('gen_rooms.id'))  # Required room/lab
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    subject = db.relationship('GenSubject')
    room = db.relationship('GenRoom')
    
    __table_args__ = (db.UniqueConstraint('subject_id', 'school_level'),)


class GenSubject(db.Model):
    """Subjects for timetable generation - separate from academic subjects"""
    __tablename__ = 'gen_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(20))
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    category = db.Column(db.String(50))  # Science, Arts, Commercial, General, Vocational
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    __table_args__ = (db.UniqueConstraint('name', 'school_level'),)
    
    def __repr__(self):
        return f'<GenSubject {self.name} ({self.school_level})>'


class GenClassSubjectConfig(db.Model):
    """Per-class subject configuration - overrides global defaults"""
    __tablename__ = 'gen_class_subject_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    is_enabled = db.Column(db.Boolean, default=True)  # Does this class take this subject?
    periods_per_week = db.Column(db.Integer, default=4)
    needs_double_period = db.Column(db.Boolean, default=False)
    double_period_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    class_config = db.relationship('GenClassConfig', backref='subject_configs')
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('class_config_id', 'subject_id'),)


class GenRoom(db.Model):
    """Rooms/Venues for timetable generation"""
    __tablename__ = 'gen_rooms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    short_name = db.Column(db.String(10))
    room_type = db.Column(db.String(20), default='classroom')  # classroom, lab, hall, field
    capacity = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    def __repr__(self):
        return f'<GenRoom {self.name}>'


class GenStream(db.Model):
    """Stream definitions (Science, Arts, Commercial)"""
    __tablename__ = 'gen_streams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    short_name = db.Column(db.String(10))
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subjects = db.relationship('GenStreamSubject', backref='stream', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<GenStream {self.name}>'


class GenStreamSubject(db.Model):
    """Subjects belonging to each stream with stream-specific period configuration"""
    __tablename__ = 'gen_stream_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    stream_id = db.Column(db.Integer, db.ForeignKey('gen_streams.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    is_compulsory = db.Column(db.Boolean, default=True)  # Compulsory within stream
    
    # Stream-specific period configuration (overrides global subject config)
    periods_per_week = db.Column(db.Integer, nullable=True)  # If NULL, use global config
    needs_double_period = db.Column(db.Boolean, nullable=True)  # If NULL, use global config
    double_period_count = db.Column(db.Integer, nullable=True)  # If NULL, use global config
    
    # Relationship
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('stream_id', 'subject_id'),)


class GenClassConfig(db.Model):
    """Class configuration for generation"""
    __tablename__ = 'gen_class_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(20), nullable=False)  # SSS1, SSS2, SSS3, JSS1, JSS2, JSS3
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    num_arms = db.Column(db.Integer, default=1)
    arm_names = db.Column(db.String(200))  # Comma-separated: "Iris,Rose,Lily,Tulip"
    has_streams = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    arm_streams = db.relationship('GenClassArmStream', backref='class_config', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def arm_list(self):
        """Return list of arm names"""
        if self.arm_names:
            return [a.strip() for a in self.arm_names.split(',')]
        return []
    
    def __repr__(self):
        return f'<GenClassConfig {self.class_name}>'


class GenClassArmStream(db.Model):
    """Which stream each class arm belongs to"""
    __tablename__ = 'gen_class_arm_streams'
    
    id = db.Column(db.Integer, primary_key=True)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    arm_name = db.Column(db.String(50), nullable=False)  # e.g., "Iris"
    stream_id = db.Column(db.Integer, db.ForeignKey('gen_streams.id'))
    
    # Relationship
    stream = db.relationship('GenStream')
    
    __table_args__ = (db.UniqueConstraint('class_config_id', 'arm_name'),)


class GenClassStreamSubject(db.Model):
    """Class-specific stream subject period configuration
    Allows SSS2 Science to have different periods than SSS3 Science for the same subject
    """
    __tablename__ = 'gen_class_stream_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    stream_id = db.Column(db.Integer, db.ForeignKey('gen_streams.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    
    # Class-stream specific period configuration
    periods_per_week = db.Column(db.Integer, nullable=False)
    needs_double_period = db.Column(db.Boolean, default=False)
    double_period_count = db.Column(db.Integer, default=0)
    is_enabled = db.Column(db.Boolean, default=True)  # Can disable subject for this class-stream
    
    # Relationships
    class_config = db.relationship('GenClassConfig')
    stream = db.relationship('GenStream')
    subject = db.relationship('GenSubject')
    
    __table_args__ = (db.UniqueConstraint('class_config_id', 'stream_id', 'subject_id'),)


class GenTeacherAssignment(db.Model):
    """Which teacher teaches which subject to which class-arm"""
    __tablename__ = 'gen_teacher_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    class_config_id = db.Column(db.Integer, db.ForeignKey('gen_class_configs.id'), nullable=False)
    arm_name = db.Column(db.String(50))  # Specific arm, or NULL for all arms
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subject = db.relationship('GenSubject')
    class_config = db.relationship('GenClassConfig')
    
    __table_args__ = (db.UniqueConstraint('teacher_id', 'subject_id', 'class_config_id', 'arm_name'),)


class GenTimetableRule(db.Model):
    """Timetable generation rules"""
    __tablename__ = 'gen_timetable_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(50), nullable=False)
    # Types: 'no_repeat_same_day', 'max_consecutive', 'break_after_period', etc.
    value = db.Column(db.String(100))
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'))  # If rule is subject-specific
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    subject = db.relationship('GenSubject')


class GenTimetableResult(db.Model):
    """Generated timetable results"""
    __tablename__ = 'gen_timetable_results'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(50), nullable=False)  # Groups results from same generation
    school_level = db.Column(db.String(10), default='sss')  # 'jss' or 'sss'
    class_name = db.Column(db.String(20), nullable=False)
    arm_name = db.Column(db.String(50), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday to 4=Friday
    period_number = db.Column(db.Integer, nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'))
    teacher_id = db.Column(db.Integer, db.ForeignKey('gen_teachers.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('gen_rooms.id'))
    is_double_period = db.Column(db.Boolean, default=False)
    is_locked = db.Column(db.Boolean, default=False)  # Locked slots won't change on regeneration
    generated_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subject = db.relationship('GenSubject')
    teacher = db.relationship('GenTeacher')
    room = db.relationship('GenRoom')
    
    @property
    def day_name(self):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        return days[self.day_of_week] if 0 <= self.day_of_week < 5 else ''


class GenSettings(db.Model):
    """Generator settings including school info for printing"""
    __tablename__ = 'gen_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(50), nullable=False, unique=True)
    setting_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    
    @staticmethod
    def get(key, default=None):
        setting = GenSettings.query.filter_by(setting_key=key).first()
        return setting.setting_value if setting else default
    
    @staticmethod
    def set(key, value):
        setting = GenSettings.query.filter_by(setting_key=key).first()
        if setting:
            setting.setting_value = value
        else:
            setting = GenSettings(setting_key=key, setting_value=value)
            db.session.add(setting)
        db.session.commit()


# ============================================================================
# TIMETABLE CONSTRAINT RULES (Database-driven)
# ============================================================================

class GenSubjectClashRule(db.Model):
    """
    Rules for subjects that must NOT be scheduled at the same time.
    Used for combined classes where different student groups take different subjects simultaneously.
    Example: Geography for SSS3 Iris should not clash with Literature (because Arts students do Lit while Commercial do Geo)
    """
    __tablename__ = 'gen_subject_clash_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # Descriptive name for the rule
    description = db.Column(db.Text)  # Explanation of why this rule exists
    
    # Source subject (the one we're protecting)
    source_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    source_class_name = db.Column(db.String(20), nullable=False)  # e.g., "SSS3"
    source_arm_name = db.Column(db.String(50))  # e.g., "Iris", or NULL for all arms
    
    # Target subject (the one that must not clash with source)
    target_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    target_class_name = db.Column(db.String(20))  # e.g., "SSS1", or NULL for all classes
    target_arm_name = db.Column(db.String(50))  # e.g., "Iris", or NULL for all arms
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    source_subject = db.relationship('GenSubject', foreign_keys=[source_subject_id])
    target_subject = db.relationship('GenSubject', foreign_keys=[target_subject_id])
    
    def __repr__(self):
        return f'<GenSubjectClashRule {self.name}>'


class GenCombinedClassRule(db.Model):
    """
    Rules for combined classes where a teacher "shadows" another subject.
    When the shadow subject is scheduled, the teacher is also occupied.
    Used to ensure the teacher doesn't get 3 consecutive periods across both subjects.
    Example: Literature teacher shadows Geography for SSS3 Iris (same time slot)
    """
    __tablename__ = 'gen_combined_class_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # The subject being shadowed (e.g., Geography)
    shadow_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    shadow_class_name = db.Column(db.String(20), nullable=False)  # e.g., "SSS3"
    shadow_arm_name = db.Column(db.String(50))  # e.g., "Iris"
    
    # The teacher's own subject (e.g., Literature) - used to find the teacher
    teacher_subject_id = db.Column(db.Integer, db.ForeignKey('gen_subjects.id'), nullable=False)
    teacher_class_name = db.Column(db.String(20), nullable=False)  # The class where teacher is assigned
    teacher_arm_name = db.Column(db.String(50))  # The arm where teacher is assigned
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    shadow_subject = db.relationship('GenSubject', foreign_keys=[shadow_subject_id])
    teacher_subject = db.relationship('GenSubject', foreign_keys=[teacher_subject_id])
    
    def __repr__(self):
        return f'<GenCombinedClassRule {self.name}>'
