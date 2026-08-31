"""Finance Phase 3: installment plans (term payment schedule)."""
import re
from datetime import date, timedelta

from models import (db, Student, Term, AcademicSession, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, FeeItem, FeeStructure,
                    FeePayment, InstallmentPlan, AdditionalCharge, Branch)

TOK = 'a' * 64


def _enrolled_with_fee(app, sid, fee):
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name='INS-Sess').first() or AcademicSession(name='INS-Sess')
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(name='INS-Term').first() or Term(session_id=ssn.id, term_number=1, name='INS-Term')
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='INS-Class').first() or SchoolClass(name='INS-Class', level=1)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(name='INS-Arm').first() or ClassArm(name='INS-Arm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id))
        db.session.add(caa); db.session.flush()
        st = Student.query.filter_by(student_id=sid).first()
        if not st:
            st = Student(student_id=sid, first_name='I', surname='N', gender='Male',
                         is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.flush()
        if not StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first():
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        item = FeeItem.query.filter_by(name='INS-Tuition').first() or FeeItem(name='INS-Tuition')
        db.session.add(item); db.session.flush()
        if not FeeStructure.query.filter_by(term_id=term.id, class_id=cls.id, fee_item_id=item.id).first():
            db.session.add(FeeStructure(term_id=term.id, class_id=cls.id, arm_id=None, fee_item_id=item.id, amount=fee))
        db.session.commit()
        return term.id, st.id


def _admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True; s['role'] = 'super_admin'; s['_csrf_token'] = TOK
    return c


def _plan(app, term_id):
    with app.app_context():
        InstallmentPlan.query.filter_by(term_id=term_id).delete()
        db.session.add(InstallmentPlan(term_id=term_id, class_id=None, label='1st', percent=40,
                                       due_date=date.today() - timedelta(days=1), sort_order=0))
        db.session.add(InstallmentPlan(term_id=term_id, class_id=None, label='2nd', percent=60,
                                       due_date=date.today() + timedelta(days=30), sort_order=1))
        db.session.commit()


def test_student_status_expected_and_behind(app):
    from utils import finance_installments as I
    term_id, _ = _enrolled_with_fee(app, sid='INS-STU', fee=10000)
    _plan(app, term_id)
    with app.app_context():
        st = Student.query.filter_by(student_id='INS-STU').first()
        db.session.add(FeePayment(student_id=st.id, term_id=term_id, amount=2000, method='Cash',
                                  branch_id=Branch.get_default().id))
        db.session.commit()
        status = I.student_status(st.id, term_id)
        assert status['has_plan'] and status['payable'] == 10000 and status['paid'] == 2000
        # 1st installment (40% of 10000 = 4000) is due; only 2000 paid -> behind 2000
        assert status['expected_to_date'] == 4000 and status['behind'] == 2000
        assert status['on_track'] is False
        assert status['next_due']['label'] == '2nd'


def test_save_and_class_override(app):
    from utils import finance_installments as I
    term_id, _ = _enrolled_with_fee(app, sid='INS-OV', fee=5000)
    with app.app_context():
        cls = SchoolClass.query.filter_by(name='INS-Class').first()
        InstallmentPlan.query.filter_by(term_id=term_id).delete(); db.session.commit()
        I.save_plan(term_id, None, [{'label': 'Full', 'percent': 100, 'due_date': date.today()}])
        assert len(I.get_plan(term_id, cls.id)) == 1                 # falls back to term-wide
        I.save_plan(term_id, cls.id, [{'label': 'A', 'percent': 50, 'due_date': date.today()},
                                      {'label': 'B', 'percent': 50, 'due_date': date.today()}])
        assert len(I.get_plan(term_id, cls.id)) == 2                 # class-specific overrides


def test_installments_page_and_save_route(app):
    term_id, _ = _enrolled_with_fee(app, sid='INS-PG', fee=8000)
    c = _admin(app)
    r = c.get(f'/finance/installments?term_id={term_id}')
    assert r.status_code == 200 and 'Installment plans' in r.get_data(as_text=True)
    c.post('/finance/installments/save', data={
        '_csrf_token': TOK, 'term_id': term_id, 'class_id': '',
        'label': ['1st', '2nd'], 'percent': ['30', '70'],
        'due': [date.today().isoformat(), date.today().isoformat()]})
    from utils import finance_installments as I
    with app.app_context():
        assert len(I.get_plan(term_id, None)) == 2


def test_installment_penalty_targets_only_behind(app):
    term_id, _ = _enrolled_with_fee(app, sid='INS-STU', fee=10000)
    _plan(app, term_id)
    c = _admin(app)
    with app.app_context():
        st = Student.query.filter_by(student_id='INS-STU').first()
        AdditionalCharge.query.filter_by(term_id=term_id, category='Penalty').delete()
        # ensure a payment exists but leaves them behind
        if not FeePayment.query.filter_by(student_id=st.id, term_id=term_id).first():
            db.session.add(FeePayment(student_id=st.id, term_id=term_id, amount=1000, method='Cash',
                                      branch_id=Branch.get_default().id))
        db.session.commit()
    c.post('/finance/billing-tools/penalties',
           data={'_csrf_token': TOK, 'term_id': term_id, 'ptype': 'installment', 'value': '500'})
    with app.app_context():
        st = Student.query.filter_by(student_id='INS-STU').first()
        pen = AdditionalCharge.query.filter_by(student_id=st.id, term_id=term_id, category='Penalty').all()
        assert len(pen) == 1 and pen[0].amount == 500
