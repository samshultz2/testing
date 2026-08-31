"""A manager may never delegate access larger than their own.

A branch manager can only grant modules/sub-sections they themselves hold (at a
level no higher than theirs), and may only assign permission-group bundles that
fit inside their own authority. Central admins remain unfettered. Superior-
granted permissions a lower manager lacks are preserved on edit, never stripped.
"""
import re
from config import Config
from models import db, User, Branch, PermissionGroup
from tests.conftest import login_token


def _branch(app, name):
    with app.app_context():
        b = Branch.query.filter_by(name=name).first()
        if not b:
            b = Branch(name=name, is_active=True); db.session.add(b); db.session.commit()
        return b.id


def _user(app, username, **kw):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username.title(), is_active=True)
            u.set_password('secret123'); db.session.add(u)
        perms = kw.pop('perms', None)
        for k, v in kw.items():
            setattr(u, k, v)
        if perms is not None:
            u.set_permissions(perms)
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


def _principal(app):
    """A branch principal who holds ONLY students + results (no hr/finance)."""
    b1 = _branch(app, 'Clamp Branch')
    pid = _user(app, 'clamp_princ', role='staff', scope='branch', branch_id=b1,
                rank=60, manage_scope='branch',
                perms={'students': 'edit', 'results': 'edit'})
    return pid, b1


def test_branch_manager_cannot_grant_module_they_lack(app):
    _, b1 = _principal(app)
    c = _login(app, 'clamp_princ')
    tok = _csrf(c)
    c.post('/users/add', data={
        'username': 'clamped_sub', 'password': 'Str0ng!Passw0rd',
        'confirm_password': 'Str0ng!Passw0rd', 'full_name': 'Sub', 'role': 'staff',
        'scope': 'branch', 'branch_id': str(b1), 'rank': '10',
        'perm_students': 'edit',       # principal HAS this -> granted
        'perm_hr': 'edit',             # principal LACKS this -> dropped
        'perm_finance': 'edit',        # principal LACKS this -> dropped
        '_csrf_token': tok,
    }, follow_redirects=False)
    with app.app_context():
        u = User.query.filter_by(username='clamped_sub').first()
        assert u is not None
        pm = u.permission_map
        assert pm.get('students') == 'edit'      # allowed
        assert 'hr' not in pm                     # blocked
        assert 'finance' not in pm                # blocked


def test_edit_preserves_superior_granted_module(app):
    """A principal editing a user cannot strip a module a superior granted them
    but the principal doesn't hold."""
    _, b1 = _principal(app)
    sub = _user(app, 'has_finance', role='staff', scope='branch', branch_id=b1,
                rank=10, manage_scope='none', perms={'students': 'edit', 'finance': 'edit'})
    c = _login(app, 'clamp_princ')
    tok = _csrf(c)
    # principal tries to revoke finance (perm_finance=none) — must not take effect
    c.post(f'/users/{sub}/edit', data={
        'full_name': 'Has Finance', 'role': 'staff', 'is_active': 'on',
        'scope': 'branch', 'branch_id': str(b1), 'rank': '10', 'manage_scope': 'none',
        'perm_students': 'edit', 'perm_finance': 'none',
        '_csrf_token': tok,
    }, follow_redirects=False)
    with app.app_context():
        assert User.query.get(sub).permission_map.get('finance') == 'edit'   # preserved


def test_oversized_group_not_assignable_by_branch_manager(app):
    _, b1 = _principal(app)
    with app.app_context():
        g = PermissionGroup(name='Big Bundle', branch_id=None, is_active=True)
        g.set_permissions({'finance': 'edit', 'hr': 'edit'})   # beyond principal
        db.session.add(g); db.session.commit()
        gid = g.id
    c = _login(app, 'clamp_princ')
    tok = _csrf(c)
    c.post('/users/add', data={
        'username': 'grp_sub', 'password': 'Str0ng!Passw0rd',
        'confirm_password': 'Str0ng!Passw0rd', 'full_name': 'Grp Sub', 'role': 'staff',
        'scope': 'branch', 'branch_id': str(b1), 'rank': '10',
        'permission_group_id': str(gid), '_csrf_token': tok,
    }, follow_redirects=False)
    with app.app_context():
        u = User.query.filter_by(username='grp_sub').first()
        assert u is not None
        assert u.permission_group_id is None            # oversized group refused
        assert 'finance' not in u.permission_map


def test_central_admin_can_grant_anything(app):
    b1 = _branch(app, 'Clamp Branch')
    c = app.test_client()
    t = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': t})
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                    c.get('/users/').get_data(as_text=True)).group(1)
    c.post('/users/add', data={
        'username': 'central_sub', 'password': 'Str0ng!Passw0rd',
        'confirm_password': 'Str0ng!Passw0rd', 'full_name': 'Central Sub', 'role': 'staff',
        'scope': 'branch', 'branch_id': str(b1), 'rank': '10',
        'perm_hr': 'edit', 'perm_finance': 'edit', '_csrf_token': tok,
    }, follow_redirects=False)
    with app.app_context():
        u = User.query.filter_by(username='central_sub').first()
        assert u.permission_map.get('hr') == 'edit'      # central: unfettered
        assert u.permission_map.get('finance') == 'edit'
