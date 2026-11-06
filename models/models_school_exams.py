"""
JSS3 and Basic 6 external examinations (state + federal).

Everything external-exam related before this module was for SSS3 (WAEC / JAMB /
Mock WAEC / Mock JAMB). Two other classes sit public exams in Nigeria:

* **JSS3** — the Basic Education Certificate Examination (BECE):
    - *State*: the state Ministry / Examinations Board BECE ("Junior WAEC").
    - *Federal*: NECO's BECE, taken by Federal Unity Colleges and federal schools.
* **Basic 6** (Primary 6) — the common entrance / placement examination:
    - *State*: the state Common Entrance / Placement examination into JSS1.
    - *Federal*: NECO's National Common Entrance Examination (NCEE) into the
      Federal Unity Colleges.

The two levels are kept separate end-to-end (own blueprint, URLs, pages,
analytics and settings) — exactly like the JSS / SSS split of the timetable
generator — but share these three tables, keyed by ``level`` and ``body``:

* ``SchoolExamResult``    — one row per (student, level, body, year, subject):
  a score (optional) and a grade.
* ``SchoolExamCandidate`` — one row per (student, level, body, year): the
  candidate's exam number, total score, and placement / admission outcome.
* ``SchoolExamConfig``    — per (level, body): exam name, subject list, maximum
  score, grade bands, admission cut-off and the "good result" benchmark.

Grade bands are configurable because states differ. Each band has a letter,
a label, a minimum percentage and a *kind* (distinction / credit / pass /
fail) so every analytic speaks the same language regardless of the letters a
particular state uses.
"""
import json

from models.models import db, local_now

LEVELS = ('jss3', 'basic6')
BODIES = ('state', 'federal')
KINDS = ('distinction', 'credit', 'pass', 'fail')

# Level metadata used by routes / templates.
LEVEL_META = {
    'jss3': {
        'key': 'jss3', 'class_label': 'JSS3', 'name': 'JSS3 Exams',
        'long_name': 'Junior Secondary 3 — Basic Education Certificate Examination',
        'exam_short': 'BECE', 'icon': 'fa-user-graduate', 'color': '#2563eb',
        'gradient': 'linear-gradient(135deg,#2563eb 0%,#7c3aed 100%)',
        'bodies': {
            'state': {'name': 'State BECE', 'full': 'State Basic Education Certificate Examination (Junior WAEC)'},
            'federal': {'name': 'NECO BECE', 'full': 'NECO Basic Education Certificate Examination (Federal)'},
        },
        'outcome_label': 'Next placement (SSS1 / stream)',
    },
    'basic6': {
        'key': 'basic6', 'class_label': 'Basic 6', 'name': 'Basic 6 Exams',
        'long_name': 'Primary / Basic 6 — Common Entrance Examination',
        'exam_short': 'Common Entrance', 'icon': 'fa-child', 'color': '#059669',
        'gradient': 'linear-gradient(135deg,#059669 0%,#0ea5e9 100%)',
        'bodies': {
            'state': {'name': 'State Common Entrance', 'full': 'State Common Entrance / Placement Examination into JSS1'},
            'federal': {'name': 'NCEE', 'full': 'NECO National Common Entrance Examination (Federal Unity Colleges)'},
        },
        'outcome_label': 'School offered admission',
    },
}

JSS3_SUBJECTS = [
    'English Studies', 'Mathematics', 'Basic Science', 'Basic Technology',
    'Social Studies', 'Civic Education', 'Christian Religious Studies',
    'Islamic Studies', 'Cultural and Creative Arts', 'Business Studies',
    'Agricultural Science', 'Home Economics', 'Physical and Health Education',
    'Computer Studies', 'French', 'Yoruba', 'Igbo', 'Hausa', 'Arabic',
    'History', 'Security Education',
]

BASIC6_STATE_SUBJECTS = [
    'English Studies', 'Mathematics', 'Basic Science and Technology',
    'Social Studies', 'Quantitative Reasoning', 'Verbal Reasoning',
    'General Paper',
]

BASIC6_FEDERAL_SUBJECTS = [
    'English Studies', 'Mathematics', 'Basic Science and Technology',
    'Social Studies', 'Quantitative Reasoning', 'Verbal Reasoning',
]

