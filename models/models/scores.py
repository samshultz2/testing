"""SQLAlchemy models — scores (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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
    # JSON {trait_key: 1..5} of affective/behavioural ratings for the report sheet.
    affective = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    @property
    def affective_map(self):
        import json
        if not self.affective:
            return {}
        try:
            v = json.loads(self.affective)
            return v if isinstance(v, dict) else {}
        except (ValueError, TypeError):
            return {}

    def set_affective(self, mapping):
        import json
        clean = {k: int(v) for k, v in (mapping or {}).items()
                 if str(v).isdigit() and 1 <= int(v) <= 5}
        self.affective = json.dumps(clean) if clean else None

    # Relationships
    student = db.relationship('Student', backref='term_summaries')
    term = db.relationship('Term', backref='term_summaries')
    enrollment = db.relationship('StudentEnrollment', backref='term_summary')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'term_id', name='unique_term_summary'),
    )
    
    def __repr__(self):
        return f'<TermSummary {self.student.full_name} - {self.term.name}: {self.average_score}>'
