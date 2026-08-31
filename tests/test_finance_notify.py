"""Finance Phase 4: overdue fee reminders + failed-verification alerts (in-app)."""
from datetime import date, timedelta

from models import (db, Student, Term, AcademicSession, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, FeeItem, FeeStructure,
                    InstallmentPlan, Notification, Branch)


def _behind_student(app):
    """An enrolled student who owes 10000 with 40% due yesterday and nothing paid."""
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name='FN-Sess').first() or AcademicSession(name='FN-Sess')
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(name='FN-Term').first() or Term(session_id=ssn.id, term_number=1, name='FN-Term')
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='FN-Class').first() or SchoolClass(name='FN-Class', level=1)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(name='FN-Arm').first() or ClassArm(name='FN-Arm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id))
        db.session.add(caa); db.session.flush()
        st = Student.query.filter_by(student_id='FN-STU').first()
        if not st:
            st = Student(student_id='FN-STU', first_name='F', surname='N', gender='Male',
                         is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.flush()
        if not StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first():
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        item = FeeItem.query.filter_by(name='FN-Tuition').first() or FeeItem(name='FN-Tuition')
        db.session.add(item); db.session.flush()
        if not FeeStructure.query.filter_by(term_id=term.id, class_id=cls.id, fee_item_id=item.id).first():
            db.session.add(FeeStructure(term_id=term.id, class_id=cls.id, arm_id=None, fee_item_id=item.id, amount=10000))
        InstallmentPlan.query.filter_by(term_id=term.id).delete()
        db.session.add(InstallmentPlan(term_id=term.id, class_id=None, label='1st', percent=40,
                                       due_date=date.today() - timedelta(days=1), sort_order=0))
        db.session.commit()
        return term.id, st.id


def test_overdue_detection_and_admin_reminder(app):
    from utils import finance_notify
    term_id, sid = _behind_student(app)
    with app.app_context():
        rows, total = finance_notify.overdue_students(term_id)
        assert any(s.id == sid for s, _ in rows)
        assert total >= 4000                              # 40% of 10000 due, nothing paid

        before = Notification.query.filter_by(role='admin').count()
        summary = finance_notify.run_fee_reminders(term_id)
        assert summary['count'] >= 1
        after = Notification.query.filter_by(role='admin').count()
        assert after == before + 1                        # one admin alert created


def test_failed_verification_alert(app):
    from utils import finance_notify
    with app.app_context():
        before = Notification.query.filter_by(role='admin', category='error').count()
        finance_notify.payment_verification_failed('REF-XYZ', 'gateway down')
        after = Notification.query.filter_by(role='admin', category='error').count()
        assert after == before + 1
