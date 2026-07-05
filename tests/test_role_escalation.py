"""Privilege-escalation guard: a manager may not assign a role above their own
authority via the user add/edit forms.

Without the _safe_role() clamp in routes/users.py, a mere branch manager
(manage_scope='branch', NOT is_admin) could POST role=super_admin to
/users/add and mint a central super-admin — since User.is_central is True for
any super_admin regardless of scope, and is_admin bypasses every module gate.
"""
from models import db, Branch, User
from tests.conftest import login_token, auth_csrf

_PW = 'Str0ng!Pass99'   # satisfies is_password_strong


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _mk(app, username, **kw):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username, **kw)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
        return u.id


def _branch_id(app):
    with app.app_context():
        b = Branch.query.filter_by(name='EscB').first()
        if not b:
            b = Branch(name='EscB', is_active=True)
            db.session.add(b); db.session.commit()
        return b.id


def _role_of(app, username):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        return u.role if u else None


def _add_user(client, username, role):
    return client.post('/users/add', data={
        'username': username, 'password': _PW, 'confirm_password': _PW,
        'full_name': username, 'role': role, '_csrf_token': auth_csrf(client),
    }, follow_redirects=True)


def test_branch_manager_cannot_mint_super_admin(app):
    """A branch manager POSTing role=super_admin gets a clamped (safe) role."""
    bid = _branch_id(app)
    _mk(app, 'esc_bmgr', role='staff', scope='branch', branch_id=bid,
        rank=60, manage_scope='branch')
    c = _login(app, 'esc_bmgr')

    _add_user(c, 'esc_pwn_super', 'super_admin')
    assert _role_of(app, 'esc_pwn_super') == 'teacher'   # clamped, not super_admin

    _add_user(c, 'esc_pwn_admin', 'admin')
    assert _role_of(app, 'esc_pwn_admin') == 'teacher'   # clamped, not admin


def test_branch_manager_cannot_escalate_existing_user(app):
    """Editing an existing teacher to super_admin is also clamped."""
    bid = _branch_id(app)
    _mk(app, 'esc_bmgr2', role='staff', scope='branch', branch_id=bid,
        rank=60, manage_scope='branch')
    target = _mk(app, 'esc_victim', role='staff', scope='branch',
                 branch_id=bid, rank=10, manage_scope='none')
    c = _login(app, 'esc_bmgr2')

    c.post(f'/users/{target}/edit', data={
        'full_name': 'esc_victim', 'role': 'super_admin', 'is_active': 'on',
        '_csrf_token': auth_csrf(c),
    }, follow_redirects=True)
    assert _role_of(app, 'esc_victim') == 'staff'        # unchanged, not escalated


def test_branch_manager_can_still_assign_normal_roles(app):
    """The clamp must not block legitimate non-privileged role assignment."""
    bid = _branch_id(app)
    _mk(app, 'esc_bmgr3', role='staff', scope='branch', branch_id=bid,
        rank=60, manage_scope='branch')
    c = _login(app, 'esc_bmgr3')

    _add_user(c, 'esc_new_teacher', 'teacher')
    assert _role_of(app, 'esc_new_teacher') == 'teacher'
    _add_user(c, 'esc_new_readonly', 'readonly')
    assert _role_of(app, 'esc_new_readonly') == 'readonly'


def test_central_super_admin_can_assign_super_admin(app):
    """A genuine central super-admin retains the ability to grant privileged
    roles — the clamp gates on authority, it does not blanket-ban."""
    _mk(app, 'esc_root', role='super_admin', scope='central',
        rank=100, manage_scope='central')
    c = _login(app, 'esc_root')

    _add_user(c, 'esc_new_admin', 'admin')
    assert _role_of(app, 'esc_new_admin') == 'admin'
    _add_user(c, 'esc_new_super', 'super_admin')
    assert _role_of(app, 'esc_new_super') == 'super_admin'
