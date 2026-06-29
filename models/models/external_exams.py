"""SQLAlchemy models — external_exams (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


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
