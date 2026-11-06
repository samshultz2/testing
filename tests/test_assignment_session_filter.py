"""Assignment page "Add students": each available student carries the class
they were in per session, so the list can be filtered by academic session."""
import uuid

from config import Config
from models import (db, Student, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment)
from tests.conftest import login_token


def test_available_students_carry_their_class_per_session(app):
    with app.app_context():
        old = AcademicSession(name='2045/2046', is_active=False)
        new = AcademicSession(name='2046/2047', is_active=False)
        db.session.add_all([old, new]); db.session.flush()
        t_old = Term(session_id=old.id, term_number=3, name='Third Term')
        t_new = Term(session_id=new.id, term_number=1, name='First Term')
        db.session.add_all([t_old, t_new]); db.session.flush()
        jss1 = SchoolClass.query.filter_by(name='JSS1').first() or SchoolClass(name='JSS1', level=1)
        jss2 = SchoolClass.query.filter_by(name='JSS2').first() or SchoolClass(name='JSS2', level=2)
        db.session.add_all([jss1, jss2]); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        was = ClassArmAssignment(class_id=jss1.id, arm_id=arm.id, term_id=t_old.id)
        target = ClassArmAssignment(class_id=jss2.id, arm_id=arm.id, term_id=t_new.id)
        db.session.add_all([was, target]); db.session.flush()
        from models import Branch
        bid = Branch.get_default().id
        returning = Student(student_id='SF' + uuid.uuid4().hex[:6], first_name='Ret', surname='Sessfilter',
                            gender='Male', branch_id=bid)
        fresh = Student(student_id='SF' + uuid.uuid4().hex[:6], first_name='New', surname='Sessfilter',
                        gender='Male', branch_id=bid)
        db.session.add_all([returning, fresh]); db.session.flush()
        db.session.add(StudentEnrollment(student_id=returning.id, class_arm_assignment_id=was.id, is_active=True))
        db.session.commit()
        ids = (returning.id, fresh.id, target.id, str(old.id), was.display_name)
    ret_id, fresh_id, target_id, old_sid, was_name = ids
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    d = c.get(f'/academics/assignments/{target_id}', headers={'X-Requested-With': 'fetch'}).get_json()
    avail = {s['id']: s for s in d['available_students']}
    assert avail[ret_id]['classes'] == {old_sid: was_name}
    assert avail[fresh_id]['classes'] == {}
    assert any(str(x['id']) == old_sid for x in d['sessions'])
