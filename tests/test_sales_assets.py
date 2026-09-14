"""Sales Phase 16 — fixed-asset register + conversion from inventory."""
import datetime as dt
from config import Config
from models import db, Branch, Product, FixedAsset, StockMovement, FinanceTransaction
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


def _product(app, tag, stock=10, cost=5000):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name=f'ZzAsset{tag}', category='ICT Equipment',
                    unit_price=cost * 2, cost_price=cost, stock_qty=stock, is_active=True,
                    storage_location='Lab 1')
        db.session.add(p); db.session.commit()
        return p.id


# --- depreciation model -----------------------------------------------------
def test_straight_line_book_value(app):
    with app.app_context():
        a = FixedAsset(branch_id=Branch.get_default().id, name='ZzDepr', acquisition_cost=10000,
                       salvage_value=1000, useful_life_years=3,
                       acquisition_date=dt.date.today() - dt.timedelta(days=365))
        db.session.add(a); db.session.flush()
        # (10000-1000)/3 = 3000/yr; ~1 year old → ~3000 accumulated, ~7000 book
        assert a.annual_depreciation == 3000
        assert 2900 <= a.accumulated_depreciation <= 3100
        assert 6900 <= a.book_value <= 7100


def test_book_value_never_below_salvage(app):
    with app.app_context():
        a = FixedAsset(branch_id=Branch.get_default().id, name='ZzOld', acquisition_cost=10000,
                       salvage_value=1000, useful_life_years=2,
                       acquisition_date=dt.date.today() - dt.timedelta(days=365 * 10))
        db.session.add(a); db.session.flush()
        assert a.accumulated_depreciation == 9000        # capped at cost − salvage
        assert a.book_value == 1000


# --- register CRUD ----------------------------------------------------------
def test_register_asset(app):
    c = _admin(app)
    r = _post(c, '/sales/assets/add', name='ZzProjector', category='ICT Equipment',
              acquisition_cost=45000, useful_life_years=5, asset_tag='ICT-9001')
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        a = FixedAsset.query.filter_by(asset_tag='ICT-9001').first()
        assert a is not None and a.acquisition_cost == 45000 and a.status == 'In Use'


# --- conversion from inventory ----------------------------------------------
def test_convert_product_to_asset_draws_stock(app):
    c = _admin(app)
    pid = _product(app, 'CONV', stock=5, cost=8000)
    r = _post(c, f'/sales/products/{pid}/convert-asset', quantity=2, name='ZzLabPC',
              category='ICT Equipment', useful_life_years=4)
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        p = db.session.get(Product, pid)
        assert p.stock_qty == 3                          # 5 − 2 drawn out
        a = FixedAsset.query.filter_by(name='ZzLabPC').order_by(FixedAsset.id.desc()).first()
        assert a is not None and a.quantity == 2 and a.source_product_id == pid
        assert a.acquisition_cost == 16000               # default cost 8000 × 2
        assert a.location == 'Lab 1'                     # carried from the product
        mv = StockMovement.query.filter_by(product_id=pid, reason='Converted to Fixed Asset').first()
        assert mv is not None and mv.direction == 'out' and mv.quantity == 2


def test_convert_rejects_over_stock(app):
    c = _admin(app)
    pid = _product(app, 'OVER', stock=1)
    r = _post(c, f'/sales/products/{pid}/convert-asset', quantity=5)
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(Product, pid).stock_qty == 1


# --- disposal + finance -----------------------------------------------------
def test_dispose_posts_proceeds_to_ledger(app):
    c = _admin(app)
    r = _post(c, '/sales/assets/add', name='ZzOldVan', category='Vehicles', acquisition_cost=500000)
    with app.app_context():
        aid = FixedAsset.query.filter_by(name='ZzOldVan').order_by(FixedAsset.id.desc()).first().id
    r = _post(c, f'/sales/assets/{aid}/dispose', disposal_amount=120000, method='Transfer',
              disposal_note='Sold to staff')
    assert r.get_json()['ok']
    with app.app_context():
        a = db.session.get(FixedAsset, aid)
        assert a.status == 'Disposed' and a.disposal_amount == 120000 and a.book_value == 0
        tx = FinanceTransaction.query.filter_by(origin_type='asset_disposal', origin_id=aid).first()
        assert tx is not None and tx.direction == 'in'
        assert tx.category == 'Asset Disposal' and tx.amount == 120000


