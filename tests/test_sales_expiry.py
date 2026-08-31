"""Sales Phase 9 — expiry tracking report + alerts."""
from datetime import date, timedelta
from config import Config
from models import db, Branch, Product
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, tag):
    with app.app_context():
        bid = Branch.get_default().id
        today = date.today()
        soon = Product(branch_id=bid, name=f'ZzExpSoon-{tag}', category='Medical Supplies',
                       unit_price=100, cost_price=50, stock_qty=10, is_active=True,
                       expiry_date=today + timedelta(days=10))
        gone = Product(branch_id=bid, name=f'ZzExpGone-{tag}', category='Medical Supplies',
                       unit_price=100, cost_price=50, stock_qty=5, is_active=True,
                       expiry_date=today - timedelta(days=3))
        far = Product(branch_id=bid, name=f'ZzExpFar-{tag}', category='Medical Supplies',
                      unit_price=100, cost_price=50, stock_qty=5, is_active=True,
                      expiry_date=today + timedelta(days=200))
        db.session.add_all([soon, gone, far]); db.session.commit()
        return {'soon': soon.name, 'gone': gone.name, 'far': far.name}


def test_expiry_report_lists_near_and_expired(app):
    names = _seed(app, 'RPT')
    c = _admin(app)
    j = c.get('/sales/reports?kind=expiry', headers={'X-Requested-With': 'fetch'}).get_json()
    rows = {r['name']: r for r in j['report']['rows']}
    assert names['soon'] in rows and rows[names['soon']]['status'] == '≤30 days'
    assert names['gone'] in rows and rows[names['gone']]['status'] == 'Expired'
    assert names['far'] not in rows          # >90 days out is not surfaced


def test_dashboard_expiring_soon_count(app):
    _seed(app, 'DASH')
    c = _admin(app)
    j = c.get('/sales/', headers={'X-Requested-With': 'fetch'}).get_json()
    # The 10-day and the already-expired product both count; the 200-day one doesn't.
    assert j['expiring_soon'] >= 2


def test_main_dashboard_insight_flags_expiry(app):
    _seed(app, 'INS')
    c = _admin(app)
    j = c.get('/api/dashboard/data').get_json()
    keys = {it['key'] for it in j['insights']}
    assert 'expiring' in keys
