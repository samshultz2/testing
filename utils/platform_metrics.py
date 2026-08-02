"""Executive metrics for the platform command-center dashboard.

Everything here is derived from the control-plane registry and its history —
no invented snapshots. The heavy cross-tenant usage sweep (largest schools) is
cached and degrades to empty when tenant databases are unreachable, so the
dashboard never fails on a slow or missing tenant DB.

Kept deliberately cheap: a single pass over the (small) Tenant list plus the
already-cached monthly trend and platform-totals helpers.
"""
from __future__ import annotations

import datetime as _dt

from flask import current_app

from utils import tenancy, billing


def _price_naira():
    return (current_app.config.get('TENANT_PRICE_KOBO', 0) or 0) / 100.0


def _bucket(t, st):
    if st['owner']:
        return 'owner'
    if t.status == 'pending':
        return 'pending'
    if t.status == 'archived':
        return 'archived'
    if t.status == 'suspended':
        return 'suspended'
    if st['on_trial']:
        return 'trial'
    if st['active'] and t.status == 'active':
        return 'paying'
    return 'unpaid'


def executive_summary():
    """The full KPI set for the dashboard, as a single dict. Null-safe."""
    tenants = tenancy.list_tenants()
    now = _dt.datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - _dt.timedelta(days=today.weekday())
    month = today.replace(day=1)
    prev_month_end = month - _dt.timedelta(days=1)
    prev_month = prev_month_end.replace(day=1)
    price = _price_naira()

    counts = {k: 0 for k in ('owner', 'pending', 'suspended', 'archived', 'trial',
                             'paying', 'unpaid')}
    customers = ending_soon = new_today = new_week = new_month = new_prev = 0
    failing = 0            # subscribers with a stored auto-renew error
    card_on_file = 0

    for t in tenants:
        st = billing.status(t)
        b = _bucket(t, st)
        counts[b] = counts.get(b, 0) + 1
        if b == 'owner':
            continue
        customers += 1
        c = t.created_at
        if c:
            if c >= today:
                new_today += 1
            if c >= week:
                new_week += 1
            if c >= month:
                new_month += 1
            if prev_month <= c < month:
                new_prev += 1
        if st['active'] and st['days_left'] is not None and 0 <= st['days_left'] <= 3:
            ending_soon += 1
        if getattr(t, 'auto_renew_last_error', None):
            failing += 1
        if st['card_on_file']:
            card_on_file += 1

    paying = counts['paying']
    active = paying + counts['trial']
    mrr = paying * price

    # Month-over-month signup growth (real, from created_at).
    mom_pct = None
    if new_prev:
        mom_pct = round((new_month - new_prev) / new_prev * 100)

    # Retention signals from real history: churn events & credited payments.
    try:
        from utils import platform_analytics
        trend = platform_analytics.monthly_trends(12)
    except Exception:
        trend = {'labels': [], 'signups': [], 'payments': [], 'churn': [],
                 'cumulative': [], 'totals': {}}
    churn_month = (trend.get('churn') or [0])[-1] if trend.get('churn') else 0
    renewals_month = (trend.get('payments') or [0])[-1] if trend.get('payments') else 0
    # Renewal-health proxy: credited payments vs (payments + churn) this month.
    denom = renewals_month + churn_month
    renewal_rate = round(renewals_month / denom * 100) if denom else None
    churn_rate = round(churn_month / active * 100, 1) if active else None

    # Distribution bar (customers only), each segment mapped to a schools filter.
    dist = [
        ('paying', 'Paying', counts['paying'], 'paying'),
        ('trial', 'Trial', counts['trial'], 'trial'),
        ('unpaid', 'Unpaid', counts['unpaid'], 'unpaid'),
        ('suspended', 'Suspended', counts['suspended'], 'suspended'),
        ('archived', 'Archived', counts['archived'], 'archived'),
        ('pending', 'Pending', counts['pending'], ''),
    ]
    dist = [{'key': k, 'label': lb, 'count': n, 'filter': f,
             'pct': round(n / customers * 100) if customers else 0}
            for (k, lb, n, f) in dist if n]

    return {
        'portfolio': {
            'total': len(tenants),
            'customers': customers,
            'lifetime': customers,           # every customer ever provisioned
            'active': active,
            'paying': paying,
            'trial': counts['trial'],
            'unpaid': counts['unpaid'],
            'suspended': counts['suspended'],
            'archived': counts['archived'],
            'pending': counts['pending'],
            'ending_soon': ending_soon,
            'card_on_file': card_on_file,
        },
        'revenue': {
            'mrr': mrr, 'arr': mrr * 12,
            'arpa': price if paying else 0,
            'price': price,
            'failing': failing,
        },
        'growth': {
            'today': new_today, 'week': new_week, 'month': new_month,
            'prev_month': new_prev, 'mom_pct': mom_pct,
        },
        'retention': {
            'churn_month': churn_month, 'renewals_month': renewals_month,
            'renewal_rate': renewal_rate, 'churn_rate': churn_rate,
        },
        'distribution': dist,
        'trend': trend,
    }


def sparkline_points(series, width=100.0, height=30.0, pad=2.0):
    """Map a numeric series to an SVG polyline 'x,y ...' string (y inverted).
    Returns ('', '', None) when there's nothing to draw."""
    vals = [v for v in (series or []) if v is not None]
    if len(vals) < 2:
        return '', '', None
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + (width - 2 * pad) * (i / (n - 1))
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        pts.append(f'{x:.1f},{y:.1f}')
    return ' '.join(pts), pts[-1], vals[-1]
