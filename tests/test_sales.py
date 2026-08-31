"""Stage 5: Sales & Inventory."""
import re

from config import Config
from models import db, Product, Sale, Branch
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


def test_sales_pages_load(app):
    client = _admin(app)
    for url in ['/sales/', '/sales/products', '/sales/new', '/sales/history']:
        assert client.get(url).status_code == 200


def test_sales_pages_are_react_shells(app):
    client = _admin(app)
    pages = {'/sales/': 'dashboard', '/sales/products': 'products',
             '/sales/new': 'new_sale', '/sales/history': 'history'}
    for url, page in pages.items():
        html = client.get(url).get_data(as_text=True)
        assert 'sales-app' in html and 'sales-data' in html
        assert f'"page": "{page}"' in html


def test_add_product_json(app):
    client = _admin(app)
    r = client.post('/sales/products/add', headers={'X-Requested-With': 'fetch'},
                    data={'name': 'JSONPen', 'unit_price': '50', 'stock_qty': '4',
                          '_csrf_token': _ptoken(client)})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        assert Product.query.filter_by(name='JSONPen').first() is not None


def test_add_product_and_sell_decrements_stock(app):
    client = _admin(app)
    tok = _ptoken(client)
    client.post('/sales/products/add',
                data={'name': 'Uniform', 'category': 'Uniform', 'unit_price': 3000,
                      'stock_qty': 5, '_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        p = Product.query.filter_by(name='Uniform').first()
        assert p is not None and p.stock_qty == 5
        assert p.branch_id == Branch.get_default().id
        pid = p.id
    client.post('/sales/new',
                data={'product_id': pid, 'quantity': 2, 'payment_method': 'Cash',
                      '_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        assert Product.query.get(pid).stock_qty == 3       # 5 - 2
        sale = Sale.query.order_by(Sale.id.desc()).first()
        assert sale.total == 6000 and sale.items.count() == 1


def test_cannot_oversell(app):
    client = _admin(app)
    tok = _ptoken(client)
    client.post('/sales/products/add',
                data={'name': 'Ruler', 'category': 'Stationery', 'unit_price': 100,
                      'stock_qty': 1, '_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        pid = Product.query.filter_by(name='Ruler').first().id
    client.post('/sales/new',
                data={'product_id': pid, 'quantity': 5, '_csrf_token': tok},
                follow_redirects=True)
    with app.app_context():
        assert Product.query.get(pid).stock_qty == 1       # unchanged — refused
