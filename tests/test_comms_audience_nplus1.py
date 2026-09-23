"""resolve_audience() (the parent-messaging recipient resolver used by every
Compose broadcast) used to run per-student N+1 queries in three places:
- the 'class'/'arm' audience lazy-loaded .student per enrollment,
- the 'defaulters' audience called student_bill() (itself 3+ queries) per
  enrollment instead of the same batched math the Finance Defaulters page
  uses,
- and, for EVERY audience, the final contact lookup called
  student.parent_contacts.all() per student (lazy='dynamic' — always a fresh
  SELECT, no identity-map reuse).
Regression: none of these scale with the number of resolved students."""
import re
from datetime import date
from flask import session
from sqlalchemy import event
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, ParentContact,
                    FeeItem, FeeStructure, FeePayment)
from utils import comms

_COHORT_SIZE = 10
_SEQ = [0]


def _deactivate(app, student_ids):
    """These fixtures' students are only needed within their own test; leaving
    them is_active=True would leak into any OTHER test's audience='all' query
    in this shared session-scoped DB (e.g. asserting on recipients[0] of an
    unrelated broadcast) — deactivate once done."""
    with app.app_context():
        Student.query.filter(Student.id.in_(student_ids)).update(
            {Student.is_active: False}, synchronize_session=False)
        db.session.commit()


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


def _setup(app, with_billing=False):
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'CAN-Sess-{_SEQ[0]}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'CAN-Term-{_SEQ[0]}')
        db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'CAN-Class-{_SEQ[0]}', level=1); db.session.add(sc); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        if with_billing:
            item = FeeItem(name=f'CAN-Tuition-{_SEQ[0]}', is_active=True)
            db.session.add(item); db.session.flush()
            db.session.add(FeeStructure(term_id=term.id, class_id=sc.id, fee_item_id=item.id,
                                        amount=10000, is_active=True))

        student_ids = []
        for i in range(_COHORT_SIZE):
            s = Student(student_id=f'CAN{_SEQ[0]}{i:03d}', first_name=f'C{i}', surname='And',
                       gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                             is_active=True))
            db.session.add(ParentContact(student_id=s.id, name=f'Parent {i}',
                                         phone_number=f'080000000{i:02d}', is_primary=True))
            if with_billing:
                db.session.add(FeePayment(student_id=s.id, term_id=term.id, branch_id=bid,
                                          amount=4000, method='Cash',
                                          receipt_no=f'CAN-RCPT-{_SEQ[0]}-{i}'))
            student_ids.append(s.id)
        db.session.commit()
        return term.id, caa.id, student_ids


def test_class_audience_does_not_scale_with_class_size(app):
    term_id, caa_id, student_ids = _setup(app)
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        term = db.session.get(Term, term_id)
        caa = db.session.get(ClassArmAssignment, caa_id)

        def _resolve():
            return comms.resolve_audience('class', term, class_id=caa.class_id)

        n = _count_selects(app, 'students', _resolve)
        assert n < _COHORT_SIZE, f'{n} Student SELECTs for a {_COHORT_SIZE}-student class audience — looks like an N+1'

        targets = _resolve()
        got_ids = {t['student'].id for t in targets}
        assert got_ids == set(student_ids)
        # Contact lookup batched too: everyone should have their phone attached.
        for t in targets:
            assert t['phone'].startswith('080000000')
    _deactivate(app, student_ids)


def test_defaulters_audience_does_not_scale_with_cohort_size(app):
    term_id, caa_id, student_ids = _setup(app, with_billing=True)
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        term = db.session.get(Term, term_id)

        def _resolve():
            return comms.resolve_audience('defaulters', term)

        n = _count_selects(app, 'fee_payments', _resolve)
        assert n < _COHORT_SIZE, f'{n} FeePayment SELECTs for a {_COHORT_SIZE}-student defaulters audience — looks like an N+1'

        targets = _resolve()
        by_id = {t['student'].id: t['balance'] for t in targets}
        for sid in student_ids:
            assert sid in by_id
            assert abs(by_id[sid] - 6000) < 0.01   # 10000 billed - 4000 paid
    _deactivate(app, student_ids)


def test_contact_lookup_does_not_scale_with_student_count(app):
    _, _, student_ids = _setup(app)
    with app.test_request_context('/'):
        session['role'] = 'admin'; session['scope'] = 'central'
        n = _count_selects(app, 'parent_contacts',
                           lambda: comms.resolve_audience('students', None, student_ids=student_ids))
        assert n < _COHORT_SIZE, f'{n} ParentContact SELECTs for {_COHORT_SIZE} students — looks like an N+1'
    _deactivate(app, student_ids)
