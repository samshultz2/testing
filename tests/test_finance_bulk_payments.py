"""Take payment for several students at once."""
import uuid

from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    Student, StudentEnrollment, FeeItem, FeeStructure, FeePayment)
from tests.conftest import auth_csrf
from tests.test_finance_defaulters_nplus1 import _admin

H = {'X-Requested-With': 'fetch'}


def _seed(app, n=3):
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'BP-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'BP-{tag}'); db.session.add(term); db.session.flush()
        cls = SchoolClass(name=f'BP-C-{tag}', level=1); db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        asg = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(asg); db.session.flush()
        tuition = FeeItem(name=f'Tuition {tag}', is_active=True)
        waec = FeeItem(name=f'WAEC {tag}', is_active=True)
        other = FeeItem(name=f'Other {tag}', is_active=True)
        db.session.add_all([tuition, waec, other]); db.session.flush()
        db.session.add_all([FeeStructure(term_id=term.id, class_id=cls.id, fee_item_id=tuition.id, amount=50000, is_active=True),
                            FeeStructure(term_id=term.id, class_id=cls.id, fee_item_id=waec.id, amount=20000, is_active=True)])
        ids = []
        for i in range(n):
            s = Student(student_id=f'BP{tag}{i}', first_name=f'S{i}', surname='Bulk', gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=asg.id, is_active=True))
            ids.append(s.id)
        # a student with no class this term
        lone = Student(student_id=f'BP{tag}x', first_name='Lone', surname='Bulk', gender='Male', is_active=True, branch_id=bid)
        db.session.add(lone); db.session.commit()
        return term.id, ids, lone.id, tuition.id, waec.id, other.id


def _bulk(c, tid, ids, **kw):
    data = {'_csrf_token': auth_csrf(c), 'term_id': tid, 'student_ids': ','.join(map(str, ids)),
            'method': 'Transfer', 'payment_date': '2026-11-20', 'mode': 'fixed', **kw}
    return c.post('/finance/payments/record-bulk', data=data, headers=H)


def test_same_amount_for_several_students_gives_one_receipt_each(app):
    tid, ids, lone, tuition, waec, other = _seed(app)
    c = _admin(app)
    r = _bulk(c, tid, ids, amount=15000, reference='TLR-77')
    j = r.get_json()
    assert j['ok'], j
    with app.app_context():
        ps = FeePayment.query.filter(FeePayment.student_id.in_(ids), FeePayment.term_id == tid).all()
        assert len(ps) == 3 and all(p.amount == 15000 and p.reference == 'TLR-77' and p.method == 'Transfer' for p in ps)
        assert len({p.receipt_no for p in ps}) == 3
    page = c.get(j['redirect'], headers=H).get_json()
    assert page['page'] == 'payment_batch' and len(page['payments']) == 3 and page['total'] == 45000
    pdf = c.get(page['pdf_all_url'])
    assert pdf.status_code == 200 and pdf.data[:4] == b'%PDF'
    # same reference again is refused for everyone and nothing is added
    j2 = _bulk(c, tid, ids, amount=15000, reference='TLR-77').get_json()
    assert not j2['ok'] and 'Nothing was recorded' in j2['error']
    with app.app_context():
        assert FeePayment.query.filter(FeePayment.student_id.in_(ids), FeePayment.term_id == tid).count() == 3


def test_each_balance_and_fee_item(app):
    tid, ids, lone, tuition, waec, other = _seed(app)
    c = _admin(app)
    _bulk(c, tid, ids[:1], amount=70000)                 # first student fully paid
    j = _bulk(c, tid, ids, mode='balance', fee_item_id=waec).get_json()
    assert j['ok'] and '1 skipped' in j['message'], j
    with app.app_context():
        ps = FeePayment.query.filter(FeePayment.student_id.in_(ids[1:]), FeePayment.term_id == tid).all()
        assert len(ps) == 2 and all(p.amount == 20000 and p.items[0].fee_item_id == waec for p in ps)


def test_problems_stop_the_whole_batch(app):
    tid, ids, lone, tuition, waec, other = _seed(app)
    c = _admin(app)
    j = _bulk(c, tid, ids + [lone], amount=1000).get_json()
    assert not j['ok'] and 'no class this term' in j['error']
    j = _bulk(c, tid, ids, amount=1000, fee_item_id=other).get_json()
    assert not j['ok'] and 'not billed' in j['error']
    assert not _bulk(c, tid, ids, amount=0).get_json()['ok']
    with app.app_context():
        assert FeePayment.query.filter(FeePayment.student_id.in_(ids)).count() == 0


def test_preview_lists_balances_and_items(app):
    tid, ids, lone, tuition, waec, other = _seed(app, n=2)
    c = _admin(app)
    j = c.get(f'/finance/payments/bulk-preview?term_id={tid}&ids={ids[1]},{ids[0]},{lone}').get_json()
    rows = j['students']
    assert [r['id'] for r in rows] == [ids[1], ids[0], lone]
    assert rows[0]['balance'] == 70000 and {i['id'] for i in rows[0]['items']} == {tuition, waec}
    assert rows[2]['has_bill'] is False
