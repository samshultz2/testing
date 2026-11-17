"""Take payment: pay for particular fee items (e.g. only WAEC registration)."""
import json
import re
import uuid

from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    Student, StudentEnrollment, FeeItem, FeeStructure, FeePayment, FeePaymentItem)
from tests.conftest import auth_csrf
from tests.test_finance_defaulters_nplus1 import _admin

H = {'X-Requested-With': 'fetch'}


def _seed(app):
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'PI-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'PI-{tag}'); db.session.add(term); db.session.flush()
        cls = SchoolClass(name=f'PI-C-{tag}', level=1); db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        asg = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(asg); db.session.flush()
        tuition = FeeItem(name=f'Tuition {tag}', is_active=True)
        waec = FeeItem(name=f'WAEC registration {tag}', is_active=True)
        other = FeeItem(name=f'Not billed {tag}', is_active=True)
        db.session.add_all([tuition, waec, other]); db.session.flush()
        db.session.add_all([FeeStructure(term_id=term.id, class_id=cls.id, fee_item_id=tuition.id, amount=100000, is_active=True),
                            FeeStructure(term_id=term.id, class_id=cls.id, fee_item_id=waec.id, amount=30000, is_active=True)])
        s = Student(student_id=f'PI{tag}', first_name='Pay', surname='Items', gender='Female', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=asg.id, is_active=True))
        db.session.commit()
        return term.id, s.id, tuition.id, waec.id, other.id


def _pay(c, sid, tid, amount, items=None):
    data = {'_csrf_token': auth_csrf(c), 'student_id': sid, 'term_id': tid, 'amount': amount,
            'method': 'Cash', 'payment_date': '2026-11-17'}
    if items is not None:
        data['items'] = json.dumps(items)
    return c.post('/finance/payments/record', data=data, headers=H)


def _bill(c, sid, tid):
    html = c.get(f'/finance/payments/record?student_id={sid}&term_id={tid}').get_data(as_text=True)
    raw = re.search(r'<script type="application/json" id="fin-data">(.*?)</script>', html, re.S).group(1)
    data = json.loads(raw)
    if isinstance(data, str):            # |tojson of an already-serialised payload
        data = json.loads(data)
    return data['bill']


def test_pay_only_one_item_then_see_what_is_left(app):
    tid, sid, tu, wa, _ = _seed(app)
    c = _admin(app)
    r = _pay(c, sid, tid, 30000, [{'id': wa, 'amount': 30000}])
    assert r.get_json()['ok']
    with app.app_context():
        p = FeePayment.query.filter_by(student_id=sid, term_id=tid).one()
        assert [(i.fee_item_id, i.amount) for i in p.items] == [(wa, 30000)]
        pid = p.id
    b = _bill(c, sid, tid)
    lines = {l['id']: l for l in b['lines']}
    assert lines[wa]['left'] == 0 and lines[wa]['paid'] == 30000
    assert lines[tu]['left'] == 100000 and b['balance'] == 100000 and b['general_paid'] == 0
    html = c.get(f'/finance/payments/{pid}/receipt').get_data(as_text=True)
    assert 'Paid for' in html and 'WAEC registration' in html
    pdf = c.get(f'/finance/payments/{pid}/receipt.pdf')
    assert pdf.status_code == 200


def test_split_with_remainder_and_plain_payments_still_work(app):
    tid, sid, tu, wa, _ = _seed(app)
    c = _admin(app)
    assert _pay(c, sid, tid, 50000, [{'id': tu, 'amount': 40000}]).get_json()['ok']   # 10k toward the rest
    assert _pay(c, sid, tid, 5000).get_json()['ok']                                     # no items: whole bill
    b = _bill(c, sid, tid)
    lines = {l['id']: l for l in b['lines']}
    assert lines[tu]['paid'] == 40000 and b['general_paid'] == 15000 and b['balance'] == 75000


def test_bad_item_choices_are_refused(app):
    tid, sid, tu, wa, other = _seed(app)
    c = _admin(app)
    r = _pay(c, sid, tid, 10000, [{'id': other, 'amount': 10000}])
    assert not r.get_json()['ok'] and 'not on this student' in r.get_json()['error']
    r = _pay(c, sid, tid, 10000, [{'id': tu, 'amount': 8000}, {'id': wa, 'amount': 5000}])
    assert not r.get_json()['ok'] and 'more than the payment' in r.get_json()['error']
    with app.app_context():
        assert FeePayment.query.filter_by(student_id=sid, term_id=tid).count() == 0


def test_reversing_a_payment_removes_its_item_split(app):
    tid, sid, tu, wa, _ = _seed(app)
    c = _admin(app)
    _pay(c, sid, tid, 30000, [{'id': wa, 'amount': 30000}])
    with app.app_context():
        pid = FeePayment.query.filter_by(student_id=sid, term_id=tid).one().id
    r = c.post(f'/finance/payments/{pid}/delete', data={'_csrf_token': auth_csrf(c), 'reason': 'test'}, headers=H)
    assert r.status_code in (200, 302)
    with app.app_context():
        assert FeePaymentItem.query.filter_by(payment_id=pid).count() == 0
