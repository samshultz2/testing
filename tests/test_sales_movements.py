"""Sales Phase 5 — inventory movement ledger, adjustments and physical count."""
from config import Config
from models import db, Branch, Product, StockMovement
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _product(app, **kw):
    with app.app_context():
        bid = Branch.get_default().id
        p = Product(branch_id=bid, name=kw.pop('name', 'ZzMv'), category='Stationery',
                    unit_price=100, cost_price=60, stock_qty=kw.pop('stock', 20), is_active=True)
        db.session.add(p); db.session.commit()
        return p.id


def test_restock_records_in_movement(app):
    c = _admin(app); tok = _csrf(c)
    pid = _product(app, name='ZzMvRestock', stock=5)
    c.post(f'/sales/products/{pid}/restock', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok, 'qty': 10, 'reference': 'GRN-1'})
    with app.app_context():
        p = db.session.get(Product, pid)
        assert p.stock_qty == 15
        mv = StockMovement.query.filter_by(product_id=pid, direction='in').order_by(StockMovement.id.desc()).first()
        assert mv.quantity == 10 and mv.qty_after == 15 and mv.reference == 'GRN-1'


def test_adjust_out_records_and_guards(app):
    c = _admin(app); tok = _csrf(c)
    pid = _product(app, name='ZzMvOut', stock=8)
    # Cannot remove more than on hand.
    r = c.post(f'/sales/products/{pid}/adjust', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': tok, 'mode': 'move', 'direction': 'out',
                     'reason': 'Damage', 'quantity': 20})
    assert r.status_code == 400
    # A valid removal is applied and ledgered.
    r = c.post(f'/sales/products/{pid}/adjust', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': tok, 'mode': 'move', 'direction': 'out',
                     'reason': 'Damage', 'quantity': 3, 'note': 'broken'})
    assert r.status_code == 200
    with app.app_context():
        p = db.session.get(Product, pid)
        assert p.stock_qty == 5
        mv = StockMovement.query.filter_by(product_id=pid, reason='Damage').first()
        assert mv.direction == 'out' and mv.quantity == 3 and mv.note == 'broken'


def test_adjust_rejects_bad_reason(app):
    c = _admin(app); tok = _csrf(c)
    pid = _product(app, name='ZzMvBad', stock=8)
    r = c.post(f'/sales/products/{pid}/adjust', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': tok, 'mode': 'move', 'direction': 'out',
                     'reason': 'Sale', 'quantity': 1})   # 'Sale' isn't a manual reason
    assert r.status_code == 400


def test_physical_count_sets_and_logs_variance(app):
    c = _admin(app); tok = _csrf(c)
    pid = _product(app, name='ZzMvCount', stock=20)
    c.post(f'/sales/products/{pid}/adjust', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok, 'mode': 'count', 'counted': 17})
    with app.app_context():
        p = db.session.get(Product, pid)
        assert p.stock_qty == 17
        mv = StockMovement.query.filter_by(product_id=pid, reason='Physical Stock Count').first()
        assert mv.direction == 'out' and mv.quantity == 3 and mv.qty_after == 17


def test_sale_records_out_movement(app):
    c = _admin(app); tok = _csrf(c)
    pid = _product(app, name='ZzMvSale', stock=10)
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': 'a' * 64, 'product_id': pid, 'quantity': 2, 'payment_method': 'Cash'})
    with app.app_context():
        mv = StockMovement.query.filter_by(product_id=pid, reason='Sale').first()
        assert mv is not None and mv.direction == 'out' and mv.quantity == 2
        assert mv.sale_id is not None


def test_movements_ledger_filters(app):
    c = _admin(app); tok = _csrf(c)
    pid = _product(app, name='ZzMvLedger', stock=5)
    c.post(f'/sales/products/{pid}/restock', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok, 'qty': 4})
    j = c.get(f'/sales/movements?product_id={pid}&direction=in',
              headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['page'] == 'movements'
    assert j['summary']['total_in'] >= 4
    assert all(m['direction'] == 'in' for m in j['movements'])
    assert any(m['product'] == 'ZzMvLedger' for m in j['movements'])
