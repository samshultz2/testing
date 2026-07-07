"""Subscription tiers for school billing.

One monthly base price (TENANT_PRICE_KOBO) drives three tiers — Monthly, Termly
and Annual — with longer commitments discounted. Termly/annual prices default to
a discounted multiple of the monthly base but can be pinned via config. Every
tier maps onto the existing billing primitive: paying grants `days` of access
(billing.record_payment(days=...)), so nothing else in the state machine changes.

Prices are live-editable by the platform admin at /platform/pricing. Config env
vars are the *seed* — a stored override document in the control-plane DB
(key 'pricing') takes precedence, so changing a price needs no redeploy. A price
change only ever affects *future* payments: the amount is locked when a school
checks out (routes/billing.start_payment), so existing subscribers are never
retro-billed.
"""
from __future__ import annotations

TIER_IDS = ('monthly', 'termly', 'annual')
PRICING_KEY = 'pricing'


_CFG_KEYS = ('TENANT_PRICE_KOBO', 'TENANT_PLAN_DAYS', 'TENANT_TERM_DAYS',
             'TENANT_TERMLY_PRICE_KOBO', 'TENANT_ANNUAL_PRICE_KOBO')


def _cfg(cfg=None):
    if cfg is not None:
        return cfg
    try:
        from flask import current_app
        return current_app.config          # inside a request / app context
    except Exception:
        pass
    # No app context (e.g. the daily billing cron): read the Config class.
    from config import Config
    return {k: getattr(Config, k, None) for k in _CFG_KEYS}


def _naira(kobo):
    return int((kobo or 0) // 100)


def _stored_overrides():
    """The admin-saved pricing overrides ({'tiers': {...}}), or {} if none/unavailable."""
    try:
        from utils import tenancy
        return tenancy.get_content(PRICING_KEY) or {}
    except Exception:
        return {}


def tenant_plans(cfg=None, overrides=None, include_disabled=False):
    """The available subscription tiers, as display-ready dicts. Prices are in
    kobo (for Paystack) with a naira convenience field and a computed savings %
    versus paying monthly for the same duration.

    Config supplies the defaults; a stored override document (from /platform/pricing)
    takes precedence per tier. Disabled tiers are dropped unless include_disabled.
    Each returned tier carries an `enabled` flag for the admin editor."""
    cfg = _cfg(cfg)
    base = int(cfg.get('TENANT_PRICE_KOBO', 0) or 0)
    month_days = int(cfg.get('TENANT_PLAN_DAYS', 30) or 30)
    term_days = int(cfg.get('TENANT_TERM_DAYS', 120) or 120)
    # Pricing is on a clean months basis (so annual = 12x monthly, discounted);
    # access is granted in `days`.
    term_months = max(1, round(term_days / month_days))

    termly = int(cfg.get('TENANT_TERMLY_PRICE_KOBO') or round(base * term_months * 0.90))
    annual = int(cfg.get('TENANT_ANNUAL_PRICE_KOBO') or round(base * 12 * 0.80))

    # config-derived defaults, before overrides
    defaults = {
        'monthly': {'id': 'monthly', 'label': 'Monthly', 'days': month_days, 'per': 'month',
                    'price_kobo': base, 'badge': None, 'months': 1},
        'termly':  {'id': 'termly', 'label': 'Termly', 'days': term_days, 'per': 'term',
                    'price_kobo': termly, 'badge': None, 'months': term_months},
        'annual':  {'id': 'annual', 'label': 'Annual', 'days': 365, 'per': 'year',
                    'price_kobo': annual, 'badge': 'Best value', 'months': 12},
    }

    tiers_ov = (overrides if overrides is not None else _stored_overrides()).get('tiers') or {}

    merged = {}
    for tid in TIER_IDS:
        p = dict(defaults[tid])
        o = tiers_ov.get(tid) or {}
        if o.get('price_kobo') is not None:
            p['price_kobo'] = max(0, int(o['price_kobo']))
        if o.get('days'):
            p['days'] = int(o['days'])
        if o.get('label'):
            p['label'] = o['label']
        if 'badge' in o:
            p['badge'] = (o['badge'] or None)
        p['enabled'] = o.get('enabled', True) is not False
        p['price_naira'] = _naira(p['price_kobo'])
        merged[tid] = p

    # Savings are measured against the effective monthly price for the same span.
    eff_monthly = merged['monthly']['price_kobo']

    def savings(price_kobo, months):
        equiv = eff_monthly * months
        return int(round(100 * (1 - price_kobo / equiv))) if equiv else 0

    out = []
    for tid in TIER_IDS:
        p = merged[tid]
        p['savings'] = 0 if tid == 'monthly' else savings(p['price_kobo'], p['months'])
        if include_disabled or p['enabled']:
            out.append(p)
    return out


def get_plan(plan_id, cfg=None):
    """Look up one enabled tier by id; falls back to the first enabled tier
    (Monthly by default) for an unknown/blank/disabled id."""
    plans = tenant_plans(cfg)
    for p in plans:
        if p['id'] == plan_id:
            return p
    return plans[0]


def get_pricing():
    """The raw stored pricing override document ({'tiers': {...}, ...}) or {}."""
    return _stored_overrides()


def save_pricing(doc):
    """Persist the pricing override document to the control plane (live)."""
    from utils import tenancy
    tenancy.save_content(PRICING_KEY, doc)
