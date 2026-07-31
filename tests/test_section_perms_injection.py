"""Permission-aware UI: every React section payload carries a `perms` block so
the client can hide write actions a user may not perform.

These tests lock in the server half of that contract — the thing the React
`canWrite(d)` helper depends on. They exercise the real render chain
(`utils.spa.render_or_json`, which every section — including the ones with a
bespoke `_render` like library — funnels through) rather than the helper in
isolation, so a regression that drops the block is caught here.
"""
from config import Config
from models import db, User
from tests.conftest import login_token


def _make_user(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', full_name=username.title())
            u.set_password('secret123')
            u.set_permissions(perms)
            db.session.add(u)
            db.session.commit()


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _section_json(client, path):
    return client.get(path, headers={'X-Requested-With': 'fetch'}).get_json()


def test_viewer_gets_perms_block_with_write_false(app):
    _make_user(app, 'lib_viewer', {'library': 'view'})
    client = _login(app, 'lib_viewer')
    data = _section_json(client, '/library/')
    assert data is not None and 'perms' in data, 'section payload missing perms block'
    assert data['perms']['module'] == 'library'
    # `write` is what the client's canWrite() keys off: a 'view' grant means no
    # write. (`read_only` is the separate global view-only flag and stays False
    # for a user who simply lacks edit on this one module.)
    assert data['perms']['write'] is False
    assert data['perms']['level'] == 'view'


def test_editor_gets_perms_block_with_write_true(app):
    _make_user(app, 'lib_editor', {'library': 'edit'})
    client = _login(app, 'lib_editor')
    data = _section_json(client, '/library/')
    assert data is not None and 'perms' in data
    assert data['perms']['module'] == 'library'
    assert data['perms']['write'] is True


def test_admin_gets_write_true(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                '_csrf_token': token})
    data = _section_json(client, '/library/')
    assert data is not None and 'perms' in data
    assert data['perms']['write'] is True


def test_bespoke_render_sections_also_get_perms(app):
    """Sections whose blueprint defines its own `_render` (admissions, events,
    sales, promotion, library) still get the block because injection lives in
    the shared `render_or_json` choke point."""
    _make_user(app, 'multi_viewer',
               {'admissions': 'view', 'events': 'view', 'sales': 'view'})
    client = _login(app, 'multi_viewer')
    for path, module in (('/admissions/', 'admissions'),
                         ('/events/', 'events'),
                         ('/sales/', 'sales')):
        data = _section_json(client, path)
        assert data is not None and 'perms' in data, f'{path} missing perms'
        assert data['perms']['module'] == module, path
        assert data['perms']['write'] is False, path
