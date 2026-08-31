"""Subscription pricing for school billing — a per-tier × per-cycle grid.

Two axes combine into a purchasable *plan*:

  * capability **tier**  — basic / premium / enterprise (features + limits live
    in utils.entitlements). This is what a school picks at signup and what gets
    stamped on ``tenant.tier``.
  * billing **cycle**    — monthly / termly / annual (how long a payment buys,
    granted as ``days``; longer commitments are discounted).

A plan id is ``"<tier>-<cycle>"`` (e.g. ``premium-annual``). Every plan still
maps onto the one billing primitive: paying grants ``days`` of access
(billing.record_payment(days=..., tier=...)), so the state machine is unchanged.

Prices seed from config (TENANT_PRICE_KOBO is the Basic-Monthly anchor) times a
per-tier multiplier and a per-cycle discount. Any cell can be overridden live by
the platform admin at /platform/pricing — a stored document (key 'pricing') in
the control-plane DB takes precedence, so a price change needs no redeploy and
only ever affects *future* payments (the amount is locked at checkout).
"""
from __future__ import annotations

CYCLE_IDS = ('monthly', 'termly', 'annual')
PURCHASABLE_TIERS = ('basic', 'premium', 'enterprise')
TIER_IDS = PURCHASABLE_TIERS            # back-compat alias
DEFAULT_TIER = 'basic'                  # anchor tier for headline / fallback pricing
PRICING_KEY = 'pricing'

# Default price multiplier per capability tier, applied to the monthly anchor.
_TIER_MULT = {'basic': 1.0, 'premium': 2.0, 'enterprise': 4.0}
# Per-cycle discount versus paying month-by-month for the same span.
_CYCLE_DISCOUNT = {'monthly': 1.0, 'termly': 0.90, 'annual': 0.80}

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
    from config import Config              # no app context (e.g. the billing cron)
    return {k: getattr(Config, k, None) for k in _CFG_KEYS}


