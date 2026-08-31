"""Sales Phase 10 — discounts & promo codes at checkout."""
from datetime import date, timedelta
from config import Config
from models import db, Branch, Product, Sale, PromoCode
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _product(app, price=1000, stock=50):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name='ZzPromoItem', category='Textbooks',
                    unit_price=price, cost_price=400, stock_qty=stock, is_active=True)
        db.session.add(p); db.session.commit()
        return p.id


def _promo(app, **kw):
    with app.app_context():
        pc = PromoCode(branch_id=Branch.get_default().id, is_active=True, **kw)
        db.session.add(pc); db.session.commit()
        return pc.code


def _sell(c, pid, qty=1, **extra):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
                  data={'_csrf_token': 'a' * 64, 'product_id': pid, 'quantity': qty,
                        'payment_method': 'Cash', **extra})


def test_percent_promo_applied(app):
    c = _admin(app); _csrf(c)
    pid = _product(app)
    _promo(app, code='SAVE10', kind='percent', value=10)
    r = _sell(c, pid, 2, promo_code='SAVE10')       # subtotal 2000, 10% off = 200
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        sale = Sale.query.filter_by(discount_code='SAVE10').order_by(Sale.id.desc()).first()
        assert sale.subtotal == 2000 and sale.discount == 200 and sale.total == 1800
        pc = PromoCode.query.filter_by(code='SAVE10').first()
        assert pc.used_count == 1


def test_fixed_promo_and_manual_discount(app):
    c = _admin(app); _csrf(c)
    pid = _product(app)
    _promo(app, code='FLAT500', kind='fixed', value=500)
    r = _sell(c, pid, 1, promo_code='FLAT500', discount_amount='100')   # 1000 - 500 - 100
    assert r.get_json()['ok']
    with app.app_context():
        sale = Sale.query.filter_by(discount_code='FLAT500').order_by(Sale.id.desc()).first()
        assert sale.discount == 600 and sale.total == 400


def test_min_purchase_enforced(app):
    c = _admin(app); _csrf(c)
    pid = _product(app, price=300)
    _promo(app, code='BIG', kind='percent', value=10, min_purchase=1000)
    r = _sell(c, pid, 1, promo_code='BIG')          # subtotal 300 < 1000
    assert r.status_code == 400
    assert 'at least' in r.get_json()['error'].lower()


def test_expired_promo_rejected(app):
    c = _admin(app); _csrf(c)
    pid = _product(app)
    _promo(app, code='OLD', kind='percent', value=10, expires_on=date.today() - timedelta(days=1))
    r = _sell(c, pid, 1, promo_code='OLD')
    assert r.status_code == 400 and 'expired' in r.get_json()['error'].lower()


def test_unknown_code_rejected(app):
    c = _admin(app); _csrf(c)
    pid = _product(app)
    r = _sell(c, pid, 1, promo_code='NOPE')
    assert r.status_code == 400


def test_check_promo_endpoint(app):
    c = _admin(app); _csrf(c)
    _promo(app, code='CHK20', kind='percent', value=20)
    j = c.get('/sales/api/promo?code=CHK20&subtotal=5000').get_json()
    assert j['ok'] is True and j['discount'] == 1000
    j = c.get('/sales/api/promo?code=CHK20&subtotal=0').get_json()
    assert j['ok'] is True and j['discount'] == 0


def test_add_and_toggle_promo(app):
    c = _admin(app); tok = _csrf(c)
    r = c.post('/sales/promos/add', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': tok, 'code': 'zznew', 'kind': 'percent', 'value': 5})
    assert r.status_code == 200 and r.get_json()['ok']
    with app.app_context():
        pc = PromoCode.query.filter_by(code='ZZNEW').first()
        assert pc is not None and pc.value == 5
        pid = pc.id
    c.post(f'/sales/promos/{pid}/toggle', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(PromoCode, pid).is_active is False
