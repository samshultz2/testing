"""Staff <-> User linking: the shared service plus the create-time checkboxes on
the Add User and Add Staff forms."""
import re
import uuid

from config import Config
from models import db, Branch, User, StaffMember, Teacher
from tests.conftest import login_token
from utils import staff_user_link as sul


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


# --- service ---------------------------------------------------------------- #
def test_create_staff_for_user_links_and_splits_name(app):
    with app.app_context():
        u = User(username='svc_u_' + uuid.uuid4().hex[:5], full_name='Ada Grace Okafor',
                 email=f'ada.{uuid.uuid4().hex[:5]}@s.edu', role='teacher', is_active=True,
                 branch_id=Branch.get_default().id)
        u.set_password('Zebra!Mango42Q'); db.session.add(u); db.session.flush()
        s = sul.create_staff_for_user(u)
        db.session.commit()
        assert s.user_id == u.id and s.first_name == 'Ada' and s.surname == 'Okafor'
        # idempotent
        assert sul.create_staff_for_user(u).id == s.id


def test_create_user_for_staff_makes_login_and_teacher(app):
    with app.app_context():
        s = StaffMember(staff_id=StaffMember.generate_staff_id(), first_name='Bola',
                        surname='Ade', email=f'bola.{uuid.uuid4().hex[:5]}@s.edu',
                        staff_type='Teaching', branch_id=Branch.get_default().id)
        db.session.add(s); db.session.flush()
        u, temp = sul.create_user_for_staff(s)
        db.session.commit()
        assert s.user_id == u.id and temp and u.must_change_password is True
        assert u.check_password(temp)                       # the temp password works
        assert Teacher.query.filter_by(user_id=u.id).first() is not None
        # idempotent — no second account
        u2, temp2 = sul.create_user_for_staff(s)
        assert u2.id == u.id and temp2 is None


# --- routes ----------------------------------------------------------------- #
def test_add_user_with_create_staff_checkbox(app):
    c = _admin(app)
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'k' * 64
    uname = 'linku_' + uuid.uuid4().hex[:5]
    c.post('/users/add', data={
        '_csrf_token': 'k' * 64, 'username': uname, 'full_name': 'Chidi Nwosu',
        'password': 'Zebra!Mango42Q', 'confirm_password': 'Zebra!Mango42Q',
        'role': 'staff', 'create_staff': 'on'}, follow_redirects=False)
    with app.app_context():
        u = User.query.filter_by(username=uname).first()
        assert u is not None
        assert StaffMember.query.filter_by(user_id=u.id).first() is not None


def test_add_staff_with_create_user_checkbox(app):
    c = _admin(app)
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'k' * 64
    sur = 'Link' + uuid.uuid4().hex[:5]
    c.post('/hr/staff/add', data={
        '_csrf_token': 'k' * 64, 'first_name': 'Grace', 'surname': sur,
        'email': f'grace.{uuid.uuid4().hex[:5]}@s.edu', 'staff_type': 'Teaching',
        'create_user': 'true'}, follow_redirects=False)
    with app.app_context():
        s = StaffMember.query.filter_by(surname=sur).first()
        assert s is not None and s.user_id is not None
        assert db.session.get(User, s.user_id) is not None
