"""Tests for fine-grained module permissions (roles & access control)."""
from config import Config
from models import db, User
from tests.conftest import login_token


def _make_user(app, username, role='teacher', modules=None):
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


def test_finance_only_user_blocked_from_hr(app):
    """A user granted only Finance cannot reach the HR module."""
    _make_user(app, 'bursar1', role='staff', modules=['finance'])
    client = _login(app, 'bursar1')

    # Finance is allowed.
    assert client.get('/finance/').status_code == 200

    # HR is gated -> redirect back to dashboard (mounted at '/').
    resp = client.get('/hr/', follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers.get('Location', '') in ('/', 'http://localhost/')


def test_finance_only_user_sidebar_hides_hr(app):
    """The sidebar should not render sections the user cannot access."""
    _make_user(app, 'bursar2', role='staff', modules=['finance'])
    client = _login(app, 'bursar2')
    html = client.get('/').get_data(as_text=True)
    assert 'Finance' in html
    # No HR / Library nav sections for this user.
    assert '>Staff / HR<' not in html
    assert '>Library<' not in html


def test_admin_sees_everything(app):
    """Legacy admin login bypasses all module gates."""
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                '_csrf_token': token})
    assert client.get('/hr/').status_code == 200
    assert client.get('/finance/').status_code == 200


def test_teacher_default_modules(app):
    """A teacher with no explicit modules gets the role default set."""
    _make_user(app, 'teach1', role='teacher', modules=None)
    client = _login(app, 'teach1')
    # CBT is in the teacher default set.
    assert client.get('/cbt/').status_code == 200
    # Finance is not -> redirect away.
    resp = client.get('/finance/', follow_redirects=False)
    assert resp.status_code in (302, 303)