# Five-band scheme widely used by state boards; four-band NECO BECE scheme.
_FIVE_BANDS = [
    {'grade': 'A', 'label': 'Distinction', 'min': 70, 'kind': 'distinction'},
    {'grade': 'B', 'label': 'Upper Credit', 'min': 60, 'kind': 'credit'},
    {'grade': 'C', 'label': 'Credit', 'min': 50, 'kind': 'credit'},
    {'grade': 'P', 'label': 'Pass', 'min': 40, 'kind': 'pass'},
    {'grade': 'F', 'label': 'Fail', 'min': 0, 'kind': 'fail'},
]
_NECO_BECE_BANDS = [
    {'grade': 'A', 'label': 'Distinction', 'min': 70, 'kind': 'distinction'},
    {'grade': 'C', 'label': 'Credit', 'min': 50, 'kind': 'credit'},
    {'grade': 'P', 'label': 'Pass', 'min': 40, 'kind': 'pass'},
    {'grade': 'F', 'label': 'Fail', 'min': 0, 'kind': 'fail'},
]

# Defaults per (level, body). ``benchmark_credits`` is the number of credits
# (or better) *including English and Mathematics* that counts as a "good
# result" — the usual SSS1 admission requirement after BECE. ``cutoff`` is the
# total-score admission cut-off (used mainly by the common entrance exams).
DEFAULTS = {
    ('jss3', 'state'): {'exam_name': 'State BECE', 'subjects': JSS3_SUBJECTS,
                        'max_score': 100, 'bands': _FIVE_BANDS,
                        'benchmark_credits': 6, 'cutoff': None},
    ('jss3', 'federal'): {'exam_name': 'NECO BECE', 'subjects': JSS3_SUBJECTS,
                          'max_score': 100, 'bands': _NECO_BECE_BANDS,
                          'benchmark_credits': 6, 'cutoff': None},
    ('basic6', 'state'): {'exam_name': 'State Common Entrance', 'subjects': BASIC6_STATE_SUBJECTS,
                          'max_score': 100, 'bands': _FIVE_BANDS,
                          'benchmark_credits': 4, 'cutoff': None},
    ('basic6', 'federal'): {'exam_name': 'NCEE', 'subjects': BASIC6_FEDERAL_SUBJECTS,
                            'max_score': 100, 'bands': _FIVE_BANDS,
                            'benchmark_credits': 4, 'cutoff': None},
}

CORE_SUBJECT_KEYS = ('english', 'mathematics')


def is_core_subject(subject):
    """English (Studies/Language) or Mathematics — the two subjects every
    admission benchmark insists on."""
    s = (subject or '').strip().lower()
    return s.startswith('english') or s in ('mathematics', 'maths', 'math')


def core_key(subject):
    s = (subject or '').strip().lower()
    if s.startswith('english'):
        return 'english'
    if s in ('mathematics', 'maths', 'math'):
        return 'mathematics'
    return None


class SchoolExamConfig(db.Model):
    """Per (level, body) settings for a JSS3 / Basic 6 external exam."""
    __tablename__ = 'school_exam_configs'

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(10), nullable=False)
    body = db.Column(db.String(10), nullable=False)
    exam_name = db.Column(db.String(120))
    subjects_json = db.Column(db.Text)
    bands_json = db.Column(db.Text)
    max_score = db.Column(db.Float, default=100)
    benchmark_credits = db.Column(db.Integer)
    cutoff = db.Column(db.Float)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    __table_args__ = (db.UniqueConstraint('level', 'body', name='uq_school_exam_config'),)


