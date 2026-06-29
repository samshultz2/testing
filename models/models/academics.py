"""SQLAlchemy models — academics (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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
    section = db.Column(db.String(20))  # nursery / primary / junior / senior
    description = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    assignments = db.relationship('ClassArmAssignment', backref='school_class', lazy='dynamic')
    
    def __repr__(self):
        return f'<SchoolClass {self.name}>'


class ClassArm(db.Model):
    """Class arm (Rose, Lily, etc.).

    A school that doesn't stream its classes (just SSS1/SSS2/SSS3, no arms) uses
    a single hidden "General" arm (``is_default``): every class gets one
    assignment on it, and its name is omitted everywhere a class is shown."""
    __tablename__ = 'class_arms'

    DEFAULT_NAME = 'General'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    description = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    # The single auto "no-arm" arm for schools that don't use streams.
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=local_now)

    # Relationships
    assignments = db.relationship('ClassArmAssignment', backref='arm', lazy='dynamic')

    @staticmethod
    def default():
        """Return (creating if needed) the hidden 'General' arm used by schools
        that don't stream their classes."""
        arm = ClassArm.query.filter_by(is_default=True).first()
        if arm is None:
            # Reuse a same-named arm if one exists (e.g. created before this flag).
            arm = ClassArm.query.filter_by(name=ClassArm.DEFAULT_NAME).first()
            if arm is None:
                arm = ClassArm(name=ClassArm.DEFAULT_NAME,
                               description='Default arm (schools without streams)')
                db.session.add(arm)
            arm.is_default = True
            arm.is_active = True
            db.session.flush()
        return arm

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
        """Class + arm, e.g. 'JSS1 Rose'. The hidden default ('General') arm is
        omitted, so an arm-less school just sees 'JSS1'."""
        cls = self.school_class.name if self.school_class else ''
        if self.arm and not getattr(self.arm, 'is_default', False):
            return f"{cls} {self.arm.name}"
        return cls

    @property
    def arm_label(self):
        """Just the arm name, or '' for the hidden default ('General') arm.
        Use this anywhere the arm is shown on its own (badges, columns, CSV)."""
        if self.arm and not getattr(self.arm, 'is_default', False):
            return self.arm.name
        return ''

    @property
    def full_display_name(self):
        """display_name plus the term."""
        term = self.term.full_name if self.term else ''
        return f"{self.display_name} - {term}"
    
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
