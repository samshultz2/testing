"""The Exam Hall Allocator form lists every class-arm assignment in the active
term with its active-enrollment count. It used to run one COUNT query per
assignment instead of a single grouped query. Regression: the enrollment
COUNT-query count stays small and constant, not one per assignment."""
import re
from sqlalchemy import event
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment)
from tests.conftest import login_token

_ASSIGNMENT_COUNT = 8
_SEQ = [0]


def _count_queries(app, fn):
    """Count every SELECT that touches student_enrollments (the .count() calls)."""
    pattern = re.compile(r'^select\b.*\bfrom\s+student_enrollments\b', re.IGNORECASE | re.DOTALL)
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


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        AcademicSession.query.update({AcademicSession.is_active: False})
        Term.query.update({Term.is_active: False})
        sess = AcademicSession(name=f'EHN-Sess-{_SEQ[0]}', is_active=True)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'EHN-Term-{_SEQ[0]}',
                    is_active=True)
        db.session.add(term); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        for i in range(_ASSIGNMENT_COUNT):
            sc = SchoolClass(name=f'EHN-Class-{_SEQ[0]}-{i}', level=1)
            db.session.add(sc); db.session.flush()
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            s = Student(student_id=f'EHN{_SEQ[0]}{i:03d}', first_name=f'E{i}', surname='Hall',
                       gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                             is_active=True))
        db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_exam_halls_form_does_not_scale_with_assignment_count(app):
    _setup(app)
    c = _admin(app)
    n = _count_queries(app, lambda: c.get('/tools/exam-halls/'))
    assert n < _ASSIGNMENT_COUNT, f'{n} enrollment-count SELECTs for {_ASSIGNMENT_COUNT} assignments — looks like an N+1'
