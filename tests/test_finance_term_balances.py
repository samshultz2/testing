"""Owing figures come from one calculation (utils.finance.term_balances):
a student enrolled twice in a term is billed once, extra charges count,
students who paid in full are counted as cleared, and the dashboard's
"students owing" agrees with the Defaulters page."""
import uuid

from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, FeeItem,
                    FeeStructure, FeePayment, AdditionalCharge)
from utils.finance import term_balances
from tests.test_finance_defaulters_nplus1 import _admin


def _seed(app):
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'TB-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'TB-{tag}'); db.session.add(term); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        paid_cls = SchoolClass(name=f'TB-A-{tag}', level=1)
        free_cls = SchoolClass(name=f'TB-B-{tag}', level=2)          # no fee set
        db.session.add_all([paid_cls, free_cls]); db.session.flush()
        a1 = ClassArmAssignment(class_id=paid_cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        a2 = ClassArmAssignment(class_id=free_cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        arm2 = ClassArm(name=f'TB{tag}'); db.session.add(arm2); db.session.flush()
        a1b = ClassArmAssignment(class_id=paid_cls.id, arm_id=arm2.id, term_id=term.id, branch_id=bid)
        db.session.add_all([a1, a2, a1b]); db.session.flush()
        item = FeeItem(name=f'TB-Tuition-{tag}', is_active=True); db.session.add(item); db.session.flush()
        db.session.add(FeeStructure(term_id=term.id, class_id=paid_cls.id, fee_item_id=item.id,
                                    amount=10000, is_active=True))
        st = {}
        for k in ('twice', 'cleared', 'charged', 'free'):
            s = Student(student_id=f'TB{tag}{k}', first_name=k, surname='Bal', gender='Male',
                        is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush(); st[k] = s.id
        for k in ('twice', 'cleared', 'charged'):
            db.session.add(StudentEnrollment(student_id=st[k], class_arm_assignment_id=a1.id, is_active=True))
        # Moved arms without closing the old enrolment: two active rows this term.
        db.session.add(StudentEnrollment(student_id=st['twice'], class_arm_assignment_id=a1b.id, is_active=True))
        db.session.add(StudentEnrollment(student_id=st['free'], class_arm_assignment_id=a2.id, is_active=True))
        db.session.add(FeePayment(student_id=st['twice'], term_id=term.id, branch_id=bid, amount=4000,
                                  method='Cash', receipt_no=f'TB-{tag}-1'))
        db.session.add(FeePayment(student_id=st['cleared'], term_id=term.id, branch_id=bid, amount=10000,
                                  method='Cash', receipt_no=f'TB-{tag}-2'))
        db.session.add(FeePayment(student_id=st['charged'], term_id=term.id, branch_id=bid, amount=10000,
                                  method='Cash', receipt_no=f'TB-{tag}-3'))
        db.session.add(AdditionalCharge(student_id=st['charged'], term_id=term.id, kind='charge',
                                        amount=2500, description='Late fee'))
        db.session.commit()
        return term.id, st


def test_each_student_once_with_charges(app):
    term_id, st = _seed(app)
    with app.app_context():
        b = term_balances(term_id, scope=False)
        assert len(b) == 4
        assert b[st['twice']]['balance'] == 6000          # billed once, not 20000
        assert b[st['cleared']]['balance'] == 0
        assert b[st['charged']]['balance'] == 2500        # extra charge counts
        assert b[st['free']]['payable'] == 0
    # The finance overview agrees with the Defaulters page.
    html = _admin(app).get(f'/finance/?term_id={term_id}').get_data(as_text=True).replace(' ', '')
    assert '"defaulter_count":2' in html
    assert '"expected":30000' in html                      # duplicate enrolment not billed twice
    assert '"enrolled":4' in html


def test_defaulters_page_reports_whole_term(app):
    term_id, st = _seed(app)
    c = _admin(app)
    html = c.get(f'/finance/defaulters?term_id={term_id}').get_data(as_text=True)
    for frag in ('"enrolled": 4', '"cleared": 2', '"all_paid": 24000', '"all_payable": 32500', '"no_fee": 1'):
        assert frag.replace(' ', '') in html.replace(' ', ''), frag
