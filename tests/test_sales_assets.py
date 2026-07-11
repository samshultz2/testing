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
