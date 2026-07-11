"""Sales Phase 12 — stock-audit sessions (physical count + variance sign-off)."""
from config import Config
from models import (db, Branch, Product, StockAudit, StockAuditItem,
                    StockMovement, FinanceTransaction)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _cat(tag):
    return f'ZzAudit{tag}'


def _products(app, tag, specs):
    """specs: list of (name, stock, cost). Returns {name: id} for a unique category."""
    ids = {}
    with app.app_context():
        for name, stock, cost in specs:
            p = Product(branch_id=Branch.get_default().id, name=f'{name}{tag}',
                        category=_cat(tag), unit_price=cost * 2, cost_price=cost,
                        stock_qty=stock, is_active=True)
            db.session.add(p); db.session.flush()
            ids[name] = p.id
        db.session.commit()
    return ids


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, headers={'X-Requested-With': 'fetch'}, data=data)


def _start(c, tag):
    r = _post(c, '/sales/audits/new', category=_cat(tag))
    assert r.status_code == 200 and r.get_json()['ok']
    return r.get_json()['redirect']


def _audit_id(app, tag):
    with app.app_context():
        a = StockAudit.query.filter_by(scope_category=_cat(tag)).order_by(StockAudit.id.desc()).first()
        return a.id


def test_start_snapshots_products(app):
    c = _admin(app)
    _products(app, 'SNAP', [('Pen', 20, 50), ('Book', 5, 100)])
    _start(c, 'SNAP')
    aid = _audit_id(app, 'SNAP')
    with app.app_context():
        a = db.session.get(StockAudit, aid)
        assert a.status == 'Counting' and a.reference.startswith('SA')
        items = a.items.all()
        assert len(items) == 2
        assert {i.system_qty for i in items} == {20, 5}
        assert all(i.counted_qty is None for i in items)


def test_save_counts_persists(app):
    c = _admin(app)
    _products(app, 'SAVE', [('Ruler', 10, 30)])
    _start(c, 'SAVE')
    aid = _audit_id(app, 'SAVE')
    with app.app_context():
        item = db.session.get(StockAudit, aid).items.first()
        iid = item.id
    r = _post(c, f'/sales/audits/{aid}/save',
              counts=__import__('json').dumps([{'item_id': iid, 'counted_qty': 8}]))
    assert r.get_json()['ok']
    with app.app_context():
        assert db.session.get(StockAuditItem, iid).counted_qty == 8


def test_complete_applies_shrinkage_to_stock_and_ledger(app):
    import json
    c = _admin(app)
    ids = _products(app, 'SHRK', [('WidgetA', 20, 100), ('WidgetB', 8, 50)])
    _start(c, 'SHRK')
    aid = _audit_id(app, 'SHRK')
    with app.app_context():
        items = {i.product_id: i.id for i in db.session.get(StockAudit, aid).items.all()}
    # A: counted 17 (−3 × 100 = −300). B: counted 8 (no change).
    counts = [{'item_id': items[ids['WidgetA']], 'counted_qty': 17},
              {'item_id': items[ids['WidgetB']], 'counted_qty': 8}]
    r = _post(c, f'/sales/audits/{aid}/complete', counts=json.dumps(counts))
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        a = db.session.get(StockAudit, aid)
        assert a.status == 'Completed' and a.approved_by
        assert a.variance_value == -300 and a.ledger_posted is True
        # stock corrected
        assert db.session.get(Product, ids['WidgetA']).stock_qty == 17
        assert db.session.get(Product, ids['WidgetB']).stock_qty == 8
        # a Physical Stock Count movement recorded for the varying product only
        mv = StockMovement.query.filter_by(product_id=ids['WidgetA'],
                                           reason='Physical Stock Count').first()
        assert mv is not None and mv.direction == 'out' and mv.quantity == 3
        assert StockMovement.query.filter_by(product_id=ids['WidgetB'],
                                             reason='Physical Stock Count').count() == 0
        # finance ledger: shrinkage expense
        tx = FinanceTransaction.query.filter_by(origin_type='stock_audit', origin_id=aid).first()
        assert tx is not None and tx.direction == 'out'
        assert tx.category == 'Inventory Shrinkage' and tx.amount == 300


def test_complete_overage_posts_gain(app):
    import json
    c = _admin(app)
    ids = _products(app, 'GAIN', [('Gadget', 5, 200)])
    _start(c, 'GAIN')
    aid = _audit_id(app, 'GAIN')
    with app.app_context():
        iid = db.session.get(StockAudit, aid).items.first().id
    r = _post(c, f'/sales/audits/{aid}/complete',
              counts=json.dumps([{'item_id': iid, 'counted_qty': 7}]))   # +2 × 200 = +400
    assert r.get_json()['ok']
    with app.app_context():
        assert db.session.get(Product, ids['Gadget']).stock_qty == 7
        tx = FinanceTransaction.query.filter_by(origin_type='stock_audit', origin_id=aid).first()
        assert tx.direction == 'in' and tx.category == 'Inventory Gain' and tx.amount == 400


def test_cancel_changes_nothing(app):
    c = _admin(app)
    ids = _products(app, 'CANC', [('Thing', 12, 10)])
    _start(c, 'CANC')
    aid = _audit_id(app, 'CANC')
    r = _post(c, f'/sales/audits/{aid}/cancel')
    assert r.get_json()['ok']
    with app.app_context():
        assert db.session.get(StockAudit, aid).status == 'Cancelled'
        assert db.session.get(Product, ids['Thing']).stock_qty == 12
        assert FinanceTransaction.query.filter_by(origin_type='stock_audit', origin_id=aid).count() == 0


def test_cannot_complete_twice(app):
    import json
    c = _admin(app)
    ids = _products(app, 'TWICE', [('Item', 10, 100)])
    _start(c, 'TWICE')
    aid = _audit_id(app, 'TWICE')
    with app.app_context():
        iid = db.session.get(StockAudit, aid).items.first().id
    _post(c, f'/sales/audits/{aid}/complete', counts=json.dumps([{'item_id': iid, 'counted_qty': 9}]))
    r2 = _post(c, f'/sales/audits/{aid}/complete', counts=json.dumps([{'item_id': iid, 'counted_qty': 3}]))
    assert r2.status_code == 400
    with app.app_context():
        # still reflects the first sign-off only
        assert db.session.get(Product, ids['Item']).stock_qty == 9