class SchoolExamResult(db.Model):
    """One subject result for a JSS3 / Basic 6 candidate."""
    __tablename__ = 'school_exam_results'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    level = db.Column(db.String(10), nullable=False, index=True)
    body = db.Column(db.String(10), nullable=False)
    exam_year = db.Column(db.Integer, nullable=False, index=True)
    subject = db.Column(db.String(80), nullable=False)
    score = db.Column(db.Float)          # optional — many boards publish grades only
    grade = db.Column(db.String(4), nullable=False)
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    student = db.relationship('Student', backref=db.backref('school_exam_results', lazy='dynamic',
                                                            cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('student_id', 'level', 'body', 'exam_year', 'subject',
                            name='uq_school_exam_result'),
    )


class SchoolExamCandidate(db.Model):
    """Per-candidate sitting record: exam number, total, placement outcome."""
    __tablename__ = 'school_exam_candidates'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    level = db.Column(db.String(10), nullable=False, index=True)
    body = db.Column(db.String(10), nullable=False)
    exam_year = db.Column(db.Integer, nullable=False, index=True)
    exam_number = db.Column(db.String(40))
    centre = db.Column(db.String(120))
    total_score = db.Column(db.Float)    # as published; else the sum of subject scores
    placement = db.Column(db.String(150))
    admitted = db.Column(db.Boolean)     # None = not yet known
    remarks = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=local_now)
    updated_at = db.Column(db.DateTime, default=local_now, onupdate=local_now)

    student = db.relationship('Student', backref=db.backref('school_exam_candidacies', lazy='dynamic',
                                                            cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('student_id', 'level', 'body', 'exam_year',
                            name='uq_school_exam_candidate'),
    )


# --------------------------------------------------------------------------- #
# Resolved configuration
# --------------------------------------------------------------------------- #
class ExamScheme:
    """The effective configuration for one (level, body): DB overrides on top of
    the built-in defaults, plus the grading helpers every page uses."""

    def __init__(self, level, body, row=None):
        d = DEFAULTS[(level, body)]
        self.level, self.body = level, body
        self.exam_name = (row.exam_name if row and row.exam_name else d['exam_name'])
        self.subjects = _loads(row.subjects_json if row else None) or list(d['subjects'])
        bands = _loads(row.bands_json if row else None) or [dict(b) for b in d['bands']]
        self.bands = normalise_bands(bands) or [dict(b) for b in d['bands']]
        self.max_score = float(row.max_score) if row and row.max_score else float(d['max_score'])
        self.benchmark_credits = (row.benchmark_credits if row and row.benchmark_credits is not None
                                  else d['benchmark_credits'])
        self.cutoff = row.cutoff if row and row.cutoff is not None else d['cutoff']

    # -- grading ----------------------------------------------------------- #
    @property
    def grades(self):
        return [b['grade'] for b in self.bands]

    def band_for_grade(self, grade):
        g = (grade or '').strip().upper()
        for b in self.bands:
            if b['grade'].upper() == g:
                return b
        return None

    def kind_of(self, grade):
        b = self.band_for_grade(grade)
        return b['kind'] if b else None

    def grade_from_score(self, score):
        """Score -> grade letter using the band minimums (as a % of max_score)."""
        if score is None:
            return None
        pct = max(0.0, min(100.0, float(score) / self.max_score * 100.0))
        for b in self.bands:                       # bands sorted high -> low
            if pct + 1e-9 >= b['min']:
                return b['grade']
        return self.bands[-1]['grade']

    def is_credit(self, grade):
        return self.kind_of(grade) in ('distinction', 'credit')

    def is_pass(self, grade):
        return self.kind_of(grade) in ('distinction', 'credit', 'pass')

    def grade_points(self, grade):
        """Higher-is-better ordinal points: top band = len(bands), fail = 1."""
        n = len(self.bands)
        for i, b in enumerate(self.bands):
            if b['grade'].upper() == (grade or '').strip().upper():
                return n - i
        return 0

    def as_dict(self):
        return {'level': self.level, 'body': self.body, 'exam_name': self.exam_name,
                'subjects': self.subjects, 'bands': self.bands, 'max_score': self.max_score,
                'benchmark_credits': self.benchmark_credits, 'cutoff': self.cutoff}


def _loads(text):
    if not text:
        return None
    try:
        v = json.loads(text)
        return v or None
    except (TypeError, ValueError):
        return None


def normalise_bands(bands):
    """Validate + sort grade bands (highest minimum first). Drops malformed
    rows; guarantees the lowest band starts at 0 so every score gets a grade."""
    out, seen = [], set()
    for b in bands or []:
        try:
            grade = str(b.get('grade', '')).strip().upper()[:4]
            mn = float(b.get('min'))
        except (TypeError, ValueError, AttributeError):
            continue
        kind = str(b.get('kind', '')).strip().lower()
        if not grade or grade in seen or kind not in KINDS:
            continue
        seen.add(grade)
        out.append({'grade': grade, 'label': (str(b.get('label') or '').strip() or grade)[:40],
                    'min': max(0.0, min(100.0, mn)), 'kind': kind})
    if not out:
        return []
    out.sort(key=lambda b: -b['min'])
    out[-1]['min'] = 0.0
    return out


def get_scheme(level, body):
    """The effective ExamScheme for (level, body). Never raises — falls back to
    the defaults if the config table is unavailable."""
    row = None
    try:
        row = SchoolExamConfig.query.filter_by(level=level, body=body).first()
    except Exception:
        db.session.rollback()
    return ExamScheme(level, body, row)
