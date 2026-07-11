"""Sales Phase 3 — detailed, filterable sales history + export."""
import csv
import io
from config import Config
from models import db, Branch, Product, Sale, SaleItem
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, tag):
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name=f'ZzHi-{tag}', category='Stationery',
                    unit_price=200, cost_price=120, stock_qty=100, is_active=True)
        db.session.add(p); db.session.flush()
        s = Sale(branch_id=bid, payment_method='POS', total=400, amount_paid=300,
                 sold_by=f'Cashier-{tag}', customer_name=f'Walkin-{tag}',
                 receipt_no=f'HI{tag}')
        db.session.add(s); db.session.flush()
        db.session.add(SaleItem(sale_id=s.id, product_id=p.id, description=p.name,
                                quantity=2, unit_price=200, line_total=400))
        db.session.commit()
        return {'cashier': f'Cashier-{tag}', 'receipt': f'HI{tag}', 'product_id': p.id}


def test_history_detail_and_filter(app):
    ids = _seed(app, 'DETAIL')
    try:
        c = _admin(app)
        j = c.get(f'/sales/history?cashier={ids["cashier"]}',
                  headers={'X-Requested-With': 'fetch'}).get_json()
        assert j['page'] == 'history'
        assert 'options' in j and 'cashiers' in j['options']
        row = next(r for r in j['sales'] if r['receipt_no'] == ids['receipt'])
        assert row['item_count'] == 1
        assert row['items'][0]['quantity'] == 2
        assert row['balance'] == 100          # 400 total - 300 paid
        assert row['buyer_type'] == 'Staff / Walk-in'
        # The cashier filter narrows to just this sale.
        assert all(r['cashier'] == ids['cashier'] for r in j['sales'])
    finally:
        pass


def test_history_product_filter(app):
    ids = _seed(app, 'PROD')
    try:
        c = _admin(app)
        j = c.get(f'/sales/history?product_id={ids["product_id"]}',
                  headers={'X-Requested-With': 'fetch'}).get_json()
        receipts = {r['receipt_no'] for r in j['sales']}
        assert ids['receipt'] in receipts
        assert j['summary']['count'] == 1     # only the one sale of this product
    finally:
        pass


def test_history_export_csv(app):
    ids = _seed(app, 'CSV')
    c = _admin(app)
    r = c.get(f'/sales/history/export?format=csv&cashier={ids["cashier"]}')
    assert r.status_code == 200
    assert 'text/csv' in r.headers['Content-Type']
    assert 'attachment' in r.headers['Content-Disposition']
    reader = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    assert reader[0][0] == 'Receipt'
    assert any(row[0] == ids['receipt'] for row in reader[1:])


def test_history_export_excel(app):
    ids = _seed(app, 'XLS')
    c = _admin(app)
    r = c.get(f'/sales/history/export?format=excel&cashier={ids["cashier"]}')
    assert r.status_code == 200
    assert 'spreadsheet' in r.headers['Content-Type']
