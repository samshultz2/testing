"""A form teacher who adds a student auto-enrols them into their form class."""
import re

from models import (db, Branch, User, Teacher, Student, SchoolClass, ClassArm,
                     ClassArmAssignment, StudentEnrollment, TeacherClassAssignment,
                     AcademicSession, Term)
from tests.conftest import login_token


def _active_term_id(app):
    with app.app_context():
        t = Term.query.filter_by(is_active=True).first()
        if not t:
            s = AcademicSession(name='AE-Sess', is_active=True)
            db.session.add(s); db.session.flush()
            t = Term(session_id=s.id, term_number=1, name='AE-Term', is_active=True)
            db.session.add(t); db.session.commit()
        return t.id


def _setup_form_teacher(app):
    tid = _active_term_id(app)
    with app.app_context():
        existing = User.query.filter_by(username='ae_teacher').first()
        if existing:
            return dict(uid=existing.id,
                        caa=list(existing.teacher_profile.form_class_ids)[0])
        bid = Branch.get_default().id
        sc = SchoolClass.query.first()
        arm = ClassArm.query.first()
        caa = ClassArmAssignment.query.filter_by(
            class_id=sc.id, arm_id=arm.id, term_id=tid).first()
        if not caa:
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id,
                                     term_id=tid, branch_id=bid)
            db.session.add(caa); db.session.flush()
        u = User(username='ae_teacher', role='teacher', scope='branch', branch_id=bid)
        u.set_password('secret123'); u.set_modules(['students'])
        db.session.add(u); db.session.flush()
        t = Teacher(user_id=u.id, employee_id='AE001', branch_id=bid,
                    can_view_student_details=True)
        db.session.add(t); db.session.flush()
        db.session.add(TeacherClassAssignment(
            teacher_id=t.id, class_arm_assignment_id=caa.id, is_form_teacher=True))
        db.session.commit()
        return dict(uid=u.id, caa=caa.id)


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def test_teacher_add_student_enrols_into_form_class(app):
    ids = _setup_form_teacher(app)
    client = _login(app, 'ae_teacher')

    page = client.get('/students/add').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page)
    token = m.group(1) if m else None
    # The form should offer the teacher's form class, pre-selected.
    assert '(your class)' in page

    with app.app_context():
        before = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=ids['caa']).count()

    # No class_arm_assignment_id submitted -> should default to the form class.
    resp = client.post('/students/add',
                       data={'surname': 'Auto', 'first_name': 'Enrol',
                             'gender': 'Male', '_csrf_token': token},
                       follow_redirects=False)
    assert resp.status_code in (302, 303)

    with app.app_context():
        after = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=ids['caa']).count()
        assert after == before + 1
        # the newest student really is the one we just enrolled
        st = Student.query.filter_by(first_name='Enrol', surname='Auto').first()
        assert st is not None
        assert StudentEnrollment.query.filter_by(
            student_id=st.id, class_arm_assignment_id=ids['caa'],
            is_active=True).first() is not None
