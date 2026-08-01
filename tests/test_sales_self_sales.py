"""Self-scope Sales — a cashier sees only the sales THEY recorded (matched on
the seller name stamped at sale time), read-only, with no Sales-module access."""
from datetime import datetime
from flask import session
from models import db, User, Branch, Sale


def _cashier(app, username, full_name, perms):
    with app.app_context():
        bid = Branch.get_default().id
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=full_name, role='staff',
                     scope='branch', branch_id=bid)
            u.set_password('CorrectHorse9')
            db.session.add(u); db.session.flush()
        u.is_active = True
        u.set_permissions(perms)
        db.session.commit()
        return u.id, u.full_name


def _sale(app, sold_by, total):
    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(Sale(sold_by=sold_by, total=total, payment_method='Cash',
                            branch_id=bid, created_at=datetime.now()))
        db.session.commit()


def test_self_sales_registered(app):
    from utils.access_control import (CAPABILITY_SUBSECTIONS, SELF_SCOPE_SUBSECTIONS,
                                      MODULE_SUBSECTIONS)
    assert 'sales.self_sales' in CAPABILITY_SUBSECTIONS
    assert 'sales.self_sales' in SELF_SCOPE_SUBSECTIONS
    assert 'self_sales' in MODULE_SUBSECTIONS['sales']


def test_self_sales_shows_own_takings_not_module(app):
    uid, myname = _cashier(app, 'cash_me', 'Cashier Mine', {'sales.self_sales': 'view'})
    _cashier(app, 'cash_other', 'Cashier Other', {'sales.self_sales': 'view'})
    _sale(app, myname, 1500)
    _sale(app, myname, 2500)
    _sale(app, 'Cashier Other', 9999)
    with app.app_context():
        bid = Branch.get_default().id
    with app.test_request_context('/'):
        # Login stamps the user's branch into the session; replicate that so the
        # branch-scoped query sees this branch's sales.
        session.update(logged_in=True, user_id=uid, role='staff', scope='branch', branch_id=bid)
        from utils.access_control import can_access_module
        from utils.self_service import sales_self_sales
        assert can_access_module('sales') is False        # capability != module access
        d = sales_self_sales(db.session.get(User, uid))
        assert d is not None
        assert d['today_count'] == 2 and d['today_total'] == 4000
        totals = {r['total'] for r in d['recent']}
        assert 9999 not in totals                         # another cashier's sale never shows


def test_self_sales_none_without_capability(app):
    uid, _ = _cashier(app, 'cash_nocap', 'Cashier NoCap', {'students': 'view'})
    with app.test_request_context('/'):
        session.update(logged_in=True, user_id=uid, role='staff')
        from utils.self_service import sales_self_sales
        assert sales_self_sales(db.session.get(User, uid)) is None
