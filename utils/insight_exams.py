"""The exams the Deeper Insights page can analyse, behind one interface so
every section works the same way for WAEC, NECO, JSS3 (state BECE / NECO BECE)
and Basic 5/6 (state Common Entrance / NCEE) — each with its own grading.

``Exam`` objects provide: rows() / years() to read results, points() /
is_credit() / status() for the grading rule, and labels for the page."""
from __future__ import annotations

from collections import defaultdict

from models import db, Student
from utils import exam_rules as R


class Exam:
    key = ''
    name = ''              # short ("WAEC")
    exam_name = ''         # full ("WASSCE")
    level = 'sss3'         # school-exam level the cohort sits in
    level_label = 'SSS3'
    class_keys = ('SSS3',)
    near_label = 'D7'
    credit_label = 'credit'
    benchmark_label = '5 credits incl. Eng & Maths'
    max_points = 9
    # Which sections make sense for this exam.
    has_mocks = True
    earlier = None         # (label, Exam factory) — exam sat earlier by the same pupils
    years_from_jss1 = 5    # exam year = JSS1 intake year + this (None = no cohort view)

    # ---- data ------------------------------------------------------------
    def rows(self, year=None, bid=None):
        raise NotImplementedError

    def years(self):
        return sorted({y for _sid, y, _s, _g in self.rows()}, reverse=True)

    def by_student(self, year, bid=None):
        """{student_id: {subject: grade}} for one year."""
        out = defaultdict(dict)
        for sid, _y, subj, grade in self.rows(year, bid):
            if grade:
                out[sid][self.canon(subj)] = grade
        return dict(out)

    def canon(self, subject):
        return (subject or '').strip()

    # ---- grading ---------------------------------------------------------
    def points(self, g):
        raise NotImplementedError

    def is_credit(self, g):
        raise NotImplementedError

    def is_distinction(self, g):
        return False

    def is_near(self, g):
        """One grade short of a credit."""
        raise NotImplementedError

    def status(self, grades):
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# WAEC / NECO
# --------------------------------------------------------------------------- #
class BoardExam(Exam):
    def __init__(self, model, key, name, exam_name):
        self.model, self.key, self.name, self.exam_name = model, key, name, exam_name
        self.earlier = ('BECE (JSS3)', lambda: SchoolExam('jss3', None))

    def rows(self, year=None, bid=None):
        m = self.model
        q = db.session.query(m.student_id, m.exam_year, m.subject, m.grade)
        if year is not None:
            q = q.filter(m.exam_year == year)
        if bid is not None:
            q = q.join(Student, Student.id == m.student_id).filter(Student.branch_id == bid)
        return [(sid, y, subj, R.norm_grade(g)) for sid, y, subj, g in q.all()]

    def years(self):
        return sorted({y for (y,) in db.session.query(self.model.exam_year).distinct()}, reverse=True)

    def canon(self, subject):
        return R.canonical_subject(subject)

    def points(self, g):
        return R.points(g)

    def is_credit(self, g):
        return R.is_credit(g)

    def is_distinction(self, g):
        return R.is_distinction(g)

    def is_near(self, g):
        return R.norm_grade(g) in R.NEAR_CREDIT_GRADES

    def status(self, grades):
        return R.five_credit_status(grades)


def waec():
    from models import WAECResult
    return BoardExam(WAECResult, 'waec', 'WAEC', 'WASSCE')


def neco():
    from models import NECOResult
    return BoardExam(NECOResult, 'neco', 'NECO', 'NECO SSCE')


