"""
CBT / Online Tests — computer-based objective tests students sit in-app.

A teacher builds a ``CBTExam`` (subject + class + date) of multiple-choice
``CBTQuestion`` rows and gives it an *access password* (distinct per exam). On
the exam day a student logs into the test portal with their student ID + their
own portal password, sees the exams active for their class that day, enters the
exam's access password to start, answers, and is auto-graded.
"""
from datetime import date

from werkzeug.security import generate_password_hash, check_password_hash

from models.models import db, local_now


class CBTExam(db.Model):
    __tablename__ = 'cbt_exams'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    class_id = db.Column(db.Integer, db.ForeignKey('school_classes.id'))
    arm_id = db.Column(db.Integer, db.ForeignKey('class_arms.id'))      # optional
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id'))
    exam_date = db.Column(db.Date, default=date.today)                   # day it is active
    start_time = db.Column(db.String(5))     # 'HH:MM' window opens (optional)
    end_time = db.Column(db.String(5))       # 'HH:MM' window closes (optional)
    duration_minutes = db.Column(db.Integer, default=30)
    instructions = db.Column(db.Text)
    access_password = db.Column(db.String(60))                           # per-exam subject password
    shuffle = db.Column(db.Boolean, default=True)
    is_published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    subject = db.relationship('Subject')
    school_class = db.relationship('SchoolClass')
    arm = db.relationship('ClassArm')
    term = db.relationship('Term')
    questions = db.relationship('CBTQuestion', backref='exam',
                                lazy='dynamic', cascade='all, delete-orphan')
    attempts = db.relationship('CBTAttempt', backref='exam',
                               lazy='dynamic', cascade='all, delete-orphan')

    def _dt(self, hhmm, default_h, default_m):
        from datetime import datetime, time
        h, m = default_h, default_m
        if hhmm:
            try:
                h, m = [int(x) for x in hhmm.split(':')]
            except (ValueError, AttributeError):
                pass
        return datetime.combine(self.exam_date, time(h, m))

    @property
    def opens_at(self):
        return self._dt(self.start_time, 0, 0)

    @property
    def closes_at(self):
        return self._dt(self.end_time, 23, 59)

    def access_state(self, now=None):
        """('open'|'before'|'closed'|'wrong_day', human_message)."""
        from datetime import datetime
        now = now or datetime.now()
        if now.date() < self.exam_date:
            return 'wrong_day', f'Opens on {self.exam_date.strftime("%d %b %Y")}'
        if now.date() > self.exam_date:
            return 'closed', 'This test has closed'
        if now < self.opens_at:
            return 'before', f'Opens at {self.opens_at.strftime("%I:%M %p")}'
        if now > self.closes_at:
            return 'closed', f'Closed at {self.closes_at.strftime("%I:%M %p")}'
        return 'open', 'Available now'

    @property
    def is_available(self):
        return self.access_state()[0] == 'open'

    @property
    def window_label(self):
        if self.start_time or self.end_time:
            return f'{self.start_time or "00:00"}–{self.end_time or "23:59"}'
        return 'All day'

    @property
    def total_marks(self):
        return sum(q.marks or 0 for q in self.questions)

    @property
    def question_count(self):
        return self.questions.count()

    def __repr__(self):
        return f'<CBTExam {self.title!r}>'


class CBTQuestion(db.Model):
    __tablename__ = 'cbt_questions'

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('cbt_exams.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(300))
    option_b = db.Column(db.String(300))
    option_c = db.Column(db.String(300))
    option_d = db.Column(db.String(300))
    correct_option = db.Column(db.String(1))     # 'A'/'B'/'C'/'D'
    marks = db.Column(db.Float, default=1)
    order = db.Column(db.Integer, default=0)

    @property
    def options(self):
        return [('A', self.option_a), ('B', self.option_b),
                ('C', self.option_c), ('D', self.option_d)]

    def __repr__(self):
        return f'<CBTQuestion exam{self.exam_id} #{self.order}>'


class CBTAttempt(db.Model):
    __tablename__ = 'cbt_attempts'

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('cbt_exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=local_now)
    submitted_at = db.Column(db.DateTime)
    score = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(15), default='In progress')   # In progress / Submitted

    student = db.relationship('Student')
    answers = db.relationship('CBTAnswer', backref='attempt',
                              lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (db.UniqueConstraint('exam_id', 'student_id', name='uq_cbt_attempt'),)

    @property
    def percentage(self):
        return round(self.score / self.total * 100, 1) if self.total else 0.0

    def __repr__(self):
        return f'<CBTAttempt exam{self.exam_id} student{self.student_id} {self.status}>'


class CBTAnswer(db.Model):
    __tablename__ = 'cbt_answers'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('cbt_attempts.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('cbt_questions.id'), nullable=False)
    selected_option = db.Column(db.String(1))
    is_correct = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint('attempt_id', 'question_id', name='uq_cbt_answer'),)
