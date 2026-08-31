"""Attendance intervention records.

When a student's attendance drops, staff open an intervention, log follow-ups
(notes, parent meetings, counselling) and track whether attendance recovers.
Additive tables — never touches the marking write path."""
from models.models import db, local_now


class AttendanceIntervention(db.Model):
    __tablename__ = 'attendance_interventions'

    STATUSES = ['Open', 'In progress', 'Escalated', 'Resolved', 'Closed']

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    reason = db.Column(db.String(200))
    status = db.Column(db.String(15), default='Open')
    baseline_pct = db.Column(db.Float)          # attendance % when opened
    resolved_pct = db.Column(db.Float)          # attendance % at resolution
    outcome = db.Column(db.Text)
    opened_by = db.Column(db.String(100))
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    student = db.relationship('Student')
    notes = db.relationship('InterventionNote', backref='intervention',
                            lazy='dynamic', cascade='all, delete-orphan')

    @property
    def is_open(self):
        return self.status in ('Open', 'In progress', 'Escalated')


class InterventionNote(db.Model):
    """A follow-up on an intervention — a note, a parent meeting, a counselling
    session or a scheduled next action."""
    __tablename__ = 'attendance_intervention_notes'

    KINDS = ['Note', 'Parent meeting', 'Counselling', 'Call', 'Follow-up']

    id = db.Column(db.Integer, primary_key=True)
    intervention_id = db.Column(db.Integer, db.ForeignKey('attendance_interventions.id'),
                                nullable=False, index=True)
    kind = db.Column(db.String(20), default='Note')
    body = db.Column(db.Text)
    next_action = db.Column(db.String(200))
    next_date = db.Column(db.Date)
    author = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)