# --------------------------------------------------------------------------- #
# JSS3 BECE / Basic 5-6 Common Entrance (school_exams schemes)
# --------------------------------------------------------------------------- #
class SchoolExam(Exam):
    """One school-exam level (``jss3`` / ``basic6``) and body (``state`` /
    ``federal``; None = both, each graded on its own scheme)."""
    has_mocks = False

    def __init__(self, level, body=None):
        from models.models_school_exams import BODIES, get_scheme
        self.level, self.body = level, body
        bodies = [body] if body else list(BODIES)
        self.schemes = {b: get_scheme(level, b) for b in bodies}
        sc = self.schemes[bodies[0]]
        from utils import school_exams as svc
        self.key = level + ('_' + body if body else '')
        cls = svc.level_class_label(level)
        self.class_keys = tuple(svc.level_class_keys(level))
        self.name = sc.exam_name if body else ('BECE' if level == 'jss3' else 'Common Entrance')
        self.exam_name = self.name
        self.level_label = cls
        bench = sc.benchmark_credits
        self.benchmark_label = ('%d+ credits incl. Eng & Maths' % bench) if bench else 'Credit in Eng & Maths'
        self.max_points = max(len(s.bands) for s in self.schemes.values())
        passes = [b['grade'] for b in sc.bands if b['kind'] == 'pass']
        self.near_label = passes[0] if passes else 'P'
        if level == 'jss3':
            self.earlier = ('Common Entrance (Basic 5/6)', lambda: SchoolExam('basic6', None))
            self.years_from_jss1 = 2
        else:
            self.earlier = None
            self.years_from_jss1 = None

    def _rows_q(self):
        from models.models_school_exams import SchoolExamResult as S
        q = db.session.query(S.student_id, S.exam_year, S.subject, S.grade, S.body).filter(S.level == self.level)
        if self.body:
            q = q.filter(S.body == self.body)
        return q

    def rows(self, year=None, bid=None):
        from models.models_school_exams import SchoolExamResult as S
        q = self._rows_q()
        if year is not None:
            q = q.filter(S.exam_year == year)
        if bid is not None:
            q = q.join(Student, Student.id == S.student_id).filter(Student.branch_id == bid)
        # Tag each grade with its body so mixed state + federal results are
        # each read on their own scheme.
        return [(sid, y, subj, (body, (g or '').strip().upper())) for sid, y, subj, g, body in q.all()]

    def years(self):
        from models.models_school_exams import SchoolExamResult as S
        q = db.session.query(S.exam_year).filter(S.level == self.level)
        if self.body:
            q = q.filter(S.body == self.body)
        return sorted({y for (y,) in q.distinct()}, reverse=True)

    def _sc(self, g):
        body, grade = g
        return self.schemes.get(body) or next(iter(self.schemes.values())), grade

    def points(self, g):
        sc, grade = self._sc(g)
        n = len(sc.bands) or 1
        # Rescaled to this exam's widest band count so state and federal mix.
        return sc.grade_points(grade) * self.max_points / n

    def kind(self, g):
        sc, grade = self._sc(g)
        return sc.kind_of(grade) or 'fail'

    def is_credit(self, g):
        return self.kind(g) in ('distinction', 'credit')

    def is_distinction(self, g):
        return self.kind(g) == 'distinction'

    def is_near(self, g):
        """The top 'pass' grade of the scheme — one band below a credit."""
        sc, grade = self._sc(g)
        passes = [b['grade'] for b in sc.bands if b['kind'] == 'pass']
        return bool(passes) and grade == passes[0]

    def grade_text(self, g):
        return g[1] if isinstance(g, tuple) else g

    def status(self, grades):
        from models.models_school_exams import core_key
        credits = sum(1 for g in grades.values() if self.is_credit(g))
        eng = any(core_key(s) == 'english' and self.is_credit(g) for s, g in grades.items())
        mth = any(core_key(s) == 'mathematics' and self.is_credit(g) for s, g in grades.items())
        bodies = {g[0] for g in grades.values()} or set(self.schemes)
        bench = max((self.schemes[b].benchmark_credits or 0) for b in bodies if b in self.schemes) if bodies else 0
        meets = eng and mth and credits >= bench
        near = False
        if not meets:
            for s, g in grades.items():
                if not self.is_near(g):
                    continue
                ck = core_key(s)
                if (eng or ck == 'english') and (mth or ck == 'mathematics') and credits + 1 >= bench:
                    near = True
                    break
        return {'credits': credits, 'english': eng, 'maths': mth, 'meets': meets, 'near': near}


def grade_text(exam, g):
    return exam.grade_text(g) if hasattr(exam, 'grade_text') else g


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def choices():
    """[(key, label)] for the page's exam switch, only exams with results."""
    from models import NECOResult
    from models.models_school_exams import SchoolExamResult as S
    from utils import school_exams as svc
    out = [('waec', 'WAEC')]
    try:
        if db.session.query(NECOResult.id).first():
            out.append(('neco', 'NECO'))
        levels = {lv for (lv,) in db.session.query(S.level).distinct()}
    except Exception:
        db.session.rollback()
        levels = set()
    if 'jss3' in levels:
        out.append(('jss3', 'JSS3 BECE'))
    if 'basic6' in levels:
        out.append(('basic6', 'Common Entrance'))
    return out


def get(key):
    if key == 'neco':
        return neco()
    if key in ('jss3', 'basic6'):
        svc_ensure()
        return SchoolExam(key, None)
    return waec()


def svc_ensure():
    from utils import school_exams as svc
    svc.ensure_school_exam_schema()
