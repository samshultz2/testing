"""Sales Phase 4 — richer products, categories and tiered pricing at sale."""
from config import Config
from models import db, Branch, Product, Sale
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def test_add_product_rich_fields(app):
    c = _admin(app); tok = _csrf(c)
    r = c.post('/sales/products/add', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': tok, 'name': 'ZzRichPen', 'category': 'Stationery',
                     'sku': 'PEN-1', 'barcode': '5012345', 'brand': 'BIC',
                     'unit_price': '150', 'cost_price': '90', 'student_price': '120',
                     'staff_price': '130', 'stock_qty': '40', 'reorder_level': '5',
                     'unit': 'Piece', 'taxable': 'on', 'vat_rate': '7.5',
                     'storage_location': 'Shelf A'})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        p = Product.query.filter_by(name='ZzRichPen').first()
        assert p.barcode == '5012345' and p.brand == 'BIC'
        assert p.student_price == 120 and p.staff_price == 130
        assert p.unit == 'Piece' and p.taxable is True and p.vat_rate == 7.5
        assert p.opening_stock == 40           # defaulted from opening stock
        assert p.storage_location == 'Shelf A'


def test_edit_partial_keeps_other_fields(app):
    c = _admin(app); tok = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name='ZzEditProd', category='Stationery',
                    unit_price=200, cost_price=100, student_price=150, stock_qty=10, is_active=True)
        db.session.add(p); db.session.commit()
        pid = p.id
    # Partial edit: only change the selling price.
    c.post(f'/sales/products/{pid}/edit', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok, 'unit_price': '250'})
    with app.app_context():
        p = db.session.get(Product, pid)
        assert p.unit_price == 250
        assert p.student_price == 150          # untouched


def test_tiered_pricing_applied_at_sale(app):
    c = _admin(app); tok = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name='ZzTierBook', category='Textbooks',
                    unit_price=1000, cost_price=600, student_price=800, staff_price=900,
                    stock_qty=50, is_active=True)
        db.session.add(p); db.session.commit()
        pid = p.id

    def _sell(data):
        with c.session_transaction() as s:
            s['_csrf_token'] = 'a' * 64
        return c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
                      data={'_csrf_token': 'a' * 64, 'product_id': pid, 'quantity': 1,
                            'payment_method': 'Cash', **data})

    # Walk-in with staff price → 900.
    assert _sell({'customer_type': 'Staff'}).get_json()['ok']
    # Plain walk-in → standard 1000.
    assert _sell({'customer_type': 'Walk-in'}).get_json()['ok']
    with app.app_context():
        sales = Sale.query.filter(Sale.total.in_([900, 1000])).order_by(Sale.id.desc()).limit(2).all()
        totals = {s.total for s in sales}
        assert 900 in totals and 1000 in totals
        staff_sale = next(s for s in sales if s.total == 900)
        assert staff_sale.customer_type == 'Staff'


def test_categories_expanded(app):
    c = _admin(app)
    j = c.get('/sales/products', headers={'X-Requested-With': 'fetch'}).get_json()
    assert 'Uniforms' in j['categories'] and 'ICT Equipment' in j['categories']
    assert 'units' in j


def test_products_table_bootstrap(app):
    from sqlalchemy import inspect
    with app.app_context():
        cols = {c['name'] for c in inspect(db.engine).get_columns('sales_products')}
        for col in ('barcode', 'brand', 'student_price', 'staff_price', 'parent_price',
                    'unit', 'taxable', 'vat_rate', 'expiry_date', 'storage_location'):
            assert col in cols, f'{col} missing'
        assert 'customer_type' in {c['name'] for c in inspect(db.engine).get_columns('sales')}
