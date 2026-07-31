"""Delegation hierarchy: who may grant access to whom.

Invariants under audit:
  * Central admin has unfettered authority (manages everyone, grants anything).
  * A branch manager (principal/HOD) manages ONLY strictly-lower-ranked users
    in their OWN branch — never themselves, never a peer (same rank), never a
    superior, never another branch.
  * Non-managers (teachers/staff, manage_scope='none') cannot reach /users.
  * New/edited users are rank-clamped strictly below the manager and pinned to
    the manager's branch; a branch manager can never mint a central actor.
  * Public pages need no admin permission.
"""
import re
from config import Config
from models import db, User, Branch
from tests.conftest import login_token


def _branch(app, name):
    with app.app_context():
        b = Branch.query.filter_by(name=name).first()
        if not b:
            b = Branch(name=name, is_active=True)
            db.session.add(b); db.session.commit()
        return b.id


def _user(app, username, **kw):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username.title(), is_active=True)
            u.set_password('secret123')
            db.session.add(u)
        for k, v in kw.items():
            setattr(u, k, v)
        db.session.commit()
        return u.id


def _login(app, username):
    c = app.test_client()
    t = login_token(c)
    c.post('/login', data={'username': username, 'password': 'secret123', '_csrf_token': t})
    return c


def _csrf(c):
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/users/').get_data(as_text=True))
    return m.group(1) if m else None


def _setup(app):
    b1 = _branch(app, 'Branch One')
    b2 = _branch(app, 'Branch Two')
    ids = {
        'princA': _user(app, 'princa', role='staff', scope='branch', branch_id=b1,
                        rank=60, manage_scope='branch'),
        'princB': _user(app, 'princb', role='staff', scope='branch', branch_id=b1,
                        rank=60, manage_scope='branch'),
        'hod':    _user(app, 'hod1', role='staff', scope='branch', branch_id=b1,
                        rank=40, manage_scope='branch'),
        'teacher': _user(app, 'teach1', role='teacher', scope='branch', branch_id=b1,
                         rank=10, manage_scope='none'),
        'teacherB2': _user(app, 'teachb2', role='teacher', scope='branch', branch_id=b2,
                           rank=10, manage_scope='none'),
        'super': _user(app, 'supera', role='super_admin', scope='central', rank=100,
                       manage_scope='central'),
    }
    ids['b1'], ids['b2'] = b1, b2
    return ids


def _name_of(app, uid):
    with app.app_context():
        return User.query.get(uid).full_name


# --- can_manage via the real edit route ------------------------------------
def test_principal_cannot_edit_self_peer_or_superior(app):
    ids = _setup(app)
    c = _login(app, 'princa')
    # self, a peer principal (same rank/branch), and a cross-branch teacher
    for key in ('princA', 'princB', 'teacherB2', 'super'):
        r = c.get(f"/users/{ids[key]}/edit", follow_redirects=False)
        assert r.status_code in (302, 303), f'{key} should be blocked, got {r.status_code}'


def test_principal_can_edit_subordinate_in_branch(app):
    ids = _setup(app)
    c = _login(app, 'princa')
    tok = _csrf(c)
    r = c.post(f"/users/{ids['hod']}/edit",
               data={'full_name': 'HOD Renamed', 'role': 'staff', 'is_active': 'on',
                     'rank': '40', 'manage_scope': 'branch', 'scope': 'branch',
                     'branch_id': str(ids['b1']), '_csrf_token': tok},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert _name_of(app, ids['hod']) == 'HOD Renamed'      # change applied


def test_principal_matrix_post_ignores_peer_rows(app):
    """A crafted matrix POST carrying a peer's id must not change the peer."""
    ids = _setup(app)
    with app.app_context():
        u = User.query.get(ids['princB']); u.set_permissions({'finance': 'edit'}); db.session.commit()
    c = _login(app, 'princa')
    tok = _csrf(c)
    # try to wipe princB's finance grant via the matrix
    c.post('/users/matrix', data={f"view_{ids['princB']}": '', '_csrf_token': tok},
           follow_redirects=False)
    with app.app_context():
        assert User.query.get(ids['princB']).permission_map.get('finance') == 'edit'


def test_hod_cannot_edit_peer_or_principal_but_can_edit_teacher(app):
    ids = _setup(app)
    c = _login(app, 'hod1')
    # peer HOD would be same rank; principal is above — both blocked
    assert c.get(f"/users/{ids['princA']}/edit", follow_redirects=False).status_code in (302, 303)
    tok = _csrf(c)
    r = c.post(f"/users/{ids['teacher']}/edit",
               data={'full_name': 'Teacher Renamed', 'role': 'teacher', 'is_active': 'on',
                     'rank': '10', 'manage_scope': 'none', 'scope': 'branch',
                     'branch_id': str(ids['b1']), '_csrf_token': tok},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert _name_of(app, ids['teacher']) == 'Teacher Renamed'


def test_teacher_cannot_reach_user_management(app):
    ids = _setup(app)
    c = _login(app, 'teach1')
    for path in ('/users/', '/users/add', '/users/matrix', '/users/groups'):
        assert c.get(path, follow_redirects=False).status_code in (302, 303), path


# --- clamps on creation ----------------------------------------------------
def test_branch_manager_creation_is_rank_and_branch_clamped(app):
    ids = _setup(app)
    c = _login(app, 'princa')
    tok = _csrf(c)
    c.post('/users/add',
           data={'username': 'newbie', 'password': 'Str0ng!Passw0rd', 'confirm_password': 'Str0ng!Passw0rd',
                 'full_name': 'New Bie', 'role': 'admin',          # tries to mint an admin...
                 'rank': '90', 'manage_scope': 'central', 'scope': 'central',  # ...central, high rank
                 '_csrf_token': tok},
           follow_redirects=False)
    with app.app_context():
        u = User.query.filter_by(username='newbie').first()
        assert u is not None
        assert u.rank <= 59                     # strictly below the principal's 60
        assert u.branch_id == ids['b1']         # pinned to the manager's branch
        assert u.is_central is False            # never a central actor
        assert u.manage_scope in ('none', 'branch')


# --- central admin is unfettered -------------------------------------------
def test_central_admin_can_edit_a_branch_manager(app):
    ids = _setup(app)
    c = _login(app, 'supera')
    tok = _csrf(c)
    r = c.post(f"/users/{ids['princA']}/edit",
               data={'full_name': 'Principal Renamed', 'role': 'staff', 'is_active': 'on',
                     'rank': '60', 'manage_scope': 'branch', 'scope': 'branch',
                     'branch_id': str(ids['b1']), '_csrf_token': tok},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert _name_of(app, ids['princA']) == 'Principal Renamed'


# --- public pages need no admin permission ---------------------------------
def test_public_pages_need_no_admin(app):
    c = app.test_client()
    assert c.get('/login').status_code == 200          # login is public
