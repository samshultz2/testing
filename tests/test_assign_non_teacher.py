"""Class/subject assignment must work for any teaching staff member — not only
accounts whose role is exactly 'teacher'. Granular-permission staff (role
'staff' + a permission group) can be enabled for teaching and assigned classes.
"""
from config import Config
from models import (db, User, Teacher, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment)
from tests.conftest import login_token, auth_csrf


def _admin(app):
    client = app.test_client()
    tok = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return client


def _staff_user(app, username='granular_teacher'):
    with app.app_context():
        u = User(username=username, full_name='Granular Staff', role='staff', is_active=True)
        u.set_password('CorrectHorse9')
        db.session.add(u); db.session.commit()
        return u.id


def _a_class(app):
    """An active term with one class-arm assignment to assign to."""
    from models import Branch
    with app.app_context():
        bid = Branch.get_default().id
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            sess = AcademicSession.query.first()
            if not sess:
                sess = AcademicSession(name='ANT-Session')
                db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='ANT-Term', is_active=True)
            db.session.add(term); db.session.flush()
        cls = SchoolClass.query.order_by(SchoolClass.level).first()
        arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.commit()
        return caa.id


def test_enable_teaching_creates_profile_for_staff(app):
    uid = _staff_user(app, 'enable_me')
    client = _admin(app)
    tok = auth_csrf(client)
    r = client.post(f'/users/{uid}/enable-teaching',
                    data={'_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'}).get_json()
    assert r['ok']
    with app.app_context():
        assert db.session.get(User, uid).teacher_profile is not None


def test_assign_class_to_non_teacher_staff(app):
    uid = _staff_user(app, 'assign_me')
    caa_id = _a_class(app)
    client = _admin(app)
    tok = auth_csrf(client)
    # No pre-existing teacher profile — the assign route creates it.
    r = client.post(f'/users/{uid}/assign-class',
                    data={'assignment_id': caa_id, 'is_form_teacher': 'on', '_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'}).get_json()
    assert r['ok']
    with app.app_context():
        t = db.session.get(User, uid).teacher_profile
        assert t is not None
        assert t.class_assignments.filter_by(is_active=True).count() == 1


def test_admin_account_cannot_be_assigned(app):
    with app.app_context():
        u = User(username='an_admin', full_name='Admin Acct', role='admin', is_active=True)
        u.set_password('CorrectHorse9'); db.session.add(u); db.session.commit()
        uid = u.id
    client = _admin(app)
    tok = auth_csrf(client)
    r = client.post(f'/users/{uid}/enable-teaching',
                    data={'_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'})
    # Rejected (JSON error or redirect with flash) — never creates a profile.
    with app.app_context():
        assert db.session.get(User, uid).teacher_profile is None
