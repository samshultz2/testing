"""Privilege-escalation guard: a manager may not assign a role above their own
authority via the user add/edit forms.

Security invariant: a branch-scoped manager must not create a *central* actor.
Branch managers' new users are force-scoped to their branch by
_clamp_management_fields, so an 'admin' they create is a BRANCH admin (confined,
is_central=False) — that is the intended delegation model. The one role that
escapes the scope clamp is 'super_admin' (User.is_central is True for any
super_admin regardless of scope), so a branch manager POSTing role=super_admin
would mint a cross-branch central super-admin. That is the hole this guards.
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


def _user(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).first()


def _add_user(client, username, role):
    return client.post('/users/add', data={
        'username': username, 'password': _PW, 'confirm_password': _PW,
        'full_name': username, 'role': role, '_csrf_token': auth_csrf(client),
    }, follow_redirects=True)


def test_branch_manager_cannot_mint_super_admin(app):
    """A branch manager POSTing role=super_admin gets a clamped, NON-central
    role — the created account must never be central."""
    bid = _branch_id(app)
    _mk(app, 'esc_bmgr', role='staff', scope='branch', branch_id=bid,
        rank=60, manage_scope='branch')
    c = _login(app, 'esc_bmgr')

    _add_user(c, 'esc_pwn_super', 'super_admin')
    u = _user(app, 'esc_pwn_super')
    assert u.role != 'super_admin'
    assert u.is_central is False          # the actual security property


def test_branch_manager_admin_is_a_confined_branch_admin(app):
    """A branch manager MAY create an admin (intended delegation), but it must
    be a branch admin — scoped to the manager's branch, never central."""
    bid = _branch_id(app)
    _mk(app, 'esc_bmgr_a', role='staff', scope='branch', branch_id=bid,
        rank=60, manage_scope='branch')
    c = _login(app, 'esc_bmgr_a')

    _add_user(c, 'esc_branch_admin', 'admin')
    u = _user(app, 'esc_branch_admin')
    assert u.role == 'admin'              # role preserved…
    assert u.scope == 'branch'            # …but confined to the branch
    assert u.branch_id == bid
    assert u.is_central is False


def test_branch_manager_cannot_escalate_existing_user_to_super_admin(app):
    """Editing an existing branch user to super_admin is clamped."""
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
    u = _user(app, 'esc_victim')
    assert u.role != 'super_admin'
    assert u.is_central is False


def test_central_admin_can_create_branch_admins(app):
    """The described workflow: a central admin (role=admin, scope=central)
    creates admins for branches. This must keep working."""
    bid = _branch_id(app)
    _mk(app, 'esc_central', role='admin', scope='central',
        rank=100, manage_scope='central')
    c = _login(app, 'esc_central')

    _add_user(c, 'esc_workflow_admin', 'admin')
    assert _user(app, 'esc_workflow_admin').role == 'admin'


def test_central_manager_can_assign_super_admin(app):
    """A central manager retains the ability to grant super_admin — the clamp
    gates on central authority, it does not blanket-ban."""
    _mk(app, 'esc_central2', role='admin', scope='central',
        rank=100, manage_scope='central')
    c = _login(app, 'esc_central2')

    _add_user(c, 'esc_new_super', 'super_admin')
    assert _user(app, 'esc_new_super').role == 'super_admin'
