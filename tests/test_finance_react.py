"""Finance pages converted to the React shell (JSON-aware, no-reload)."""
import re

from config import Config
from models import db, FeeItem
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_finance_shells_render(app):
    client = _admin(app)
    pages = {
        '/finance/': 'dashboard',
        '/finance/items': 'items',
        '/finance/structure': 'structure',
        '/finance/payments': 'payments',
        '/finance/payments/record': 'record_payment',
        '/finance/expenses': 'expenses',
        '/finance/defaulters': 'defaulters',
        '/finance/collections': 'collections',
        '/finance/reports': 'reports',
    }
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'fin-app' in html and 'fin-data' in html, url
        assert f'"page": "{page}"' in html, url


def test_fee_item_json_create_and_delete(app):
    client = _admin(app)
    token = _ptoken(client)
    r = client.post('/finance/items/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'PTA Levy', 'description': 'Annual', '_csrf_token': token}).get_json()
    assert r['ok']
    with app.app_context():
        it = FeeItem.query.filter_by(name='PTA Levy').first()
        assert it is not None
        iid = it.id
    d = client.post(f'/finance/items/{iid}/delete', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': token}).get_json()
    assert d['ok']
    with app.app_context():
        assert FeeItem.query.get(iid) is None


def test_fee_item_requires_name(app):
    client = _admin(app)
    r = client.post('/finance/items/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': '  ', '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'required' in r.get_json()['error']