def test_dispose_without_proceeds_no_ledger(app):
    c = _admin(app)
    _post(c, '/sales/assets/add', name='ZzScrap', category='Other', acquisition_cost=1000)
    with app.app_context():
        aid = FixedAsset.query.filter_by(name='ZzScrap').order_by(FixedAsset.id.desc()).first().id
    _post(c, f'/sales/assets/{aid}/dispose', disposal_amount=0)
    with app.app_context():
        assert db.session.get(FixedAsset, aid).status == 'Disposed'
        assert FinanceTransaction.query.filter_by(origin_type='asset_disposal', origin_id=aid).count() == 0


def test_assets_page_and_export(app):
    c = _admin(app)
    _post(c, '/sales/assets/add', name='ZzExportAsset', acquisition_cost=2000)
    assert c.get('/sales/assets').status_code == 200
    r = c.get('/sales/assets/export')
    assert r.status_code == 200 and ('spreadsheet' in r.content_type or 'officedocument' in r.content_type)


def test_add_asset_defaults_quantity_to_one_when_omitted(app):
    """A registration with no quantity/status-breakdown field posted (the
    normal case when the form's default of 1 is left alone) must not create
    a permanently stuck quantity-0 asset that can never be disposed."""
    c = _admin(app)
    _post(c, '/sales/assets/add', name='ZzDefaultQty', category='Other', acquisition_cost=100)
    with app.app_context():
        a = FixedAsset.query.filter_by(name='ZzDefaultQty').order_by(FixedAsset.id.desc()).first()
        assert a.quantity == 1 and a.status == 'In Use'
        assert a.status_breakdown == [{'status': 'In Use', 'quantity': 1}]


def test_add_asset_rejects_explicit_zero_quantity(app):
    c = _admin(app)
    r = _post(c, '/sales/assets/add', name='ZzZeroQty', category='Other',
             acquisition_cost=100, quantity=0)
    assert not r.get_json()['ok']
    with app.app_context():
        assert FixedAsset.query.filter_by(name='ZzZeroQty').first() is None


def test_create_audit_populates_expected_items(app):
    """Regression test: /sales/assets/audits/create used to always 500
    (filter_by(is_disposed=..., is_active=...) against columns that don't
    exist on FixedAsset)."""
    from models import AssetAudit, AssetAuditItem
    c = _admin(app)
    _post(c, '/sales/assets/add', name='ZzAuditableAsset', category='Furniture',
         acquisition_cost=5000, quantity=3)
    r = _post(c, '/sales/assets/audits/create', name='ZzAudit1')
    assert r.get_json()['ok']
    with app.app_context():
        audit = AssetAudit.query.filter_by(name='ZzAudit1').first()
        assert audit is not None and audit.status == 'Draft'
        item = AssetAuditItem.query.filter_by(audit_id=audit.id).join(
            FixedAsset, AssetAuditItem.asset_id == FixedAsset.id
        ).filter(FixedAsset.name == 'ZzAuditableAsset').first()
        assert item is not None and item.state == 'Pending' and item.quantity_expected == 3


# --- bulk actions ------------------------------------------------------------

def _add(c, name, **kw):
    kw.setdefault('category', 'Other')
    kw.setdefault('acquisition_cost', 1000)
    _post(c, '/sales/assets/add', name=name, **kw)
    with c.application.app_context():
        return FixedAsset.query.filter_by(name=name).order_by(FixedAsset.id.desc()).first().id


