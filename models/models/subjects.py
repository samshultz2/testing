"""SQLAlchemy models — subjects (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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


class BehaviouralTrait(db.Model):
    """Configurable affective/behavioural traits shown on the report sheet."""
    __tablename__ = 'behavioural_traits'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(40), unique=True, nullable=False)   # stable id used in ratings
    label = db.Column(db.String(80), nullable=False)
    order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<BehaviouralTrait {self.key}>'


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
