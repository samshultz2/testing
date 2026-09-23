"""The Defaulters page (whole-school by default, no class filter) used to
lazy-load .class_arm_assignment and .student per enrollment row instead of
reusing the query's own JOINs — a fresh SELECT per student across the whole
school on every page view. Regression: the student SELECT count stays small
and constant, not one per enrollment."""
import re
from sqlalchemy import event
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, FeeItem,
                    FeeStructure, FeePayment)
from tests.conftest import login_token

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


def _setup(app):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'DFN-Sess-{_SEQ[0]}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'DFN-Term-{_SEQ[0]}')
        db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'DFN-Class-{_SEQ[0]}', level=1); db.session.add(sc); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        item = FeeItem(name=f'DFN-Tuition-{_SEQ[0]}', is_active=True)
        db.session.add(item); db.session.flush()
        db.session.add(FeeStructure(term_id=term.id, class_id=sc.id, fee_item_id=item.id,
                                    amount=10000, is_active=True))

        student_ids = []
        for i in range(_STUDENT_COUNT):
            s = Student(student_id=f'DFN{_SEQ[0]}{i:03d}', first_name=f'D{i}', surname='Fault',
                       gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                             is_active=True))
            # Half-paid — leaves a positive balance so each shows as a defaulter.
            db.session.add(FeePayment(student_id=s.id, term_id=term.id, branch_id=bid,
                                      amount=4000, method='Cash',
                                      receipt_no=f'DFN-RCPT-{_SEQ[0]}-{i}'))
            student_ids.append(s.id)
        db.session.commit()
        return term.id, student_ids


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_defaulters_page_does_not_scale_with_student_count(app):
    term_id, student_ids = _setup(app)
    c = _admin(app)

    n = _count_selects(app, 'students',
                       lambda: c.get(f'/finance/defaulters?term_id={term_id}'))
    assert n < _STUDENT_COUNT, f'{n} Student SELECTs for a {_STUDENT_COUNT}-student defaulters page — looks like an N+1'

    html = c.get(f'/finance/defaulters?term_id={term_id}').get_data(as_text=True)
    for sid in student_ids:
        with app.app_context():
            code = db.session.get(Student, sid).student_id
        assert code in html
    assert '6,000' in html.replace('.00', '') or '6000' in html  # balance = 10000 - 4000
