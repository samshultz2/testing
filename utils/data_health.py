"""Data-health checks for exam analytics: problems in the records that make
the numbers wrong (duplicate pupils, graduates on current registers, results
with no class enrolment, one subject spelt several ways, suspicious years).
Each check returns a dict the Insights page renders as a card with a fix link."""
from __future__ import annotations

from collections import defaultdict
from statistics import median, mean, pstdev

from models import db, Student
from utils import exam_rules as R


def _check(key, label, items, *, severity='warn', fix=None, fix_label=None, help_text=''):
    return {'key': key, 'label': label, 'count': len(items), 'items': items[:25],
            'severity': severity if items else 'ok', 'fix': fix, 'fix_label': fix_label,
            'help': help_text}


def duplicate_pupils():
    from utils.student_merge import find_groups
    groups = find_groups()
    items = [' / '.join('%s (%s)' % (m['student'].full_name, m['student'].student_id) for m in g['members'])
             for g in groups]
    return items


def graduates_on_registers(bid=None):
    """Graduates of an earlier session still enrolled in a current-term class."""
    from models import StudentEnrollment, ClassArmAssignment, Term
    from utils.helpers import get_active_term
    term = get_active_term()
    if not term:
        return []
    q = (db.session.query(Student, ClassArmAssignment)
         .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
         .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
         .filter(ClassArmAssignment.term_id == term.id, StudentEnrollment.is_active == True,  # noqa: E712
                 Student.is_graduated == True,  # noqa: E712
                 db.or_(Student.graduation_session_id.is_(None),
                        Student.graduation_session_id != term.session_id)))
    if bid is not None:
        q = q.filter(Student.branch_id == bid)
    return ['%s (%s) — %s' % (s.full_name, s.student_id, caa.display_name) for s, caa in q.all()]


def results_without_enrolment(year, bid=None, model=None):
    """WAEC / NECO candidates of ``year`` with no class enrolment in that session."""
    from models import WAECResult, StudentEnrollment, ClassArmAssignment, Term
    WAECResult = model or WAECResult
    from utils.helpers import session_for_exam_year
    sess = session_for_exam_year(year)
    q = db.session.query(WAECResult.student_id).filter(WAECResult.exam_year == year).distinct()
    if bid is not None:
        q = q.join(Student, Student.id == WAECResult.student_id).filter(Student.branch_id == bid)
    ids = {sid for (sid,) in q.all()}
    if not ids or not sess:
        return []
    enrolled = {sid for (sid,) in (db.session.query(StudentEnrollment.student_id)
                                   .join(ClassArmAssignment, ClassArmAssignment.id == StudentEnrollment.class_arm_assignment_id)
                                   .join(Term, Term.id == ClassArmAssignment.term_id)
                                   .filter(Term.session_id == sess.id, StudentEnrollment.student_id.in_(list(ids)))
                                   .distinct().all())}
    missing = ids - enrolled
    studs = Student.query.filter(Student.id.in_(list(missing))).order_by(Student.surname).all() if missing else []
    return ['%s (%s)' % (s.full_name, s.student_id) for s in studs]


def subject_spellings():
    """Subjects stored under more than one spelling (they split statistics)."""
    from models import WAECResult, NECOResult
    from models.mock_waec import MockWAECResult
    names = defaultdict(lambda: defaultdict(int))
    for model in (WAECResult, NECOResult, MockWAECResult):
        for subj, n in db.session.query(model.subject, db.func.count()).group_by(model.subject).all():
            if subj:
                names[R.subject_key(subj)][subj.strip()] += n
    # JAMB papers are left out: "Use of English" is its own paper, not a
    # misspelling of WAEC's "English Language".
    out = []
    for key, spell in sorted(names.items()):
        if len(spell) > 1:
            out.append(' · '.join('“%s” (%d)' % (s, n) for s, n in sorted(spell.items(), key=lambda x: -x[1])))
    return out


def year_anomalies(bid=None, model=None):
    """WAEC / NECO years whose number of candidates or average grade is far from
    the others — usually a half-finished import or a duplicated one."""
    from models import WAECResult
    WAECResult = model or WAECResult
    q = db.session.query(WAECResult.exam_year, WAECResult.student_id, WAECResult.grade)
    if bid is not None:
        q = q.join(Student, Student.id == WAECResult.student_id).filter(Student.branch_id == bid)
    per = defaultdict(lambda: {'students': set(), 'pts': []})
    for y, sid, g in q.all():
        per[y]['students'].add(sid)
        per[y]['pts'].append(R.points(g))
    if len(per) < 3:
        return []
    counts = {y: len(v['students']) for y, v in per.items()}
    means = {y: mean(v['pts']) for y, v in per.items() if v['pts']}
    out = []
    for y in sorted(per):
        others = [c for yy, c in counts.items() if yy != y]
        med = median(others)
        if med and counts[y] < 0.5 * med:
            out.append('%s: only %d candidates (other years ≈ %d) — incomplete import?' % (y, counts[y], med))
        elif med and counts[y] > 2 * med:
            out.append('%s: %d candidates (other years ≈ %d) — duplicated import?' % (y, counts[y], med))
        om = [m for yy, m in means.items() if yy != y]
        sd = pstdev(om) if len(om) > 1 else 0
        if sd and y in means and abs(means[y] - mean(om)) > 2.5 * sd and abs(means[y] - mean(om)) > 0.6:
            out.append('%s: average grade %.2f points vs %.2f in other years — check the grades' % (
                y, means[y], mean(om)))
    return out


def run(year, bid=None, model=None):
    exam = 'NECO' if model is not None and model.__tablename__ == 'neco_results' else 'WAEC'
    from flask import url_for
    checks = []
    for fn in (
        lambda: _check('duplicates', 'Possible duplicate pupils', duplicate_pupils(),
                       fix=url_for('main.duplicate_merge'), fix_label='Review duplicates',
                       help_text='The same pupil saved twice splits their results across two records.'),
        lambda: _check('graduates', 'Graduates still on a current class register', graduates_on_registers(bid),
                       severity='bad', fix=url_for('main.move_class_records'), fix_label='Move class records',
                       help_text='Usually left behind by a merge of two different pupils.'),
        lambda: _check('no_enrolment', '%s %s candidates with no class enrolment that session' % (exam, year),
                       results_without_enrolment(year, bid, model) if year else [],
                       help_text='They are left out of class, teacher and attendance analysis.'),
        lambda: _check('spellings', 'Subjects saved under more than one spelling', subject_spellings(),
                       help_text='Analytics folds common variants together, but fixing them at source keeps exports tidy.'),
        lambda: _check('years', 'Unusual %s years' % exam, year_anomalies(bid, model),
                       help_text='A year with far fewer (or more) candidates than usual, or very different grades.'),
    ):
        try:
            checks.append(fn())
        except Exception as e:  # pragma: no cover — one bad check never breaks the page
            db.session.rollback()
            checks.append({'key': 'error', 'label': 'A check could not run', 'count': 0, 'items': [str(e)],
                           'severity': 'warn', 'fix': None, 'help': ''})
    return checks
