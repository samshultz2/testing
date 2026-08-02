"""Billing intelligence for the platform Subscriptions console.

Revenue roll-ups, a renewal forecast (who lapses when, and the revenue that
rides on it), auto-renew coverage and the at-risk / failing-renewal list — all
derived from the control-plane registry and its dates. No amounts are invented:
expected renewal revenue is the *current* per-school price times the count due,
clearly labelled as a forecast.
"""
from __future__ import annotations

from flask import current_app

from utils import tenancy, billing


def _price_naira():
    return (current_app.config.get('TENANT_PRICE_KOBO', 0) or 0) / 100.0


# Forecast horizons (days) → label.
_HORIZONS = ((7, 'Next 7 days'), (30, 'Next 30 days'),
             (60, 'Next 60 days'), (90, 'Next 90 days'))


def billing_overview():
    """A single dict for the Subscriptions page: revenue, auto-renew coverage,
    renewal forecast buckets, and the at-risk renewal list. Null-safe."""
    price = _price_naira()
    tenants = tenancy.list_tenants()

    paying = 0
    auto_on = 0
    card_on_file = 0
    at_risk = []                 # auto-renew on but last attempt errored
    # Cumulative "due within N days" counts among active paying subscribers.
    horizon_counts = {d: 0 for d, _ in _HORIZONS}

    for t in tenants:
        st = billing.status(t)
        if st['owner']:
            continue
        is_paying = st['active'] and t.status == 'active' and not st['on_trial']
        if is_paying:
            paying += 1
        if st['card_on_file']:
            card_on_file += 1
        if st['auto_renew']:
            auto_on += 1
        if st['auto_renew'] and getattr(t, 'auto_renew_last_error', None):
            at_risk.append({
                'name': t.name, 'subdomain': t.subdomain,
                'days_left': st['days_left'],
                'error': (t.auto_renew_last_error or '')[:120],
            })
        # Renewal forecast: any active subscriber (paid or trialing) whose access
        # lapses within a horizon is a renewal opportunity.
        dl = st['days_left']
        if st['active'] and dl is not None and dl >= 0:
            for d, _ in _HORIZONS:
                if dl <= d:
                    horizon_counts[d] += 1

    mrr = paying * price
    forecast = [{
        'days': d, 'label': lb,
        'count': horizon_counts[d],
        'revenue': horizon_counts[d] * price,
    } for d, lb in _HORIZONS]

    at_risk.sort(key=lambda r: (r['days_left'] if r['days_left'] is not None else 999))

    return {
        'price': price,
        'mrr': mrr, 'arr': mrr * 12, 'arpa': price if paying else 0,
        'paying': paying,
        'auto_renew_on': auto_on,
        'card_on_file': card_on_file,
        'auto_renew_pct': round(auto_on / paying * 100) if paying else None,
        'forecast': forecast,
        'at_risk': at_risk,
    }
