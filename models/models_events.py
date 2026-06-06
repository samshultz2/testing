"""Events & Calendar — school calendar entries (holidays, exams, meetings…)."""
from datetime import date

from models.models import db, local_now


class SchoolEvent(db.Model):
    __tablename__ = 'school_events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(30), default='General')   # Holiday/Exam/Meeting/Activity/Sport/General
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    end_date = db.Column(db.Date)                            # for multi-day events
    start_time = db.Column(db.String(5))                     # 'HH:MM' (optional)
    end_time = db.Column(db.String(5))
    all_day = db.Column(db.Boolean, default=True)
    location = db.Column(db.String(120))
    audience = db.Column(db.String(20), default='All')       # All/Staff/Students/Parents
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    term = db.relationship('Term')

    CATEGORY_COLORS = {
        'Holiday': '#e74a3b', 'Exam': '#7e6cf0', 'Meeting': '#4e73df',
        'Activity': '#1cc88a', 'Sport': '#fd7e14', 'General': '#11998e',
    }

    @property
    def color(self):
        return self.CATEGORY_COLORS.get(self.category, '#11998e')

    @property
    def last_date(self):
        return self.end_date or self.start_date

    def __repr__(self):
        return f'<SchoolEvent {self.title!r} {self.start_date}>'
