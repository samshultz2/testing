"""Contributions module converted to the React shell (JSON-aware), behind its
own access-code gate."""
import re

from config import Config
from models import db, ContributionSettings, ContributionExpense
from tests.conftest import login_token

ACCESS_CODE = '64665842'


def _client(app):
    """Logged-in client that has also passed the contributions access gate."""
    c = app.test_client()
    token = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    c.post('/contributions/access', data={'access_code': ACCESS_CODE, '_csrf_token': token})
    return c


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_access_gate_blocks_then_grants(app):
    c = app.test_client()
    token = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    # Without the code, the settings page bounces to the access page.
    r = c.get('/contributions/settings', follow_redirects=False)
    assert r.status_code in (302, 303) and '/contributions/access' in r.headers['Location']
    # Wrong code stays out; right code lets the next request through.
    c.post('/contributions/access', data={'access_code': 'wrong', '_csrf_token': token})
    assert c.get('/contributions/settings', follow_redirects=False).status_code in (302, 303)
    c.post('/contributions/access', data={'access_code': ACCESS_CODE, '_csrf_token': token})
    assert c.get('/contributions/settings').status_code == 200


def test_contribution_shells_render(app):
    c = _client(app)
    for url, page in {
        '/contributions/settings': 'settings',
        '/contributions/payments': 'payments',
        '/contributions/expenses': 'expenses',
        '/contributions/history': 'history',
        '/contributions/daily-summary': 'daily_summary',
        '/contributions/import': 'import',
        '/contributions/expenses/add': 'add_expense',
    }.items():
        html = c.get(url).get_data(as_text=True)
        assert 'contrib-app' in html and 'contrib-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_settings_save_json(app):
    c = _client(app)
    r = c.post('/contributions/settings', headers={'X-Requested-With': 'fetch'},
               data={'max_due': '25000', 'start_date': '2025-02-01',
                     '_csrf_token': _ptoken(c)}).get_json()
    assert r['ok']
    with app.app_context():
        assert str(ContributionSettings.get('max_due', '0')) in ('25000.0', '25000')


def test_add_and_delete_expense_json(app):
    c = _client(app)
    r = c.post('/contributions/expenses/add', headers={'X-Requested-With': 'fetch'},
               data={'expense_date': '2025-03-01', 'description': 'Banner printing',
                     'amount': '4500', '_csrf_token': _ptoken(c)}).get_json()
    assert r['ok'] and r['redirect'].endswith('/contributions/expenses')
    with app.app_context():
        e = ContributionExpense.query.filter_by(description='Banner printing').first()
        assert e is not None
        eid = e.id
    d = c.post(f'/contributions/expenses/{eid}/delete', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': _ptoken(c)}).get_json()
    assert d['ok']
    with app.app_context():
        assert db.session.get(ContributionExpense, eid) is None
