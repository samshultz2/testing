"""View-only pages expose data-readonly so the UI hides write controls."""
import re
from models import db, User
from tests.conftest import login_token


def _make(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='central', full_name=username)
            u.set_password('secret123'); u.set_permissions(perms)
            db.session.add(u); db.session.commit()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def test_view_only_page_marked_readonly(app):
    _make(app, 'ro_view', {'finance': 'view'})
    c = _login(app, 'ro_view')
    html = c.get('/finance/expenses').get_data(as_text=True)
    assert 'data-readonly="1"' in html


def test_edit_page_not_readonly(app):
    _make(app, 'ro_edit', {'finance': 'edit'})
    c = _login(app, 'ro_edit')
    html = c.get('/finance/expenses').get_data(as_text=True)
    assert 'data-readonly="1"' not in html


def test_subsection_readonly_per_page(app):
    # Granular user: edit Payments, view Expenses. Each page reflects its own level.
    _make(app, 'ro_sub', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'ro_sub')
    payments = c.get('/finance/payments').get_data(as_text=True)
    expenses = c.get('/finance/expenses').get_data(as_text=True)
    assert 'data-readonly="1"' not in payments     # payments is editable
    assert 'data-readonly="1"' in expenses         # expenses is view-only
