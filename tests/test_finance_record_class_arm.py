"""Take payment: the class picker gets class, arm and a student count for each
class arm, so the page can pick a class first and then its arm."""
import json
import re
import uuid

from models import db, Branch, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment, Student, StudentEnrollment
from tests.test_finance_defaulters_nplus1 import _admin


def test_record_payment_sends_class_and_arm(app):
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'RP-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'RP-{tag}'); db.session.add(term); db.session.flush()
        cls = SchoolClass(name=f'RP-C-{tag}', level=1); db.session.add(cls); db.session.flush()
        arms = [ClassArm(name=f'Gold{tag}'), ClassArm(name=f'Blue{tag}')]
        db.session.add_all(arms); db.session.flush()
        asg = [ClassArmAssignment(class_id=cls.id, arm_id=a.id, term_id=term.id, branch_id=bid) for a in arms]
        db.session.add_all(asg); db.session.flush()
        for i in range(3):
            s = Student(student_id=f'RP{tag}{i}', first_name='P', surname=f'Rp{i}', gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=asg[0 if i < 2 else 1].id, is_active=True))
        db.session.commit()
        term_id, cid = term.id, cls.id
    html = _admin(app).get(f'/finance/payments/record?term_id={term_id}').get_data(as_text=True)
    m = re.search(r'"assignments":\s*(\[.*?\])', html)
    rows = [a for a in json.loads(m.group(1)) if a['class_id'] == cid]
    assert {(a['class_name'], a['arm'], a['students']) for a in rows} == {
        (f'RP-C-{tag}', f'Gold{tag}', 2), (f'RP-C-{tag}', f'Blue{tag}', 1)}


def test_deleted_students_are_not_listed(app):
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'RD-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'RD-{tag}'); db.session.add(term); db.session.flush()
        cls = SchoolClass(name=f'RD-C-{tag}', level=1); db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(is_default=True).first() or ClassArm.query.first()
        asg = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(asg); db.session.flush()
        for i, live in enumerate((True, False)):
            s = Student(student_id=f'RD{tag}{i}', first_name='Del' if not live else 'Live', surname=f'Rd{tag}',
                        gender='Male', is_active=live, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=asg.id, is_active=True))
        db.session.commit()
        term_id, aid = term.id, asg.id
    html = _admin(app).get(f'/finance/payments/record?term_id={term_id}&assignment_id={aid}').get_data(as_text=True)
    assert f'RD{tag}0' in html and f'RD{tag}1' not in html
