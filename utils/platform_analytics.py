"""Platform growth & subscription trends, computed from control-plane history.

Real data only — no snapshots invented:
  * signups per month   ← Tenant.created_at
  * payments per month  ← ProcessedPayment.at (grants/renewals credited)
  * churn per month     ← PlatformAudit suspend/delete actions
  * cumulative schools  ← running total of signups

Cheap (a few indexed scans of the small control-plane tables) and cached briefly.
"""
from __future__ import annotations

import datetime as _dt
import time as _time

_CACHE = {'exp': 0.0, 'val': None}
_TTL = 300


def _month_key(d):
    return f'{d.year:04d}-{d.month:02d}'


def _month_labels(n):
    """The last ``n`` calendar months as 'YYYY-MM', oldest first."""
    today = _dt.date.today().replace(day=1)
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(f'{y:04d}-{m:02d}')
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


def monthly_trends(months=12, *, use_cache=True):
    from utils import tenancy
    now = _time.time()
    if use_cache and _CACHE['val'] and _CACHE['exp'] > now and _CACHE['val'].get('_months') == months:
        return {k: v for k, v in _CACHE['val'].items() if k != '_months'}

    labels = _month_labels(months)
    idx = {k: i for i, k in enumerate(labels)}
    signups = [0] * months
    payments = [0] * months
    churn = [0] * months

    tenancy.init_control_plane()
    with tenancy._session() as s:
        for (created,) in s.query(tenancy.Tenant.created_at).all():
            if created:
                k = _month_key(created)
                if k in idx:
                    signups[idx[k]] += 1
        for (at,) in s.query(tenancy.ProcessedPayment.at).all():
            if at:
                k = _month_key(at)
                if k in idx:
                    payments[idx[k]] += 1
        churn_actions = ('suspend', 'delete', 'bulk_suspend', 'bulk_delete')
        for at, action in s.query(tenancy.PlatformAudit.at, tenancy.PlatformAudit.action).all():
            if at and action in churn_actions:
                k = _month_key(at)
                if k in idx:
                    churn[idx[k]] += 1

    # Cumulative schools needs signups from *before* the window too, so start the
    # running total at the count created before the first shown month.
    first = labels[0]
    with tenancy._session() as s:
        before = sum(1 for (c,) in s.query(tenancy.Tenant.created_at).all()
                     if c and _month_key(c) < first)
    cumulative = []
    run = before
    for v in signups:
        run += v
        cumulative.append(run)

    out = {
        'labels': labels,
        'signups': signups, 'payments': payments, 'churn': churn,
        'cumulative': cumulative,
        'totals': {
            'signups': sum(signups), 'payments': sum(payments), 'churn': sum(churn),
            'signups_last': signups[-1], 'payments_last': payments[-1], 'churn_last': churn[-1],
        },
    }
    _CACHE['val'] = dict(out, _months=months)
    _CACHE['exp'] = now + _TTL
    return out
