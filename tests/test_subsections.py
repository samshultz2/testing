"""Sub-section permissions (e.g. Finance: payments but not expenses)."""
import re
from models import db, User, Expense
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


def _ptoken(c):
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                  c.get('/').get_data(as_text=True))
    return m.group(1) if m else None


def test_granular_finance_access(app):
    _make(app, 'fpart', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'fpart')
    # granted sub-sections reachable
    assert c.get('/finance/payments').status_code == 200          # payments (edit)
    assert c.get('/finance/expenses').status_code == 200          # expenses (view)
    # ungranted sub-section blocked
    assert c.get('/finance/defaulters', follow_redirects=False).status_code in (302, 303)


def test_view_subsection_blocks_write(app):
    _make(app, 'fpart2', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'fpart2')
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add',
           data={'description': 'Tape', 'amount': 300, '_csrf_token': _ptoken(c)},
           follow_redirects=True)
    with app.app_context():
        assert Expense.query.count() == before        # expenses is view-only -> blocked


def test_subsection_level_helper(app):
    from flask import session
    from utils.access_control import subsection_level, module_level
    _make(app, 'fpart3', {'finance.payments': 'edit'})
    with app.app_context():
        uid = User.query.filter_by(username='fpart3').first().id
    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = uid
        session['role'] = 'staff'; session['scope'] = 'central'
        assert subsection_level('finance', 'payments') == 'edit'
        assert subsection_level('finance', 'expenses') is None   # not granted
        assert module_level('finance') == 'edit'                 # module visible
