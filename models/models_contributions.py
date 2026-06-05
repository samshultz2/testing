"""
Contribution Models - SSS3 Graduation Fund Tracking
Session-based: Each academic session has its own contribution records
"""
from models.models import db, local_now


class ContributionSettings(db.Model):
    """Settings for contribution tracking - per session"""
    __tablename__ = 'contribution_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=True)
    setting_key = db.Column(db.String(50), nullable=False)
    setting_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Unique constraint on session_id + setting_key
    __table_args__ = (db.UniqueConstraint('session_id', 'setting_key', name='uq_session_setting'),)
    
    @staticmethod
    def get(key, default=None, session_id=None):
        """Get setting value, optionally for specific session"""
        query = ContributionSettings.query.filter_by(setting_key=key)
        if session_id:
            query = query.filter_by(session_id=session_id)
        else:
            query = query.filter_by(session_id=None)
        setting = query.first()
        return setting.setting_value if setting else default
    
    @staticmethod
    def set(key, value, session_id=None):
        """Set setting value, optionally for specific session"""
        query = ContributionSettings.query.filter_by(setting_key=key)
        if session_id:
            query = query.filter_by(session_id=session_id)
        else:
            query = query.filter_by(session_id=None)
        setting = query.first()
        
        if setting:
            setting.setting_value = str(value)
        else:
            setting = ContributionSettings(
                session_id=session_id,
                setting_key=key,
                setting_value=str(value)
            )
            db.session.add(setting)
        db.session.commit()


class ContributionPayment(db.Model):
    """Individual payment records for student contributions"""
    __tablename__ = 'contribution_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    received_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    student = db.relationship('Student', backref=db.backref('contributions', lazy='dynamic'))
    session = db.relationship('AcademicSession', backref=db.backref('contribution_payments', lazy='dynamic'))
    
    def __repr__(self):
        return f'<ContributionPayment {self.student_id}: ₦{self.amount}>'


class ContributionExpense(db.Model):
    """Expenses from the contribution fund"""
    __tablename__ = 'contribution_expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('academic_sessions.id'), nullable=True)
    expense_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationship
    session = db.relationship('AcademicSession', backref=db.backref('contribution_expenses', lazy='dynamic'))
    
    def __repr__(self):
        return f'<ContributionExpense {self.description}: ₦{self.amount}>'
