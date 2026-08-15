"""
Extended models for academic analytics: WAEC<->JAMB correlation, university
cut-offs, persisted risk assessments / predictions, and an analytics cache.
"""
from datetime import datetime, date
from models.models import db, local_now



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
            if cache.expires_at and cache.expires_at < local_now():
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
            cache.expires_at = local_now() + timedelta(seconds=ttl_seconds)
        else:
            cache = AnalyticsCache(
                cache_key=key,
                cache_value=json.dumps(value),
                expires_at=local_now() + timedelta(seconds=ttl_seconds)
            )
            db.session.add(cache)
        db.session.commit()


class WaecGradeModel(db.Model):
    """A trained per-(branch, subject) ordinal model for predicting real WAEC
    grade bands from mock-WAEC scores. Stores the fitted parameters (JSON) plus
    the metadata the auto-selector and UI need: pair count and cross-validated
    Ranked Probability Score for the model vs the calibration bins. Re-fit (one
    row per branch+subject, overwritten) whenever a new cohort's results land."""
    __tablename__ = 'waec_grade_models'

    id = db.Column(db.Integer, primary_key=True)
    # branch_id NULL = a pooled/global model (not used by default — models are
    # per-branch — but kept so pooling can be switched on without a schema change).
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    subject = db.Column(db.String(50), nullable=False)
    params = db.Column(db.Text, nullable=False)        # JSON: mean/std/base/deltas/beta
    n = db.Column(db.Integer)                           # training pairs
    cv_rps = db.Column(db.Float)                        # model CV Ranked Probability Score
    cv_rps_bins = db.Column(db.Float)                  # bins CV RPS (for comparison)
    trained_at = db.Column(db.DateTime, default=local_now)

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'subject', name='unique_waec_model_branch_subject'),
    )

    def __repr__(self):
        return f'<WaecGradeModel {self.subject} branch={self.branch_id} n={self.n}>'
