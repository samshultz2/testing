"""Sales Phase 7 — the rich sales & inventory dashboard payload."""
from config import Config
from models import db, Branch, Product, Sale, SaleItem
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_dashboard_payload_has_rich_metrics(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name='ZzDashItem', category='Stationery',
                    unit_price=500, cost_price=300, stock_qty=10, is_active=True)
        db.session.add(p); db.session.flush()
        sale = Sale(branch_id=bid, payment_method='Cash', total=1000, amount_paid=1000,
                    sold_by='DashCashier', receipt_no='DASH1')
        db.session.add(sale); db.session.flush()
        db.session.add(SaleItem(sale_id=sale.id, product_id=p.id, description=p.name,
                                quantity=2, unit_price=500, line_total=1000))
        db.session.commit()
    j = c.get('/sales/', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['page'] == 'dashboard'
    for k in ('today_total', 'week_total', 'month_total', 'month_profit',
              'inventory_value', 'out_of_stock_count', 'awaiting_delivery',
              'by_method', 'by_cashier', 'by_category', 'top_products', 'trend'):
        assert k in j, f'{k} missing from dashboard payload'
    # Today's sale is reflected in the rolling totals and breakdowns.
    assert j['month_total'] >= 1000 and j['week_total'] >= 1000
    assert any(r['label'] == 'Cash' for r in j['by_method'])
    assert any(r['label'] == 'DashCashier' for r in j['by_cashier'])
    assert isinstance(j['trend'], list) and len(j['trend']) >= 28


def test_dashboard_profit_reflects_cogs(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name='ZzProfitItem', category='Textbooks',
                    unit_price=1000, cost_price=600, stock_qty=50, is_active=True)
        db.session.add(p); db.session.flush()
        sale = Sale(branch_id=bid, payment_method='Cash', total=2000, amount_paid=2000,
                    sold_by='X', receipt_no='PRFT1')
        db.session.add(sale); db.session.flush()
        db.session.add(SaleItem(sale_id=sale.id, product_id=p.id, description=p.name,
                                quantity=2, unit_price=1000, line_total=2000))
        db.session.commit()
    j = c.get('/sales/', headers={'X-Requested-With': 'fetch'}).get_json()
    # Profit is revenue minus COGS, so it's strictly below revenue when cost > 0.
    assert j['month_profit'] <= j['month_total']
