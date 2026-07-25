"""Staff self-onboarding: invite link -> pending signup -> admin approval -> user."""
import re

from config import Config
from tests.conftest import login_token


def _branch_and_group(app):
    from models import db, Branch, PermissionGroup
    b = Branch.get_default()
    g = PermissionGroup(name='Principals'); g.set_permissions({'results': 'edit'})
    db.session.add(g); db.session.commit()
    return b.id, g.id


def test_invite_signup_approve_flow(app):
    from models import db, StaffInvite, StaffSignup, User
    from utils import staff_invite as svc
    with app.app_context():
        bid, gid = _branch_and_group(app)
        inv = svc.create_invite(label='Principals', role='admin', permission_group_id=gid,
                                branch_id=None, scope='branch', max_uses=5, expires_days=14,
                                created_by='root')
        assert inv.usable and inv.token

        s, err = svc.submit_signup(inv, full_name='Jane Doe', username='jane',
                                   email='jane@x.com', phone='080', password='secret12',
                                   branch_id=bid, position='Principal')
        assert err is None and s.status == 'pending'
        assert db.session.get(StaffInvite, inv.id).uses == 1
        assert User.query.filter_by(username='jane').first() is None    # no account yet

        u, err = svc.approve_signup(s, 'root')
        assert err is None
        assert u.is_active and u.role == 'admin'
        assert u.permission_group_id == gid and u.branch_id == bid
        assert u.check_password('secret12')             # password they set carries over
        assert 'results' in u.permission_map            # group permissions applied
        assert db.session.get(StaffSignup, s.id).status == 'approved'


def test_approval_creates_hr_staff_member(app):
    """Approving a signup also files the joiner in HR, linked to their new login."""
    from models import db, StaffMember
    from utils import staff_invite as svc
    with app.app_context():
        bid, gid = _branch_and_group(app)
        inv = svc.create_invite(label='Teachers', role='teacher', permission_group_id=None,
                                branch_id=bid, scope='branch', max_uses=None, expires_days=None,
                                created_by='root')
        s, err = svc.submit_signup(inv, full_name='Ada N. Okeke', username='ada',
                                   email='ada@x.com', phone='0801', password='secret12',
                                   branch_id=None, position='Senior Teacher',
                                   gender='Female', staff_type='Teaching',
                                   qualification='B.Ed')
        assert err is None
        u, err = svc.approve_signup(s, 'root')
        assert err is None

        sm = StaffMember.query.filter_by(user_id=u.id).first()
        assert sm is not None
        assert sm.first_name == 'Ada' and sm.surname == 'Okeke' and sm.middle_name == 'N.'
        assert sm.gender == 'Female' and sm.qualification == 'B.Ed'
        assert sm.designation == 'Senior Teacher' and sm.branch_id == bid
        assert (sm.staff_type or 'Teaching') == 'Teaching'


def test_signup_validation(app):
    from models import db, User
    from utils import staff_invite as svc
    with app.app_context():
        bid, gid = _branch_and_group(app)
        u = User(username='taken', role='teacher'); u.set_password('x' * 8)
        db.session.add(u); db.session.commit()
        inv = svc.create_invite(label='T', role='teacher', permission_group_id=None,
                                branch_id=bid, scope='branch', max_uses=None, expires_days=None,
                                created_by='root')
        _, e1 = svc.submit_signup(inv, full_name='A', username='taken', email=None,
                                  phone=None, password='longenough', branch_id=None, position=None)
        assert e1 and 'taken' in e1.lower()
        _, e2 = svc.submit_signup(inv, full_name='A', username='fresh', email=None,
                                  phone=None, password='short', branch_id=None, position=None)
        assert e2 and 'characters' in e2.lower()


def test_reject_signup(app):
    from models import db, StaffSignup, User
    from utils import staff_invite as svc
    with app.app_context():
        bid, gid = _branch_and_group(app)
        inv = svc.create_invite(label='T', role='teacher', permission_group_id=None,
                                branch_id=bid, scope='branch', max_uses=None, expires_days=None,
                                created_by='root')
        s, _ = svc.submit_signup(inv, full_name='Bad Actor', username='bad', email=None,
                                 phone=None, password='longenough', branch_id=None, position=None)
        assert svc.reject_signup(s, 'root') is True
        assert db.session.get(StaffSignup, s.id).status == 'rejected'
        assert User.query.filter_by(username='bad').first() is None


def test_join_page_public_and_submit(app):
    from models import StaffSignup
    from utils import staff_invite as svc
    with app.app_context():
        bid, gid = _branch_and_group(app)
        inv = svc.create_invite(label='P', role='admin', permission_group_id=gid,
                                branch_id=bid, scope='branch', max_uses=None, expires_days=None,
                                created_by='root')
        token = inv.token

    c = app.test_client()                                # NOT logged in — public
    r = c.get(f'/join/{token}')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Join' in html
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    r2 = c.post(f'/join/{token}', data={
        '_csrf_token': tok, 'full_name': 'Sam Okoro', 'username': 'sam',
        'password': 'secret12', 'position': 'Principal'}, follow_redirects=True)
    assert 'awaiting approval' in r2.get_data(as_text=True).lower() or 'submitted' in r2.get_data(as_text=True).lower()
    with app.app_context():
        assert StaffSignup.query.filter_by(username='sam', status='pending').first() is not None


def test_bad_token_shows_closed(app):
    c = app.test_client()
    r = c.get('/join/not-a-real-token')
    assert r.status_code == 200 and 'invalid' in r.get_data(as_text=True).lower()


def test_invites_page_requires_manage(app):
    c = app.test_client()                                # anonymous
    r = c.get('/staff-invites')
    assert r.status_code in (301, 302)                   # redirected to login


def test_invites_page_renders_for_admin(auth_client, app):
    with app.app_context():
        _branch_and_group(app)
    r = auth_client.get('/staff-invites')
    assert r.status_code == 200
    assert 'invite link' in r.get_data(as_text=True).lower()
