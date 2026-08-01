"""URL-level write-form enforcement.

Beyond hiding buttons, a view-only user who *pastes the URL* of a create/edit
form (or is deep-linked to it) is redirected out on arrival — the GET is
blocked, not just the POST. Read pages for the same module stay reachable.
"""
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


def test_viewer_is_redirected_off_create_form(app):
    _make_user(app, 'lib_view', {'library': 'view'})
    client = _login(app, 'lib_view')
    # The list page (a read) is reachable...
    assert client.get('/library/').status_code == 200
    # ...but the "add book" form (a write form) bounces on GET.
    resp = client.get('/library/books/add', follow_redirects=False)
    assert resp.status_code in (302, 303), resp.status_code


def test_editor_reaches_create_form(app):
    _make_user(app, 'lib_edit', {'library': 'edit'})
    client = _login(app, 'lib_edit')
    assert client.get('/library/books/add').status_code == 200


def test_viewer_edit_form_also_blocked(app):
    """Academics session edit form: view-only bounced, editor allowed."""
    _make_user(app, 'acad_view', {'academics': 'view'})
    _make_user(app, 'acad_edit', {'academics': 'edit'})
    viewer = _login(app, 'acad_view')
    editor = _login(app, 'acad_edit')
    # Add-session form
    assert viewer.get('/academics/sessions/add', follow_redirects=False).status_code in (302, 303)
    assert editor.get('/academics/sessions/add').status_code == 200


def test_viewer_keeps_read_access_to_module(app):
    """A view grant still lets the user READ the module's list/dashboard."""
    _make_user(app, 'acad_view2', {'academics': 'view'})
    client = _login(app, 'acad_view2')
    assert client.get('/academics/sessions').status_code == 200


def test_fetch_request_gets_403_not_redirect(app):
    """React fetch() calls get a clean 403 (the client shows an error) rather
    than an HTML redirect it can't follow."""
    _make_user(app, 'lib_view_fetch', {'library': 'view'})
    client = _login(app, 'lib_view_fetch')
    resp = client.get('/library/books/add', headers={'X-Requested-With': 'fetch'})
    assert resp.status_code == 403
