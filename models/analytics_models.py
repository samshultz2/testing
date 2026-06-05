"""
Extended models for comprehensive academic analytics
Supports internal exams, performance tracking, and longitudinal analysis
"""
from datetime import datetime, date
from models.models import db, local_now


# ============================================================================
# INTERNAL EXAMINATION MODELS
# ============================================================================

class InternalExam(db.Model):
    """Internal examination definition (CA, Mid-term, Final, Mock)"""
    __tablename__ = 'internal_exams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., "First Term Exam 2024"
    exam_type = db.Column(db.String(30), nullable=False)  # CA1, CA2, MID_TERM, FINAL, MOCK
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    max_score = db.Column(db.Integer, default=100)
    weight = db.Column(db.Float, default=1.0)  # Weight for grade calculation
    exam_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    term = db.relationship('Term', backref='internal_exams')
    results = db.relationship('InternalExamResult', backref='exam', lazy='dynamic', cascade='all, delete-orphan')
    
    EXAM_TYPES = ['CA1', 'CA2', 'CA3', 'MID_TERM', 'FINAL', 'MOCK']
    
    def __repr__(self):
        return f'<InternalExam {self.name}>'


class InternalExamResult(db.Model):
    """Individual student result for internal exams"""
    __tablename__ = 'internal_exam_results'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('internal_exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(2))  # A1-F9 equivalent
    remarks = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='internal_results')
    subject = db.relationship('Subject', backref='internal_results')
    
    __table_args__ = (
        db.UniqueConstraint('exam_id', 'student_id', 'subject_id', name='unique_internal_result'),
    )
    
    @staticmethod
    def score_to_grade(score, max_score=100):
        """Convert score to WAEC-equivalent grade"""
        percentage = (score / max_score) * 100 if max_score > 0 else 0
        if percentage >= 75: return 'A1'
        elif percentage >= 70: return 'B2'
        elif percentage >= 65: return 'B3'
        elif percentage >= 60: return 'C4'
        elif percentage >= 55: return 'C5'
        elif percentage >= 50: return 'C6'
        elif percentage >= 45: return 'D7'
        elif percentage >= 40: return 'E8'
        else: return 'F9'
    
    @staticmethod
    def grade_to_points(grade):
        """Convert grade to points"""
        points = {'A1': 1, 'B2': 2, 'B3': 3, 'C4': 4, 'C5': 5, 'C6': 6, 'D7': 7, 'E8': 8, 'F9': 9}
        return points.get(grade, 9)


# ============================================================================
# PERFORMANCE TRACKING MODELS
# ============================================================================

class StudentPerformanceSnapshot(db.Model):
    """Periodic snapshot of student performance for trend analysis"""
    __tablename__ = 'student_performance_snapshots'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    
    # Aggregate metrics
    total_subjects = db.Column(db.Integer, default=0)
    average_score = db.Column(db.Float)
    average_grade_points = db.Column(db.Float)
    
    # Grade counts
    a1_count = db.Column(db.Integer, default=0)
    credit_count = db.Column(db.Integer, default=0)  # A1-C6
    pass_count = db.Column(db.Integer, default=0)    # A1-D7
    fail_count = db.Column(db.Integer, default=0)    # E8-F9
    
    # Attendance metrics
    attendance_rate = db.Column(db.Float)
    days_present = db.Column(db.Integer, default=0)
    days_absent = db.Column(db.Integer, default=0)
    
    # Risk assessment
    risk_level = db.Column(db.String(10))  # GREEN, AMBER, RED
    risk_factors = db.Column(db.Text)  # JSON list of risk factors
    
    # Rankings
    class_rank = db.Column(db.Integer)
    class_size = db.Column(db.Integer)
    
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='performance_snapshots')
    term = db.relationship('Term', backref='performance_snapshots')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'term_id', name='unique_student_term_snapshot'),
    )


class SubjectPerformanceMetrics(db.Model):
    """Subject-level performance metrics per term"""
    __tablename__ = 'subject_performance_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'))
    
    # Score metrics
    mean_score = db.Column(db.Float)
    median_score = db.Column(db.Float)
    std_deviation = db.Column(db.Float)
    min_score = db.Column(db.Float)
    max_score = db.Column(db.Float)
    
    # Grade distribution
    total_students = db.Column(db.Integer, default=0)
    a1_count = db.Column(db.Integer, default=0)
    b2_b3_count = db.Column(db.Integer, default=0)
    c4_c6_count = db.Column(db.Integer, default=0)
    d7_e8_count = db.Column(db.Integer, default=0)
    f9_count = db.Column(db.Integer, default=0)
    
    # Derived metrics
    pass_rate = db.Column(db.Float)  # A1-C6 percentage
    distinction_rate = db.Column(db.Float)  # A1-B3 percentage
    failure_rate = db.Column(db.Float)  # F9 percentage
    difficulty_index = db.Column(db.Float)  # Normalized difficulty score
    
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    subject = db.relationship('Subject', backref='performance_metrics')
    term = db.relationship('Term', backref='subject_metrics')
    school_class = db.relationship('SchoolClass', backref='subject_metrics')
    
    __table_args__ = (
        db.UniqueConstraint('subject_id', 'term_id', 'class_id', name='unique_subject_term_class_metrics'),
    )


