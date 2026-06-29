"""SQLAlchemy models — settings (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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


class AuditLog(db.Model):
    """Records who performed sensitive/administrative actions."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(100))
    role = db.Column(db.String(30))
    action = db.Column(db.String(80), nullable=False)
    # What the action was performed on (for "who did what to what").
    target_type = db.Column(db.String(40))     # e.g. 'student', 'payment'
    target_id = db.Column(db.Integer)
    target_label = db.Column(db.String(150))   # human label, e.g. the name
    branch_id = db.Column(db.Integer)          # branch context at the time
    detail = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=local_now)

    def __repr__(self):
        return f'<AuditLog {self.action} by {self.user}>'


class RateLimitHit(db.Model):
    """One row per throttled attempt (login/abuse). Shared across workers so the
    rate limit can't be bypassed by spreading attempts. `ts` is epoch seconds."""
    __tablename__ = 'rate_limit_hits'

    id = db.Column(db.Integer, primary_key=True)
    rkey = db.Column(db.String(120), nullable=False)
    ts = db.Column(db.Float, nullable=False)
