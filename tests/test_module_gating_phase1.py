"""Phase 1 of the permissions overhaul: previously-ungated staff surfaces are
now permission-checked like the rest of the app.

Modules newly gated:
  - contributions            -> module 'contributions'
  - mock_waec (Mock WAEC)    -> module 'external_exams' (like Mock JAMB)
  - settings (school config) -> module 'settings' (blanket gate relaxed to
                                honour the grant; sensitive routes stay
                                central-admin only)
  - website_admin (builder)  -> module 'website'

These tests lock in: (a) the catalog registration, (b) a staff member WITHOUT
the module is blocked by URL, (c) a staff member GRANTED the module gets in,
(d) the most sensitive settings routes remain central-admin only, (e) admins
are unaffected.
"""
from config import Config
from models import db, User
from utils.access_control import MODULES, BLUEPRINT_MODULE
from tests.conftest import login_token


def _make_user(app, username, role='staff', modules=None):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role=role, full_name=username.title())
            u.set_password('secret123')
            if modules is not None:
                u.set_modules(modules)
            db.session.add(u)
            db.session.commit()


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                '_csrf_token': token})
    return client


def test_catalog_registers_new_modules():
    for key in ('contributions', 'website', 'settings'):
        assert key in MODULES, key
    assert BLUEPRINT_MODULE['contributions'] == 'contributions'
    assert BLUEPRINT_MODULE['mock_waec'] == 'external_exams'
    assert BLUEPRINT_MODULE['settings'] == 'settings'
    assert BLUEPRINT_MODULE['website_admin'] == 'website'


def test_staff_without_module_is_blocked(app):
    _make_user(app, 'plain_staff', role='staff', modules=['finance'])
    client = _login(app, 'plain_staff')
    # Each of these lives under a module this user was NOT granted -> redirect.
    for path in ('/contributions/access', '/website/', '/mock-waec/', '/settings/'):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), f'{path} -> {resp.status_code}'


def test_granted_settings_module_reaches_settings(app):
    _make_user(app, 'cfg_staff', role='staff', modules=['settings'])
    client = _login(app, 'cfg_staff')
    assert client.get('/settings/').status_code == 200
    # ...but the sensitive user-management surface stays central-admin only.
    assert client.get('/settings/users', follow_redirects=False).status_code in (302, 303)


def test_granted_website_module_reaches_builder(app):
    _make_user(app, 'web_staff', role='staff', modules=['website'])
    client = _login(app, 'web_staff')
    assert client.get('/website/').status_code == 200


def test_granted_external_exams_reaches_mock_waec(app):
    _make_user(app, 'exam_staff', role='staff', modules=['external_exams'])
    client = _login(app, 'exam_staff')
    assert client.get('/mock-waec/', follow_redirects=False).status_code == 200


def test_granted_contributions_passes_module_gate(app):
    """The contributions access-code page is reachable once the module is
    granted (a non-granted staff member is bounced by the module gate first)."""
    _make_user(app, 'contrib_staff', role='staff', modules=['contributions'])
    client = _login(app, 'contrib_staff')
    assert client.get('/contributions/access').status_code == 200


def test_admin_reaches_everything(app):
    client = _admin(app)
    assert client.get('/settings/').status_code == 200
    assert client.get('/website/').status_code == 200
    assert client.get('/mock-waec/', follow_redirects=False).status_code == 200
    assert client.get('/contributions/access').status_code == 200
