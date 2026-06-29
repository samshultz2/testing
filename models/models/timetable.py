"""SQLAlchemy models — timetable (split from the former models/models.py).
Base names (db, local_now, EncryptedString, …) come from the package __init__;
sibling models are referenced lazily inside methods as in the original."""
from models.models import *  # noqa: F401,F403


class TimetableSlot(db.Model):
    """Period/slot definitions for the school day"""
    __tablename__ = 'timetable_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    slot_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3...
    name = db.Column(db.String(50))  # "Period 1", "Break", etc.
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_break = db.Column(db.Boolean, default=False)
    duration_minutes = db.Column(db.Integer)  # Auto-calculated or manual
    order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    timetable_entries = db.relationship('ClassTimetable', backref='slot', lazy='dynamic')
    
    def __repr__(self):
        return f'<TimetableSlot {self.name} ({self.start_time}-{self.end_time})>'


class ClassTimetable(db.Model):
    """Timetable entries for each class arm"""
    __tablename__ = 'class_timetables'
    
    id = db.Column(db.Integer, primary_key=True)
    class_arm_assignment_id = db.Column(db.Integer, db.ForeignKey('class_arm_assignments.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('timetable_slots.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 1=Tuesday, ..., 4=Friday
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)  # NULL for breaks
    teacher_name = db.Column(db.String(100))
    room = db.Column(db.String(50))  # Optional room/venue
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=local_now)
    
    # Relationships
    class_arm_assignment = db.relationship('ClassArmAssignment', backref='timetable_entries')
    subject = db.relationship('Subject', backref='timetable_entries')
    
    @property
    def day_name(self):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[self.day_of_week] if 0 <= self.day_of_week < 7 else 'Unknown'
    
    __table_args__ = (
        db.UniqueConstraint('class_arm_assignment_id', 'slot_id', 'day_of_week', name='unique_timetable_entry'),
    )
    
    def __repr__(self):
        return f'<ClassTimetable {self.class_arm_assignment.display_name} - {self.day_name} {self.slot.name}>'


class TimetableBackup(db.Model):
    """A point-in-time snapshot of the per-class timetables (ClassTimetable),
    taken before a destructive change (e.g. applying a generated batch) so the
    previous timetable can always be restored. Stored as JSON to stay
    schema-light."""
    __tablename__ = 'timetable_backups'

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'), nullable=True)
    label = db.Column(db.String(200))
    entry_count = db.Column(db.Integer, default=0)
    data = db.Column(db.Text)  # JSON list of entry dicts
    created_at = db.Column(db.DateTime, default=local_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    term = db.relationship('Term')

    def __repr__(self):
        return f'<TimetableBackup {self.id} {self.label!r} ({self.entry_count})>'
