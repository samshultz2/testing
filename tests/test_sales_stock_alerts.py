"""Sales Phase 15 — automated low-stock / expiry bell alerts."""
import datetime as dt
from models import db, Branch, Product, User, Notification
from utils import stock_notify, automations


def _product(app, tag, *, stock, reorder=0, expiry=None):
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name=f'ZzAlert{tag}',
                    category='Other', unit_price=100, cost_price=40,
                    stock_qty=stock, reorder_level=reorder, expiry_date=expiry,
                    is_active=True)
        db.session.add(p); db.session.commit()
        return p.id


def _count(app, title_prefix, *, user_id=None, role=None):
    with app.app_context():
        q = Notification.query.filter(Notification.title.like(title_prefix + '%'))
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        if role is not None:
            q = q.filter_by(role=role)
        return q.count()


def test_reorder_predicate():
    class P:
        def __init__(s, q, r): s.stock_qty, s.reorder_level = q, r
    rows = [P(0, 0), P(5, 10), P(20, 10), P(3, 0)]
    flagged = stock_notify._needs_reorder(rows)
    assert P(0, 0).stock_qty == 0
    # out-of-stock (0<=0) and at/below a real threshold (5<=10) flagged;
    # healthy (20>10) and threshold-less-but-in-stock (level 0, qty 3) are not.
    assert len(flagged) == 2


def test_low_stock_alert_fans_out_to_admins(app):
    _product(app, 'LOW', stock=1, reorder=5)          # below reorder
    before = _count(app, 'Stock: items need restocking', role='admin')
    with app.app_context():
        out = stock_notify.run_stock_alerts(app, force=True)
    assert out.get('low', 0) >= 1
    assert _count(app, 'Stock: items need restocking', role='admin') == before + 1


def test_expiry_alert_fires(app):
    soon = dt.date.today() + dt.timedelta(days=10)
    _product(app, 'EXP', stock=5, expiry=soon)
    before = _count(app, 'Stock: items expiring soon', role='admin')
    with app.app_context():
        out = stock_notify.run_stock_alerts(app, force=True)
    assert out.get('expiring', 0) >= 1
    assert _count(app, 'Stock: items expiring soon', role='admin') == before + 1


def test_sales_user_gets_personal_ping(app):
    with app.app_context():
        if not User.query.filter_by(username='storealert').first():
            u = User(username='storealert', role='staff', scope='central', full_name='Store')
            u.set_password('secret123'); u.set_permissions({'sales.inventory': 'edit'})
            db.session.add(u); db.session.commit()
        uid = User.query.filter_by(username='storealert').first().id
    _product(app, 'PING', stock=0, reorder=3)
    before = _count(app, 'Stock: items need restocking', user_id=uid)
    with app.app_context():
        stock_notify.run_stock_alerts(app, force=True)
    assert _count(app, 'Stock: items need restocking', user_id=uid) == before + 1


def test_dry_run_creates_nothing(app):
    _product(app, 'DRY', stock=0, reorder=2)
    before = _count(app, 'Stock: items need restocking', role='admin')
    with app.app_context():
        out = stock_notify.run_stock_alerts(app, force=True, dry_run=True)
    assert out.get('low', 0) >= 1                      # counted…
    assert _count(app, 'Stock: items need restocking', role='admin') == before   # …but not sent


def test_disabled_no_alert(app):
    _product(app, 'OFF', stock=0, reorder=2)
    with app.app_context():
        automations.set_enabled('stock_low', False)
        automations.set_enabled('stock_expiry', False)
        before = _count(app, 'Stock: items need restocking', role='admin')
        out = stock_notify.run_stock_alerts(app)       # not forced; disabled
    assert 'low' not in out and 'expiring' not in out
    assert _count(app, 'Stock: items need restocking', role='admin') == before


def test_automation_registry_has_stock_keys():
    assert 'stock_low' in automations.KEYS and 'stock_expiry' in automations.KEYS
    keys = {s['key'] for s in automations.all_states()}
    assert {'stock_low', 'stock_expiry'} <= keys
