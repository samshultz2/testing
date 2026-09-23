"""Contributions Defaulters lists every SSS3 student behind on their dues.
It used to lazy-load .student/.class_arm_assignment per enrollment (instead
of reusing the query's own JOINs) and run a `last payment` SELECT per
defaulting student. Regression: neither scales with the number of students."""
import re
from datetime import date
from sqlalchemy import event
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment,
                    ContributionSettings, ContributionPayment)
from tests.conftest import login_token

ACCESS_CODE = '64665842'
_STUDENT_COUNT = 10
_SEQ = [0]


def _make_select_counter(table):
    pattern = re.compile(r'^select\b.*\bfrom\s+' + re.escape(table) + r'\b',
                         re.IGNORECASE | re.DOTALL)
    counts = {'n': 0}

    def before(conn, cursor, statement, params, context, executemany):
        if pattern.match(statement):
            counts['n'] += 1
    return counts, before


def _count_selects(app, table, fn):
    counts, before = _make_select_counter(table)
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', before)
    try:
        fn()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return counts['n']


def _client(app):
    with app.app_context():
        ContributionSettings.set('access_code', ACCESS_CODE)
        ContributionSettings.set('max_due', 20000)
    c = app.test_client()
    token = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    token = _ptoken(c)
    c.post('/contributions/access', data={'access_code': ACCESS_CODE, '_csrf_token': token})
    return c


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        AcademicSession.query.update({AcademicSession.is_active: False})
        Term.query.update({Term.is_active: False})
        sess = AcademicSession(name=f'CDN-Sess-{_SEQ[0]}', is_active=True)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'CDN-Term-{_SEQ[0]}',
                    is_active=True)
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=12)
        if sc.id is None:
            db.session.add(sc); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        student_ids = []
        for i in range(_STUDENT_COUNT):
            s = Student(student_id=f'CDN{_SEQ[0]}{i:03d}', first_name=f'C{i}', surname='Due',
                       gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                             is_active=True))
            db.session.add(ContributionPayment(session_id=sess.id, student_id=s.id,
                                               amount=5000, payment_date=date(2025, 2, 1)))
            student_ids.append(s.id)
        db.session.commit()
        return student_ids


def test_contributions_defaulters_does_not_scale_with_student_count(app):
    student_ids = _setup(app)
    c = _client(app)

    n = _count_selects(app, 'students', lambda: c.get('/contributions/defaulters'))
    assert n < _STUDENT_COUNT, f'{n} Student SELECTs for a {_STUDENT_COUNT}-student defaulters page — looks like an N+1'

    n2 = _count_selects(app, 'contribution_payments', lambda: c.get('/contributions/defaulters'))
    assert n2 < _STUDENT_COUNT, f'{n2} ContributionPayment SELECTs — looks like a per-student last-payment N+1'

    html = c.get('/contributions/defaulters').get_data(as_text=True)
    for sid in student_ids:
        with app.app_context():
            name = db.session.get(Student, sid).full_name
        assert name in html
