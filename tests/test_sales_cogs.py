"""Sales Phase 11 — cost of goods sold posted to the finance ledger."""
from config import Config
from models import db, Branch, Product, Sale, FinanceTransaction
from tests.conftest import login_token
from utils import finance_ledger as fl


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _product(app, unit=1000, cost=400, stock=50):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name='ZzCogsItem', category='Textbooks',
                    unit_price=unit, cost_price=cost, stock_qty=stock, is_active=True)
        db.session.add(p); db.session.commit()
        return p.id


def _sell(c, pid, qty=1, **extra):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
                  data={'_csrf_token': 'a' * 64, 'product_id': pid, 'quantity': qty,
                        'payment_method': 'Cash', **extra})


def _ledger(app, sale_id, origin_type):
    with app.app_context():
        return FinanceTransaction.query.filter_by(
            origin_type=origin_type, origin_id=sale_id).first()


def test_sale_posts_revenue_and_cogs(app):
    c = _admin(app)
    pid = _product(app, unit=1000, cost=400)
    r = _sell(c, pid, 3)                       # revenue 3000, cogs 3×400 = 1200
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        sale = Sale.query.order_by(Sale.id.desc()).first()
        sid = sale.id
    rev = _ledger(app, sid, 'sale')
    cogs = _ledger(app, sid, 'sale_cogs')
    assert rev is not None and rev.direction == fl.REVENUE and rev.amount == 3000
    assert cogs is not None and cogs.direction == fl.EXPENSE
    assert cogs.amount == 1200 and cogs.category == fl.COGS_CATEGORY
    assert cogs.source_module == 'cogs'


def test_cogs_uses_discounted_none_but_full_cost(app):
    # A discount lowers revenue but never the cost of goods.
    c = _admin(app)
    pid = _product(app, unit=1000, cost=400)
    r = _sell(c, pid, 2, discount_amount='500')   # revenue 1500, cogs 800
    assert r.get_json()['ok']
    with app.app_context():
        sid = Sale.query.order_by(Sale.id.desc()).first().id
    assert _ledger(app, sid, 'sale').amount == 1500
    assert _ledger(app, sid, 'sale_cogs').amount == 800


def test_zero_cost_product_posts_no_cogs(app):
    c = _admin(app)
    pid = _product(app, unit=1000, cost=0)
    r = _sell(c, pid, 1)
    assert r.get_json()['ok']
    with app.app_context():
        sid = Sale.query.order_by(Sale.id.desc()).first().id
    assert _ledger(app, sid, 'sale') is not None
    assert _ledger(app, sid, 'sale_cogs') is None    # no cost → no COGS row


def test_cogs_reversed_on_sale_delete(app):
    c = _admin(app)
    pid = _product(app, unit=1000, cost=400)
    _sell(c, pid, 2)
    with app.app_context():
        sale = Sale.query.order_by(Sale.id.desc()).first()
        sid = sale.id
        db.session.delete(sale)
        db.session.commit()
        # both the revenue and the COGS originals are marked reversed
        assert FinanceTransaction.query.filter_by(
            origin_type='sale_cogs', origin_id=sid).first().reversed is True
        # an offsetting reversal (a REVENUE entry cancelling the COGS expense) exists
        revs = FinanceTransaction.query.filter_by(
            origin_type='reversal', reference=f'SL{sid:05d}').all()
        assert any(t.direction == fl.REVENUE and t.category == fl.COGS_CATEGORY for t in revs)


def test_cogs_backfill_idempotent(app):
    c = _admin(app)
    pid = _product(app, unit=1000, cost=250)
    _sell(c, pid, 4)                            # cogs 1000, already ledgered by the route
    with app.app_context():
        sid = Sale.query.order_by(Sale.id.desc()).first().id
        # Draining any un-ledgered sales once, a second backfill must add nothing
        # (every sale/COGS is now present — the unique origin key makes it a no-op).
        fl.backfill()
        assert fl.backfill() == 0
        # and the route-sold sale still has exactly one COGS row.
        assert FinanceTransaction.query.filter_by(
            origin_type='sale_cogs', origin_id=sid).count() == 1