def test_bulk_transfer_moves_batch_assets_and_skips_units(app):
    c = _admin(app)
    id1 = _add(c, 'ZzBulkT1')
    id2 = _add(c, 'ZzBulkT2')
    id3 = _add(c, 'ZzBulkT3', is_individually_tracked='on')   # individually tracked
    r = c.post('/sales/assets/bulk/transfer', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64, 'location': 'New Store',
                     'asset_ids': [str(id1), str(id2), str(id3)]})
    body = r.get_json()
    assert body['ok']
    assert '2 asset(s) transferred' in body['message']
    assert '1 individually-tracked' in body['message']
    with app.app_context():
        assert db.session.get(FixedAsset, id1).location == 'New Store'
        assert db.session.get(FixedAsset, id2).location == 'New Store'
        assert db.session.get(FixedAsset, id3).location != 'New Store'


def test_bulk_dispose_retires_selected_and_posts_ledger(app):
    c = _admin(app)
    id1 = _add(c, 'ZzBulkD1', acquisition_cost=5000)
    id2 = _add(c, 'ZzBulkD2', acquisition_cost=5000)
    r = c.post('/sales/assets/bulk/dispose', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64, 'disposal_amount': '1000',
                     'asset_ids': [str(id1), str(id2)]})
    assert r.get_json()['ok']
    with app.app_context():
        assert db.session.get(FixedAsset, id1).status == 'Disposed'
        assert db.session.get(FixedAsset, id2).status == 'Disposed'
        txs = FinanceTransaction.query.filter(
            FinanceTransaction.origin_type == 'asset_disposal',
            FinanceTransaction.origin_id.in_([id1, id2])).all()
        assert len(txs) == 2 and all(t.amount == 1000 for t in txs)


def test_bulk_delete_removes_selected(app):
    c = _admin(app)
    id1 = _add(c, 'ZzBulkDel1')
    id2 = _add(c, 'ZzBulkDel2')
    r = c.post('/sales/assets/bulk/delete', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': 'a' * 64, 'asset_ids': [str(id1), str(id2)]})
    assert r.get_json()['ok']
    with app.app_context():
        assert db.session.get(FixedAsset, id1) is None
        assert db.session.get(FixedAsset, id2) is None


def test_bulk_actions_require_selection(app):
    c = _admin(app)
    for url in ('/sales/assets/bulk/transfer', '/sales/assets/bulk/assign',
               '/sales/assets/bulk/dispose', '/sales/assets/bulk/delete'):
        r = _post(c, url, location='X', custodian='Y')
        assert not r.get_json()['ok']


def test_assets_page_survives_teacher_with_no_full_name(app):
    """Regression: /sales/assets populates its "Teacher" placement dropdown
    via _teacher_options(), which used to sort teachers by
    `t.user.full_name` directly — a plain nullable column. One teacher whose
    user record had no full_name set crashed the sort (None vs str) and took
    down the entire page, not just that dropdown."""
    from models import User, Teacher
    with app.app_context():
        # Need at least one OTHER, normally-named teacher too — Python's
        # sorted() never invokes the comparator (so never crashes) on a
        # single-element list, so the bug only reproduces with >= 2 teachers
        # where the sort must compare a None name against a real one.
        if not User.query.filter_by(username='zznamedteacher').first():
            u2 = User(username='zznamedteacher', full_name='Zz Named Teacher', role='teacher',
                     password_hash='x', is_active=True)
            db.session.add(u2); db.session.flush()
            db.session.add(Teacher(user_id=u2.id, employee_id='ZZNAMED', is_active=True))
        if not User.query.filter_by(username='zzblankname').first():
            u = User(username='zzblankname', full_name=None, role='teacher',
                     password_hash='x', is_active=True)
            db.session.add(u); db.session.flush()
            db.session.add(Teacher(user_id=u.id, employee_id='ZZBLANK', is_active=True))
        db.session.commit()
    c = _admin(app)
    assert c.get('/sales/assets').status_code == 200
