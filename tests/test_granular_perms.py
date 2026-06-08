"""Granular per-module view-vs-edit permissions."""
import re
from models import db, User, Expense
from tests.conftest import login_token


def _make(app, username, perms, scope='central'):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope=scope,
                     full_name=username, branch_id=None if scope == 'central' else 1)
            u.set_password('secret123')
            u.set_permissions(perms)
            db.session.add(u); db.session.commit()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _ptoken(c):
    # Read the CSRF meta from the dashboard (reachable by any logged-in user).
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                  c.get('/').get_data(as_text=True))
    return m.group(1) if m else None


def test_view_level_can_read_not_write(app):
    _make(app, 'finview', {'finance': 'view'})
    c = _login(app, 'finview')
    assert c.get('/finance/').status_code == 200          # can view finance
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add',
           data={'description': 'Chalk', 'amount': 500, '_csrf_token': _ptoken(c)},
           follow_redirects=True)
    with app.app_context():
        assert Expense.query.count() == before            # write blocked


def test_edit_level_can_write(app):
    _make(app, 'finedit', {'finance': 'edit'})
    c = _login(app, 'finedit')
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add',
           data={'description': 'Markers', 'amount': 800, '_csrf_token': _ptoken(c)},
           follow_redirects=True)
    with app.app_context():
        assert Expense.query.count() == before + 1        # write allowed


def test_permission_map_roundtrip(app):
    with app.app_context():
        u = User(username='permrt', role='staff'); u.set_password('x123456')
        u.set_permissions({'finance': 'view', 'students': 'edit', 'bogus': 'edit'})
        db.session.add(u); db.session.commit()
        u = User.query.filter_by(username='permrt').first()
        assert u.module_level('finance') == 'view'
        assert u.module_level('students') == 'edit'
        # legacy set_modules grants edit
        u.set_modules(['cbt'])
        assert u.module_level('cbt') == 'edit'
