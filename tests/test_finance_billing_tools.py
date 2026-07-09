"""Finance Phase 3: additional charges, bulk billing, penalties, credit notes,
and audited payment reversal."""
import re
from datetime import date

from models import (db, AdditionalCharge, FeePayment, Student, Term, AcademicSession,
                    SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment, Branch)


def _term_and_student(app, sid='BT-STU', enrol=False):
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name='BT-Sess').first() or AcademicSession(name='BT-Sess')
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(name='BT-Term').first() or Term(session_id=ssn.id, term_number=1, name='BT-Term')
        db.session.add(term); db.session.flush()
        st = Student.query.filter_by(student_id=sid).first()
        if not st:
            st = Student(student_id=sid, first_name='B', surname='T', gender='Male',
                         is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.flush()
        if enrol:
            cls = SchoolClass.query.filter_by(name='BT-Class').first() or SchoolClass(name='BT-Class', level=1)
            db.session.add(cls); db.session.flush()
            arm = ClassArm.query.filter_by(name='BT-Arm').first() or ClassArm(name='BT-Arm', is_active=True)
            db.session.add(arm); db.session.flush()
            caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first()
                   or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id))
            db.session.add(caa); db.session.flush()
            if not StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first():
                db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return term.id, st.id


TOK = 'a' * 64


def _admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['role'] = 'super_admin'
        s['_csrf_token'] = TOK
    return c


def test_charges_and_credit_notes_sum_correctly(app):
    from utils.finance import student_charges, charges_map
    term_id, sid = _term_and_student(app)
    with app.app_context():
        AdditionalCharge.query.filter_by(student_id=sid, term_id=term_id).delete()
        db.session.add(AdditionalCharge(student_id=sid, term_id=term_id, kind='charge', amount=1500, category='Excursion'))
        db.session.add(AdditionalCharge(student_id=sid, term_id=term_id, kind='credit', amount=500, category='Credit Note'))
        db.session.commit()
        ch, cr = student_charges(sid, term_id)
        assert ch == 1500 and cr == 500
        assert charges_map(term_id).get(sid) == 1000        # net (charge - credit)


def test_billing_tools_page_and_bulk_charge(app):
    term_id, sid = _term_and_student(app, sid='BT-BULK', enrol=True)
    c = _admin(app)
    page = c.get(f'/finance/billing-tools?term_id={term_id}').get_data(as_text=True)
    assert 'Billing Tools' in page and 'Bulk charge' in page
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', page).group(1)
    c.post('/finance/billing-tools/bulk-charge',
           data={'_csrf_token': tok, 'term_id': term_id, 'kind': 'charge',
                 'category': 'Excursion', 'amount': '2000', 'description': 'Zoo trip'})
    with app.app_context():
        got = AdditionalCharge.query.filter_by(student_id=sid, term_id=term_id, category='Excursion').first()
        assert got is not None and got.amount == 2000 and got.kind == 'charge'


def test_remove_charge(app):
    term_id, sid = _term_and_student(app)
    c = _admin(app)
    with app.app_context():
        ch = AdditionalCharge(student_id=sid, term_id=term_id, kind='charge', amount=100, category='X')
        db.session.add(ch); db.session.commit()
        cid = ch.id
    page = c.get(f'/finance/billing-tools?term_id={term_id}').get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', page).group(1)
    c.post(f'/finance/billing-tools/charge/{cid}/remove', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(AdditionalCharge, cid) is None


def test_apply_penalty_to_debtors_and_idempotent(app):
    from models import FeeItem, FeeStructure
    term_id, sid = _term_and_student(app, sid='BT-PEN', enrol=True)
    c = _admin(app)
    with app.app_context():
        st = Student.query.filter_by(student_id='BT-PEN').first()
        caa = StudentEnrollment.query.filter_by(student_id=st.id, is_active=True).first().class_arm_assignment
        item = FeeItem.query.filter_by(name='BT-Tuition').first() or FeeItem(name='BT-Tuition')
        db.session.add(item); db.session.flush()
        if not FeeStructure.query.filter_by(term_id=term_id, class_id=caa.class_id, fee_item_id=item.id).first():
            db.session.add(FeeStructure(term_id=term_id, class_id=caa.class_id, arm_id=None,
                                        fee_item_id=item.id, amount=5000))
        AdditionalCharge.query.filter_by(term_id=term_id, category='Penalty').delete()
        db.session.commit()

    c.post('/finance/billing-tools/penalties',
           data={'_csrf_token': TOK, 'term_id': term_id, 'ptype': 'fixed', 'value': '1000'})
    with app.app_context():
        st = Student.query.filter_by(student_id='BT-PEN').first()
        pens = AdditionalCharge.query.filter_by(student_id=st.id, term_id=term_id, category='Penalty').all()
        assert len(pens) == 1 and pens[0].amount == 1000          # debtor penalised

    # re-run must not double-charge
    c.post('/finance/billing-tools/penalties',
           data={'_csrf_token': TOK, 'term_id': term_id, 'ptype': 'fixed', 'value': '1000'})
    with app.app_context():
        st = Student.query.filter_by(student_id='BT-PEN').first()
        assert AdditionalCharge.query.filter_by(student_id=st.id, term_id=term_id, category='Penalty').count() == 1


def test_payment_reversal_is_audited_and_reverses_ledger(app):
    from models import FinanceTransaction, AuditLog
    term_id, sid = _term_and_student(app, sid='BT-REV')
    c = _admin(app)
    with app.app_context():
        p = FeePayment(student_id=sid, term_id=term_id, amount=4000, method='Cash',
                       receipt_no='RCP-REV-1', branch_id=Branch.get_default().id)
        db.session.add(p); db.session.commit()
        pid = p.id
        assert FinanceTransaction.query.filter_by(origin_type='fee_payment', origin_id=pid).first() is not None
    c.post(f'/finance/payments/{pid}/delete', data={'_csrf_token': TOK, 'reason': 'duplicate entry'})
    with app.app_context():
        # payment gone, ledger reversed, and the reversal is audited with the reason
        orig = FinanceTransaction.query.filter_by(origin_type='fee_payment', origin_id=pid).first()
        assert orig.reversed is True
        assert AuditLog.query.filter(AuditLog.action == 'finance.payment_reversed',
                                     AuditLog.detail.like('%duplicate entry%')).first() is not None
