"""SQLAlchemy models — promotion (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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
