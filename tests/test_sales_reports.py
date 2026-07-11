"""Sales Phase 8 — the reports suite + export."""
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
        sold = Product(branch_id=bid, name=f'ZzRpSold-{tag}', category='Textbooks',
                       unit_price=1000, cost_price=600, stock_qty=10, reorder_level=2, is_active=True)
        dead = Product(branch_id=bid, name=f'ZzRpDead-{tag}', category='Stationery',
                       unit_price=200, cost_price=100, stock_qty=8, reorder_level=1, is_active=True)
        low = Product(branch_id=bid, name=f'ZzRpLow-{tag}', category='Stationery',
                      unit_price=50, cost_price=30, stock_qty=0, reorder_level=5, is_active=True)
        db.session.add_all([sold, dead, low]); db.session.flush()
        sale = Sale(branch_id=bid, payment_method='Cash', total=2000, amount_paid=2000,
                    sold_by='X', receipt_no=f'RP{tag}')
        db.session.add(sale); db.session.flush()
        db.session.add(SaleItem(sale_id=sale.id, product_id=sold.id, description=sold.name,
                                quantity=2, unit_price=1000, line_total=2000))
        db.session.commit()
        return {'sold': sold.name, 'dead': dead.name, 'low': low.name}


def test_inventory_valuation_report(app):
    names = _seed(app, 'VAL')
    c = _admin(app)
    j = c.get('/sales/reports?kind=inventory_valuation', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['page'] == 'reports' and j['report']['title'] == 'Inventory Valuation'
    assert j['report']['totals']['stock_value'] > 0
    assert any(r['name'] == names['sold'] for r in j['report']['rows'])


def test_low_stock_report_flags_out(app):
    names = _seed(app, 'LOW')
    c = _admin(app)
    j = c.get('/sales/reports?kind=low_stock', headers={'X-Requested-With': 'fetch'}).get_json()
    row = next(r for r in j['report']['rows'] if r['name'] == names['low'])
    assert row['status'] == 'Out'


def test_dead_stock_excludes_sold(app):
    names = _seed(app, 'DEAD')
    c = _admin(app)
    j = c.get('/sales/reports?kind=dead_stock', headers={'X-Requested-With': 'fetch'}).get_json()
    rownames = {r['name'] for r in j['report']['rows']}
    assert names['dead'] in rownames          # never sold, has stock
    assert names['sold'] not in rownames      # sold in range → not dead


def test_profit_report(app):
    _seed(app, 'PRFT')
    c = _admin(app)
    j = c.get('/sales/reports?kind=profit', headers={'X-Requested-With': 'fetch'}).get_json()
    t = j['report']['totals']
    assert t['profit'] == round(t['revenue'] - t['cogs'], 2)


def test_report_export_csv(app):
    names = _seed(app, 'EXP')
    c = _admin(app)
    r = c.get('/sales/reports/export?kind=inventory_valuation&format=csv')
    assert r.status_code == 200 and 'text/csv' in r.headers['Content-Type']
    reader = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    assert reader[0][0] == 'Product'
    assert any(names['sold'] in row for row in reader[1:])


def test_report_export_excel(app):
    _seed(app, 'XLS')
    c = _admin(app)
    r = c.get('/sales/reports/export?kind=suppliers&format=excel')
    assert r.status_code == 200 and 'spreadsheet' in r.headers['Content-Type']
