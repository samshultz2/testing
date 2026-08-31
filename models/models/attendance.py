"""SQLAlchemy models — attendance (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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