class WAECJAMBCorrelation(db.Model):
    """Tracks correlation between WAEC and JAMB performance"""
    __tablename__ = 'waec_jamb_correlations'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_year = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(50))  # NULL for overall correlation
    
    # Correlation metrics
    correlation_coefficient = db.Column(db.Float)  # Pearson correlation
    sample_size = db.Column(db.Integer)
    
    # Predictive accuracy
    prediction_accuracy = db.Column(db.Float)  # How well WAEC predicts JAMB
    mean_waec_points = db.Column(db.Float)
    mean_jamb_score = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=local_now)
    
    __table_args__ = (
        db.UniqueConstraint('exam_year', 'subject', name='unique_waec_jamb_correlation'),
    )


class UniversityCutoff(db.Model):
    """Historical university admission cutoffs for prediction"""
    __tablename__ = 'university_cutoffs'
    
    id = db.Column(db.Integer, primary_key=True)
    university_name = db.Column(db.String(200), nullable=False)
    course_name = db.Column(db.String(200), nullable=False)
    faculty = db.Column(db.String(100))
    exam_year = db.Column(db.Integer, nullable=False)
    
    # Cutoff requirements
    jamb_cutoff = db.Column(db.Integer)
    post_utme_cutoff = db.Column(db.Float)
    aggregate_cutoff = db.Column(db.Float)
    
    # WAEC requirements
    required_subjects = db.Column(db.Text)  # JSON list
    min_credits = db.Column(db.Integer, default=5)
    
    created_at = db.Column(db.DateTime, default=local_now)
    
    __table_args__ = (
        db.UniqueConstraint('university_name', 'course_name', 'exam_year', name='unique_cutoff'),
    )


class StudentRiskAssessment(db.Model):
    """Detailed risk assessment for at-risk students"""
    __tablename__ = 'student_risk_assessments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    assessment_date = db.Column(db.Date, default=date.today)
    
    # Risk scores (0-100, higher = more risk)
    overall_risk_score = db.Column(db.Float)
    academic_risk_score = db.Column(db.Float)
    attendance_risk_score = db.Column(db.Float)
    trend_risk_score = db.Column(db.Float)
    
    # Risk classification
    risk_level = db.Column(db.String(10))  # GREEN, AMBER, RED
    
    # Risk factors (JSON)
    risk_factors = db.Column(db.Text)
    
    # Recommendations (JSON)
    recommendations = db.Column(db.Text)
    
    # Predicted outcomes
    predicted_waec_performance = db.Column(db.String(20))  # EXCELLENT, GOOD, AVERAGE, POOR
    predicted_jamb_range = db.Column(db.String(20))  # e.g., "250-300"
    
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='risk_assessments')


class AcademicPrediction(db.Model):
    """ML-based predictions for students"""
    __tablename__ = 'academic_predictions'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    prediction_type = db.Column(db.String(50), nullable=False)  # JAMB_SCORE, WAEC_GRADE, ADMISSION
    prediction_date = db.Column(db.Date, default=date.today)
    
    # Prediction details
    predicted_value = db.Column(db.String(100))
    confidence_score = db.Column(db.Float)  # 0-1
    
    # Model info
    model_version = db.Column(db.String(50))
    features_used = db.Column(db.Text)  # JSON
    
    # Explanation
    explanation = db.Column(db.Text)
    
    # Actual outcome (for model validation)
    actual_value = db.Column(db.String(100))
    prediction_accuracy = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    student = db.relationship('Student', backref='academic_predictions')


# ============================================================================
# ANALYTICS CACHE MODELS
# ============================================================================

class AnalyticsCache(db.Model):
    """Cache for expensive analytics calculations"""
    __tablename__ = 'analytics_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(200), unique=True, nullable=False)
    cache_value = db.Column(db.Text, nullable=False)  # JSON
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now)
    
    @staticmethod
    def get(key):
        """Get cached value if not expired"""
        import json
        cache = AnalyticsCache.query.filter_by(cache_key=key).first()
        if cache:
            if cache.expires_at and cache.expires_at < datetime.now():
                db.session.delete(cache)
                db.session.commit()
                return None
            return json.loads(cache.cache_value)
        return None
    
    @staticmethod
    def set(key, value, ttl_seconds=3600):
        """Set cache value with TTL"""
        import json
        from datetime import timedelta
        
        cache = AnalyticsCache.query.filter_by(cache_key=key).first()
        if cache:
            cache.cache_value = json.dumps(value)
            cache.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        else:
            cache = AnalyticsCache(
                cache_key=key,
                cache_value=json.dumps(value),
                expires_at=datetime.now() + timedelta(seconds=ttl_seconds)
            )
            db.session.add(cache)
        db.session.commit()
