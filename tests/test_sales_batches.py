"""Sales Phase 17 — batch/lot tracking with FEFO drawdown."""
import datetime as dt
from config import Config
from models import db, Branch, Product, StockBatch, Sale
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, headers={'X-Requested-With': 'fetch'}, data=data)


def _product(app, tag, *, tracked=True, stock=0):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name=f'ZzBatch{tag}', category='Other',
                    unit_price=200, cost_price=80, stock_qty=stock, is_active=True,
                    batch_tracked=tracked)
        db.session.add(p); db.session.commit()
        return p.id


def _batches(app, pid):
    with app.app_context():
        return sorted(StockBatch.query.filter_by(product_id=pid).all(),
                      key=lambda b: b.id)


def test_restock_opens_a_batch(app):
    c = _admin(app)
    pid = _product(app, 'IN')
    r = _post(c, f'/sales/products/{pid}/restock', qty=20, batch_no='LOT-A', expiry_date='2027-01-31')
    assert r.status_code == 200 and r.get_json()['ok']
    bs = _batches(app, pid)
    assert len(bs) == 1
    with app.app_context():
        b = db.session.get(StockBatch, bs[0].id)
        assert b.quantity == 20 and b.original_qty == 20 and b.batch_no == 'LOT-A'
        assert b.expiry_date == dt.date(2027, 1, 31)
        assert db.session.get(Product, pid).stock_qty == 20


def test_non_tracked_product_creates_no_batch(app):
    c = _admin(app)
    pid = _product(app, 'NOTRACK', tracked=False)
    _post(c, f'/sales/products/{pid}/restock', qty=10)
    with app.app_context():
        assert StockBatch.query.filter_by(product_id=pid).count() == 0
        assert db.session.get(Product, pid).stock_qty == 10


def test_sale_consumes_fefo(app):
    c = _admin(app)
    pid = _product(app, 'FEFO')
    # Two lots: LATER expiry received first, SOONER expiry received second.
    _post(c, f'/sales/products/{pid}/restock', qty=5, batch_no='LATE', expiry_date='2028-12-31')
    _post(c, f'/sales/products/{pid}/restock', qty=5, batch_no='SOON', expiry_date='2026-09-30')
    # Sell 6 — should empty the SOON lot (5) then take 1 from LATE.
    r = c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64, 'product_id': pid, 'quantity': 6, 'payment_method': 'Cash'})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        soon = StockBatch.query.filter_by(product_id=pid, batch_no='SOON').first()
        late = StockBatch.query.filter_by(product_id=pid, batch_no='LATE').first()
        assert soon.quantity == 0            # earliest expiry drained first
        assert late.quantity == 4            # remainder taken from the later lot
        assert db.session.get(Product, pid).stock_qty == 4


def test_batches_view_hides_empty_by_default(app):
    c = _admin(app)
    pid = _product(app, 'VIEW')
    _post(c, f'/sales/products/{pid}/restock', qty=3, batch_no='V1', expiry_date='2027-05-01')
    # drain it
    c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': 'a' * 64, 'product_id': pid, 'quantity': 3, 'payment_method': 'Cash'})
    body = c.get('/sales/batches?product_id=%d' % pid).get_data(as_text=True)
    assert 'V1' not in body                   # emptied lot hidden
    body2 = c.get('/sales/batches?product_id=%d&empty=1' % pid).get_data(as_text=True)
    assert 'V1' in body2                       # shown when asked


def test_batch_serial_capture(app):
    c = _admin(app)
    pid = _product(app, 'SER')
    _post(c, f'/sales/products/{pid}/restock', qty=1, batch_no='UNIT', serial_number='SN-12345')
    with app.app_context():
        b = StockBatch.query.filter_by(product_id=pid).first()
        assert b.serial_number == 'SN-12345' and b.quantity == 1
