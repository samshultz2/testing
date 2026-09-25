"""/subjects/scores (with all of term/assignment/class_subject/assessment
selected — the common case) built its class roster TWICE: once for the
score-entry table (students_data) and again, identically, for the "by
student" picker's roster — both gated on selected_assignment, so whenever
a class_subject + assessment were also chosen, the exact same
StudentEnrollment+Student query ran twice."""
import re
from sqlalchemy import event
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject, ClassSubject,
                    AssessmentType, StudentScore)
from tests.conftest import login_token

_SEQ = [0]
_N_STUDENTS = 10


def _count_selects(app, table, fn):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'SED{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{tag}-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'{tag}C', level=1); arm = ClassArm(name=f'{tag}A', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject(name=f'{tag}-Maths', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        at = (AssessmentType.query.filter_by(short_name='CA1').first()
              or AssessmentType(name='1st CA', short_name='CA1', max_score=20, order=1, is_active=True))
        if at.id is None:
            db.session.add(at); db.session.flush()
        for i in range(_N_STUDENTS):
            s = Student(student_id=f'{tag}-{i}', first_name=f'F{i}', surname=f'S{i}',
                       gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
            if i < 3:
                db.session.add(StudentScore(student_id=s.id, class_subject_id=cs.id,
                                            assessment_type_id=at.id, score=15))
        db.session.commit()
        return dict(term=term.id, asg=caa.id, cs=cs.id, at=at.id)


def test_roster_fetched_once_not_twice(app):
    ids = _seed(app)
    c = _admin(app)
    url = (f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}"
          f"&class_subject_id={ids['cs']}&assessment_type_id={ids['at']}")
    n = _count_selects(app, 'student_enrollments', lambda: c.get(url))
    assert n <= 1, (
        f'{n} student_enrollments SELECTs with term+assignment+class_subject+'
        f'assessment all selected — the class roster looks like it is being '
        f'fetched twice (once for students_data, once for roster)')


def test_scores_entry_response_shape_unchanged(app):
    ids = _seed(app)
    c = _admin(app)
    url = (f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}"
          f"&class_subject_id={ids['cs']}&assessment_type_id={ids['at']}")
    html = c.get(url).get_data(as_text=True)
    assert 'S0' in html and 'S1' in html and f'S{_N_STUDENTS - 1}' in html
