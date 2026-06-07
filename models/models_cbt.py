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
    max_score = db.Column(db.Float)          # scaled total for the subject (e.g. 30); None = raw
    instructions = db.Column(db.Text)
    access_password = db.Column(db.String(60))                           # per-exam subject password
    shuffle = db.Column(db.Boolean, default=True)
    strict_mode = db.Column(db.Boolean, default=True)        # fullscreen + lockdown
    violation_limit = db.Column(db.Integer, default=3)       # leaves before auto-submit (0 = never)
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
        if now is None:
            from utils.timeutil import now as _now
            now = _now()
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
    def raw_total(self):
        """Sum of all question marks (unscaled)."""
        return sum(q.marks or 0 for q in self.questions)

    @property
    def total_marks(self):
        """The score the exam is reported out of (scaled total, or raw if unset)."""
        return self.max_score if self.max_score else self.raw_total

    def scale(self, raw_score):
        """Scale a raw score to the exam's reported total."""
        rt = self.raw_total
        if not rt:
            return 0.0
        if not self.max_score:
            return round(raw_score, 2)
        return round(raw_score / rt * self.max_score, 2)

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
    image_url = db.Column(db.String(300))        # optional figure (e.g. a diagram)
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
    score = db.Column(db.Float, default=0)        # scaled score (out of exam total)
    total = db.Column(db.Float, default=0)        # exam reported total (scaled)
    raw_score = db.Column(db.Float, default=0)    # marks earned from questions
    raw_total = db.Column(db.Float, default=0)    # sum of question marks
    violations = db.Column(db.Integer, default=0) # counted leave-page events
    paused_until = db.Column(db.DateTime)         # supervisor override window
    last_seen = db.Column(db.DateTime)            # heartbeat (spot disconnects)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))
    status = db.Column(db.String(15), default='In progress')   # In progress / Submitted / Auto-submitted

    student = db.relationship('Student')
    answers = db.relationship('CBTAnswer', backref='attempt',
                              lazy='dynamic', cascade='all, delete-orphan')
    violation_log = db.relationship('CBTViolation', backref='attempt',
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


class CBTLoginEvent(db.Model):
    """Device fingerprint captured when a student logs into / starts the exam
    portal, kept for malpractice investigations."""
    __tablename__ = 'cbt_login_events'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('cbt_exams.id'))   # nullable (login)
    event = db.Column(db.String(20), default='login')               # login / start / fingerprint
    ip_address = db.Column(db.String(60))
    user_agent = db.Column(db.String(400))
    browser = db.Column(db.String(40))
    os = db.Column(db.String(40))
    device_type = db.Column(db.String(20))      # Desktop / Mobile / Tablet
    device_model = db.Column(db.String(80))      # e.g. Redmi 13C, iPhone, SM-G991B
    is_mobile = db.Column(db.Boolean, default=False)
    # Enriched client-side (best effort, may be blank).
    screen = db.Column(db.String(20))           # e.g. 1366x768
    viewport = db.Column(db.String(20))
    timezone = db.Column(db.String(60))
    language = db.Column(db.String(40))
    platform = db.Column(db.String(60))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    geo_accuracy = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=local_now)

    student = db.relationship('Student')
    exam = db.relationship('CBTExam')

    @property
    def location(self):
        if self.latitude is not None and self.longitude is not None:
            return f'{self.latitude:.5f}, {self.longitude:.5f}'
        return None


class QuestionBank(db.Model):
    """A reusable question, tagged by subject/topic, copied into exams as needed."""
    __tablename__ = 'question_bank'

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'))
    topic = db.Column(db.String(100))
    difficulty = db.Column(db.String(10), default='Medium')   # Easy/Medium/Hard
    question_text = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(300))        # optional figure
    option_a = db.Column(db.String(300))
    option_b = db.Column(db.String(300))
    option_c = db.Column(db.String(300))
    option_d = db.Column(db.String(300))
    correct_option = db.Column(db.String(1))
    marks = db.Column(db.Float, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=local_now)

    subject = db.relationship('Subject')

    @property
    def options(self):
        return [('A', self.option_a), ('B', self.option_b),
                ('C', self.option_c), ('D', self.option_d)]

    def __repr__(self):
        return f'<QuestionBank {self.id}>'


class CBTViolation(db.Model):
    """One recorded anti-malpractice event during an attempt."""
    __tablename__ = 'cbt_violations'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('cbt_attempts.id'), nullable=False)
    vtype = db.Column(db.String(30))        # tab_switch / fullscreen_exit / paste / copy / shortcut / devtools / resume
    detail = db.Column(db.Text)             # e.g. pasted text, key combo
    away_seconds = db.Column(db.Integer, default=0)
    counted = db.Column(db.Boolean, default=True)   # whether it counted toward the limit
    created_at = db.Column(db.DateTime, default=local_now)

    LABELS = {
        'tab_switch': 'Left the exam tab/app',
        'fullscreen_exit': 'Exited fullscreen',
        'paste': 'Tried to paste',
        'copy': 'Tried to copy',
        'shortcut': 'Blocked shortcut',
        'devtools': 'Possible dev-tools',
        'resume': 'Supervisor resume',
    }

    @property
    def label(self):
        return self.LABELS.get(self.vtype, self.vtype or 'Event')