def _naira(kobo):
    return int((kobo or 0) // 100)


def _stored_overrides():
    """The admin-saved pricing document, or {} if none/unavailable."""
    try:
        from utils import tenancy
        return tenancy.get_content(PRICING_KEY) or {}
    except Exception:
        return {}


def cycles(cfg=None):
    """The billing cycles as {id: {id,label,per,days,months}}. Days come from
    config (monthly/term span); the anchor month length drives term-in-months."""
    cfg = _cfg(cfg)
    month_days = int(cfg.get('TENANT_PLAN_DAYS', 30) or 30)
    term_days = int(cfg.get('TENANT_TERM_DAYS', 120) or 120)
    term_months = max(1, round(term_days / month_days))
    return {
        'monthly': {'id': 'monthly', 'label': 'Monthly', 'per': 'month',
                    'days': month_days, 'months': 1},
        'termly':  {'id': 'termly', 'label': 'Termly', 'per': 'term',
                    'days': term_days, 'months': term_months},
        'annual':  {'id': 'annual', 'label': 'Annual', 'per': 'year',
                    'days': 365, 'months': 12},
    }


def _default_price(base, tier, cycle_meta):
    """Seed price for a (tier, cycle) cell before any admin override."""
    mult = _TIER_MULT.get(tier, 1.0)
    disc = _CYCLE_DISCOUNT.get(cycle_meta['id'], 1.0)
    return int(round(base * mult * cycle_meta['months'] * disc))


def pricing_grid(cfg=None, overrides=None, include_disabled=False):
    """The full purchasable grid: one row per capability tier, each carrying its
    three cycle plans plus the tier's features/limits (for the pricing cards).

    Prices resolve as: admin cell override → (Basic only) legacy per-cycle
    override → config-seeded default. Disabled tiers/cycles are dropped unless
    include_disabled."""
    cfg = _cfg(cfg)
    base = int(cfg.get('TENANT_PRICE_KOBO', 0) or 0)
    cyc = cycles(cfg)
    doc = overrides if overrides is not None else _stored_overrides()
    grid_ov = doc.get('grid') or {}
    cyc_ov = doc.get('cycles') or {}
    tier_en = doc.get('tier_enabled') or {}
    legacy = doc.get('tiers') or {}       # old shape: keyed by cycle, {price_kobo,days,...}

    from utils.entitlements import TIER_LABELS, get_tiers
    ent = get_tiers()

    out = []
    for tier in PURCHASABLE_TIERS:
        tenabled = tier_en.get(tier, True) is not False
        if not include_disabled and not tenabled:
            continue
        row_ov = grid_ov.get(tier) or {}
        plan_list = []
        for cid in CYCLE_IDS:
            cm = dict(cyc[cid])
            co = cyc_ov.get(cid) or {}
            if co.get('days'):
                cm['days'] = int(co['days'])
            if co.get('label'):
                cm['label'] = co['label']
            cenabled = co.get('enabled', True) is not False

            if row_ov.get(cid) is not None:
                price = max(0, int(row_ov[cid]))
            elif tier == DEFAULT_TIER and (legacy.get(cid) or {}).get('price_kobo') is not None:
                price = max(0, int(legacy[cid]['price_kobo']))
            else:
                price = _default_price(base, tier, cm)

            plan_list.append({
                'id': f'{tier}-{cid}', 'tier': tier,
                'tier_label': TIER_LABELS.get(tier, tier.title()),
                'cycle': cid, 'cycle_label': cm['label'],
                'label': f"{TIER_LABELS.get(tier, tier.title())} · {cm['label']}",
                'per': cm['per'], 'days': cm['days'], 'months': cm['months'],
                'price_kobo': price, 'price_naira': _naira(price),
                'enabled': tenabled and cenabled,
                'badge': 'Best value' if cid == 'annual' else None,
            })

        eff_month = next((p['price_kobo'] for p in plan_list if p['cycle'] == 'monthly'), 0)
        for p in plan_list:
            equiv = eff_month * p['months']
            p['savings'] = (0 if p['cycle'] == 'monthly' or not equiv
                            else int(round(100 * (1 - p['price_kobo'] / equiv))))

        visible = [p for p in plan_list if include_disabled or p['enabled']]
        out.append({
            'tier': tier, 'label': TIER_LABELS.get(tier, tier.title()),
            'enabled': tenabled, 'popular': tier == 'premium',
            'features': ent.get(tier, {}).get('features', {}),
            'limits': ent.get(tier, {}).get('limits', {}),
            'plans': {p['cycle']: p for p in plan_list},
            'plan_list': visible,
            'monthly_naira': _naira(eff_month),
            'from_naira': min((p['price_naira'] for p in visible), default=_naira(eff_month)),
        })
    return out


def tenant_plans(cfg=None, overrides=None, include_disabled=False):
    """Back-compat: the anchor tier's cycle plans as a flat list with the old
    ``id`` = cycle ('monthly'/'termly'/'annual'). Used by the marketing homepage
    and site_content for the headline / "from" pricing."""
    grid = pricing_grid(cfg, overrides, include_disabled=True)
    row = next((r for r in grid if r['tier'] == DEFAULT_TIER), grid[0] if grid else None)
    if not row:
        return []
    out = []
    for p in row['plans'].values():
        q = dict(p)
        q['id'] = q['cycle']
        q['label'] = q['cycle_label']
        if include_disabled or q['enabled']:
            out.append(q)
    # keep cycle order stable
    order = {c: i for i, c in enumerate(CYCLE_IDS)}
    out.sort(key=lambda p: order.get(p['cycle'], 9))
    return out


def get_plan(plan_id, cfg=None):
    """Resolve a plan by id. Accepts a combined ``"<tier>-<cycle>"`` id, a bare
    cycle (→ default tier), or a bare tier (→ monthly). Falls back to the default
    tier's Monthly plan for anything unknown/blank."""
    grid = pricing_grid(cfg, include_disabled=True)
    pid = (plan_id or '').strip().lower()
    for row in grid:
        for p in row['plans'].values():
            if p['id'] == pid:
                return p
    default_row = next((r for r in grid if r['tier'] == DEFAULT_TIER), grid[0])
    if pid in CYCLE_IDS:
        return default_row['plans'][pid]
    tier_row = next((r for r in grid if r['tier'] == pid), None)
    if tier_row:
        return tier_row['plans']['monthly']
    return default_row['plans']['monthly']


def get_pricing():
    """The raw stored pricing override document, or {}."""
    return _stored_overrides()


def save_pricing(doc):
    """Persist the pricing override document to the control plane (live)."""
    from utils import tenancy
    tenancy.save_content(PRICING_KEY, doc)
