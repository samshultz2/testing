"""Tables behind the Insights page: weekly at-risk snapshots (to show who
moved into / out of risk) and frozen exam-year headline numbers (so year
comparisons stay stable even if student records are edited later)."""
from datetime import datetime

from models.models import db


class AtRiskSnapshot(db.Model):
    """One row per student flagged at risk in a given week."""
    __tablename__ = 'at_risk_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    week_start = db.Column(db.Date, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    status = db.Column(db.String(20))                 # NOT_READY | AT_RISK | CONDITIONAL
    blockers = db.Column(db.Text)                     # JSON list of reasons
    class_label = db.Column(db.String(60))
    created_at = db.Column(db.DateTime, default=datetime.now)

    __table_args__ = (db.UniqueConstraint('week_start', 'student_id', name='uq_at_risk_week_student'),)


class ExamYearSnapshot(db.Model):
    """Frozen headline numbers for one exam year (and branch, or all)."""
    __tablename__ = 'exam_year_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    exam_year = db.Column(db.Integer, nullable=False, index=True)
    branch_id = db.Column(db.Integer)                 # NULL = all branches
    data = db.Column(db.Text, nullable=False)         # JSON: headline metrics
    frozen_at = db.Column(db.DateTime, default=datetime.now)
    frozen_by = db.Column(db.String(120))

    __table_args__ = (db.UniqueConstraint('exam_year', 'branch_id', name='uq_exam_year_snapshot'),)


_ensured = set()


def ensure_insights_schema():
    """Create the tables on the bound DB if missing (once per engine)."""
    try:
        engine = db.engine
    except Exception:
        return
    key = str(getattr(engine, 'url', 'default'))
    if key in _ensured:
        return
    try:
        for model in (AtRiskSnapshot, ExamYearSnapshot):
            model.__table__.create(bind=engine, checkfirst=True)
        _ensured.add(key)
    except Exception:
        db.session.rollback()
