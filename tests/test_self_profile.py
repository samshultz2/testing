"""Self-service profile: a signed-in user can edit their own safe details, but
never privileged fields (role, branch, salary)."""
import re
import uuid

from config import Config
from models import db, Branch, User, StaffMember
from tests.conftest import login_token
from utils import staff_user_link as sul

_PW = 'Zebra!Mango42Q'


def _user(app, **extra):
    with app.app_context():
        u = User(username='prof_' + uuid.uuid4().hex[:6], full_name='Old Name',
                 role='teacher', is_active=True, branch_id=Branch.get_default().id, **extra)
        u.set_password(_PW); u.must_change_password = False
        db.session.add(u); db.session.commit()
        return u.id


def _login(app, uid):
    with app.app_context():
        uname = db.session.get(User, uid).username
    c = app.test_client()
    c.post('/login', data={'username': uname, 'password': _PW, '_csrf_token': login_token(c)})
    return c


def _tok(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'p' * 64
    return 'p' * 64


def test_profile_updates_safe_fields(app):
    uid = _user(app)
    c = _login(app, uid)
    tok = _tok(c)
    c.post('/account', data={'_csrf_token': tok, 'full_name': 'New Name',
                             'phone': '08012345678', 'email': f'new.{uuid.uuid4().hex[:5]}@s.edu',
                             'theme': 'ocean'}, follow_redirects=True)
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.full_name == 'New Name' and u.phone == '08012345678' and u.theme == 'ocean'


def test_profile_cannot_change_role_or_branch(app):
    uid = _user(app)
    with app.app_context():
        before_role = db.session.get(User, uid).role
        before_branch = db.session.get(User, uid).branch_id
    c = _login(app, uid)
    tok = _tok(c)
    # attacker-style extra fields must be ignored by the allow-list
    c.post('/account', data={'_csrf_token': tok, 'full_name': 'X', 'role': 'admin',
                             'branch_id': '999', 'scope': 'central', 'view_only': 'off'},
           follow_redirects=True)
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.role == before_role and u.branch_id == before_branch


def test_profile_edits_linked_staff_contact_not_salary(app):
    uid = _user(app)
    with app.app_context():
        u = db.session.get(User, uid)
        s = sul.create_staff_for_user(u)
        s.salary = 500000; s.designation = 'Senior Teacher'
        db.session.commit()
        sid = s.id
    c = _login(app, uid)
    tok = _tok(c)
    c.post('/account', data={'_csrf_token': tok, 'full_name': 'Keep',
                             'emergency_name': 'Mrs Kin', 'emergency_phone': '08099',
                             'salary': '1', 'designation': 'CEO'}, follow_redirects=True)
    with app.app_context():
        s = db.session.get(StaffMember, sid)
        assert s.emergency_name == 'Mrs Kin' and s.emergency_phone == '08099'
        assert s.salary == 500000 and s.designation == 'Senior Teacher'   # untouched


def test_profile_rejects_duplicate_email(app):
    taken = f'taken.{uuid.uuid4().hex[:5]}@s.edu'
    _user(app, email=taken)
    uid2 = _user(app)
    c = _login(app, uid2)
    tok = _tok(c)
    r = c.post('/account', data={'_csrf_token': tok, 'full_name': 'Dup', 'email': taken},
               follow_redirects=True)
    assert 'already used' in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(User, uid2).email != taken


def test_profile_page_renders(app):
    uid = _user(app)
    html = _login(app, uid).get('/account').get_data(as_text=True)
    assert 'My profile' in html and 'name="full_name"' in html
