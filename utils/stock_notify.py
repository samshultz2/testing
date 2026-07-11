"""Automated stock alerts — low/out-of-stock and expiring/expired products.

Driven daily by the scheduled worker (see app._tick_one). Gated by the
Communication automation center (``stock_low`` / ``stock_expiry``), so schools
opt in. Alerts go to the header bell of every admin *and* every user with Sales
& Inventory access (so the storekeeper who owns the shelf actually gets pinged,
not just admins). Everything is best-effort and never raises into the worker.
"""
from __future__ import annotations

import datetime as _dt

EXPIRY_SOON_DAYS = 30


def _needs_reorder(products):
    """Products at/below their reorder level (a real threshold > 0) or fully out
    of stock — i.e. the ones a storekeeper should act on."""
    out = []
    for p in products:
        qty = p.stock_qty or 0
        level = p.reorder_level or 0
        if qty <= 0 or (level > 0 and qty <= level):
            out.append(p)
    return out


def _expiring(products, today):
    horizon = today + _dt.timedelta(days=EXPIRY_SOON_DAYS)
    return [p for p in products
            if p.expiry_date and (p.stock_qty or 0) > 0 and p.expiry_date <= horizon]


def _sales_user_ids():
    """Ids of active users with any Sales & Inventory grant (module or a
    sub-section). Admins are reached via the role broadcast, so skip them here."""
    from models import User
    ids = []
    try:
        for u in User.query.filter_by(is_active=True).all():
            if getattr(u, 'is_super_admin', False):
                continue
            if any(k == 'sales' or k.startswith('sales.') for k in u.permission_map):
                ids.append(u.id)
    except Exception:
        pass
    return ids


def _fan_out(title, body, url, category):
    """Alert admins (role broadcast) and each sales-capable user individually."""
    from utils.notify import notify, notify_admins
    notify_admins(title, body, url=url, category=category)
    for uid in _sales_user_ids():
        notify(title, body, url=url, user_id=uid, category=category)


def run_stock_alerts(app, *, force=False, dry_run=False):
    """Scan the catalogue and raise low-stock / expiry bell alerts. Runs inside a
    central-scope request context so the scan (and audience resolution) spans
    every branch. Returns a small summary dict."""
    from utils import automations
    with app.test_request_context('/'):
        from flask import session, url_for
        session['scope'] = 'central'
        session['role'] = 'super_admin'
        from models import Product
        from utils.branch_scope import scope_query
        today = _dt.date.today()
        out = {}

        products = scope_query(Product.query.filter_by(is_active=True), Product).all()

        if force or automations.is_enabled('stock_low'):
            low = _needs_reorder(products)
            out['low'] = len(low)
            if low and not dry_run:
                oos = sum(1 for p in low if (p.stock_qty or 0) <= 0)
                extra = f' ({oos} out of stock)' if oos else ''
                _fan_out('Stock: items need restocking',
                         f'{len(low)} product(s) are at or below their reorder level{extra}.',
                         url_for('sales.products') + '?stock=low', 'warning')

        if force or automations.is_enabled('stock_expiry'):
            exp = _expiring(products, today)
            out['expiring'] = len(exp)
            if exp and not dry_run:
                expired = sum(1 for p in exp if p.expiry_date and p.expiry_date < today)
                extra = f' ({expired} already expired)' if expired else ''
                _fan_out('Stock: items expiring soon',
                         f'{len(exp)} product(s) expire within {EXPIRY_SOON_DAYS} days{extra}.',
                         url_for('sales.reports') + '?kind=expiry', 'warning')
        return out
