"""Subscription tiers for school billing.

One monthly base price (TENANT_PRICE_KOBO) drives three tiers — Monthly, Termly
and Annual — with longer commitments discounted. Termly/annual prices default to
a discounted multiple of the monthly base but can be pinned via config. Every
tier maps onto the existing billing primitive: paying grants `days` of access
(billing.record_payment(days=...)), so nothing else in the state machine changes.
"""
from __future__ import annotations


def _cfg(cfg=None):
    if cfg is not None:
        return cfg
    from flask import current_app
    return current_app.config


def _naira(kobo):
    return int((kobo or 0) // 100)


def tenant_plans(cfg=None):
    """The available subscription tiers, as display-ready dicts. Prices are in
    kobo (for Paystack) with a naira convenience field and a computed savings %
    versus paying monthly for the same duration."""
    cfg = _cfg(cfg)
    base = int(cfg.get('TENANT_PRICE_KOBO', 0) or 0)
    month_days = int(cfg.get('TENANT_PLAN_DAYS', 30) or 30)
    term_days = int(cfg.get('TENANT_TERM_DAYS', 120) or 120)
    # Pricing is on a clean months basis (so annual = 12x monthly, discounted);
    # access is granted in `days`.
    term_months = max(1, round(term_days / month_days))

    def savings(price_kobo, months):
        equiv = base * months
        return int(round(100 * (1 - price_kobo / equiv))) if equiv else 0

    termly = int(cfg.get('TENANT_TERMLY_PRICE_KOBO') or round(base * term_months * 0.90))
    annual = int(cfg.get('TENANT_ANNUAL_PRICE_KOBO') or round(base * 12 * 0.80))

    plans = [
        {'id': 'monthly', 'label': 'Monthly', 'days': month_days, 'per': 'month',
         'price_kobo': base, 'price_naira': _naira(base), 'savings': 0, 'badge': None},
        {'id': 'termly', 'label': 'Termly', 'days': term_days, 'per': 'term',
         'price_kobo': termly, 'price_naira': _naira(termly),
         'savings': savings(termly, term_months), 'badge': None},
        {'id': 'annual', 'label': 'Annual', 'days': 365, 'per': 'year',
         'price_kobo': annual, 'price_naira': _naira(annual),
         'savings': savings(annual, 12), 'badge': 'Best value'},
    ]
    return plans


def get_plan(plan_id, cfg=None):
    """Look up one tier by id; falls back to Monthly for an unknown/blank id."""
    plans = tenant_plans(cfg)
    for p in plans:
        if p['id'] == plan_id:
            return p
    return plans[0]
