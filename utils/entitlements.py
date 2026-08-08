"""Feature entitlements: the tier → feature/limit matrix and the resolver.

Two axes, both editable from /platform:
  * FEATURES — boolean capabilities gated by plan (mock exams, predictive
    analytics, the website builder, multi-branch, …).
  * LIMITS   — numeric caps per plan (branches, students, staff, storage, SMS).
    -1 means unlimited.

A tenant has a ``tier`` (free|basic|premium|enterprise) and, optionally, a
per-tenant override overlay (entitlements_json) so sales can unlock one feature
or raise one limit for a single school without moving its whole tier.

resolve(tenant) returns the effective {tier, features, limits} after overlay.
The tier matrix defaults live here and can be overridden live via a control-plane
document (key 'entitlements'), mirroring utils.site_content.
"""
from __future__ import annotations

import json as _json

from utils import tenancy

ENTITLEMENTS_KEY = 'entitlements'

TIER_IDS = ('free', 'basic', 'premium', 'enterprise')
TIER_LABELS = {'free': 'Free', 'basic': 'Basic',
               'premium': 'Premium', 'enterprise': 'Enterprise'}
DEFAULT_TIER = 'basic'

# (key, label) — booleans. Grounded in real product modules.
FEATURES = (
    ('mock_exams', 'Mock JAMB / WAEC & CBT'),
    ('predictive_analytics', 'Predictive academic analytics'),
    ('website_builder', 'Website builder'),
    ('multi_branch', 'Multiple branches'),
    ('library', 'Library management'),
    ('bulk_import', 'Bulk data import'),
)
# (key, label, unit) — numeric caps. -1 = unlimited.
LIMITS = (
    ('branches', 'Branches', ''),
    ('students', 'Students', ''),
    ('staff', 'Staff', ''),
    ('storage_mb', 'Storage', 'MB'),
    ('sms_monthly', 'SMS / month', ''),
)

# Ships-with defaults for each tier. Editable live from /platform/features.
DEFAULTS = {
    'tiers': {
        'free': {
            'features': {'mock_exams': False, 'predictive_analytics': False,
                         'website_builder': False, 'multi_branch': False,
                         'library': False, 'bulk_import': False},
            'limits': {'branches': 1, 'students': 60, 'staff': 15,
                       'storage_mb': 200, 'sms_monthly': 0},
        },
        'basic': {
            'features': {'mock_exams': False, 'predictive_analytics': False,
                         'website_builder': False, 'multi_branch': False,
                         'library': True, 'bulk_import': True},
            'limits': {'branches': 1, 'students': 500, 'staff': 60,
                       'storage_mb': 2000, 'sms_monthly': 500},
        },
        'premium': {
            'features': {'mock_exams': True, 'predictive_analytics': True,
                         'website_builder': True, 'multi_branch': True,
                         'library': True, 'bulk_import': True},
            'limits': {'branches': 5, 'students': 2000, 'staff': 300,
                       'storage_mb': 10000, 'sms_monthly': 5000},
        },
        'enterprise': {
            'features': {'mock_exams': True, 'predictive_analytics': True,
                         'website_builder': True, 'multi_branch': True,
                         'library': True, 'bulk_import': True},
            'limits': {'branches': -1, 'students': -1, 'staff': -1,
                       'storage_mb': -1, 'sms_monthly': -1},
        },
    },
}


def get_tiers():
    """The effective tier matrix: stored overrides merged over DEFAULTS."""
    import copy
    tiers = copy.deepcopy(DEFAULTS['tiers'])
    try:
        stored = tenancy.get_content(ENTITLEMENTS_KEY) or {}
    except Exception:
        stored = {}
    for tid, cfg in (stored.get('tiers') or {}).items():
        if tid not in tiers:
            continue
        for feat, val in (cfg.get('features') or {}).items():
            if feat in tiers[tid]['features']:
                tiers[tid]['features'][feat] = bool(val)
        for lim, val in (cfg.get('limits') or {}).items():
            if lim in tiers[tid]['limits']:
                try:
                    tiers[tid]['limits'][lim] = int(val)
                except (TypeError, ValueError):
                    pass
    return tiers


def save_tiers(tiers):
    """Persist the tier matrix override document (live, no redeploy)."""
    tenancy.save_content(ENTITLEMENTS_KEY, {'tiers': tiers})


def _tenant_tier(tenant):
    tid = (getattr(tenant, 'tier', None) or '').strip().lower()
    return tid if tid in TIER_IDS else DEFAULT_TIER


def _overrides(tenant):
    raw = getattr(tenant, 'entitlements_json', None)
    if not raw:
        return {}
    try:
        return _json.loads(raw) or {}
    except (TypeError, ValueError):
        return {}


def resolve(tenant):
    """Effective entitlements for one tenant: {tier, tier_label, features,
    limits, overridden} after applying the per-tenant overlay over the tier."""
    tid = _tenant_tier(tenant)
    tiers = get_tiers()
    base = tiers.get(tid) or tiers[DEFAULT_TIER]
    features = dict(base['features'])
    limits = dict(base['limits'])
    ov = _overrides(tenant)
    overridden = {'features': set(), 'limits': set()}
    for k, v in (ov.get('features') or {}).items():
        if k in features:
            features[k] = bool(v)
            overridden['features'].add(k)
    for k, v in (ov.get('limits') or {}).items():
        if k in limits:
            try:
                limits[k] = int(v)
                overridden['limits'].add(k)
            except (TypeError, ValueError):
                pass
    return {'tier': tid, 'tier_label': TIER_LABELS.get(tid, tid.title()),
            'features': features, 'limits': limits, 'overridden': overridden}


# Which tenant-portal blueprints each feature gates. Only admin-facing modules
# are gated; student/parent portals are left open.
FEATURE_BLUEPRINTS = {
    'mock_exams': ('mock_jamb', 'mock_waec', 'cbt'),
    'website_builder': ('website_admin',),
    'library': ('library',),
}

# Some features live inside a shared blueprint (results), so gate the specific
# endpoints rather than the whole blueprint (which is core).
FEATURE_ENDPOINTS = {
    'predictive_analytics': {
        'results.readiness', 'results.readiness_funnel', 'results.predictions_dashboard',
        'results.focus_areas', 'results.student_predictions', 'results.api_predict_jamb',
        'results.api_student_predictions', 'results.waec_model_config',
    },
    'bulk_import': {
        'results.import_results', 'results.import_template', 'results.import_results_run',
    },
}


def enforce_entitlements():
    """before_request gate: block a tenant portal blueprint whose feature the
    school's plan doesn't include, showing an upsell page instead.

    Safe by design: only schools with an explicitly-assigned tier are enforced —
    a tenant with no tier set is grandfathered (full access), so turning this on
    never breaks existing customers. The owner school is never gated."""
    from flask import session, request, render_template
    if not session.get('logged_in'):
        return None
    try:
        from utils.tenant_runtime import current_tenant
        from utils import billing
        t = current_tenant()
        if t is None or billing.is_owner(t):
            return None
        tier = (getattr(t, 'tier', None) or '').strip()
        if not tier:
            return None                                  # grandfathered
        ep = request.endpoint or ''
        bp = ep.split('.')[0]
        feat = next((f for f, bps in FEATURE_BLUEPRINTS.items() if bp in bps), None)
        if not feat:
            feat = next((f for f, eps in FEATURE_ENDPOINTS.items() if ep in eps), None)
        if not feat:
            return None
        if not resolve(t)['features'].get(feat, True):
            label = dict(FEATURES).get(feat, feat)
            return render_template('upsell.html', feature=label,
                                   tier_label=resolve(t)['tier_label']), 402
    except Exception:
        return None                                      # never break the app on gate errors
    return None


def entitled(tenant, feature_key):
    """True if the tenant's plan grants ``feature_key`` (with overlay)."""
    return bool(resolve(tenant)['features'].get(feature_key, False))


def limit_of(tenant, limit_key):
    """The numeric cap for ``limit_key`` (-1 = unlimited); None if unknown."""
    return resolve(tenant)['limits'].get(limit_key)


def usage_vs_limits(tenant, usage):
    """Pair live usage against the resolved limits for the profile page.
    ``usage`` is the dict from platform_stats.tenant_usage. Returns a list of
    {key, label, unit, used, cap, unlimited, pct, over}."""
    limits = resolve(tenant)['limits']
    # map limit key -> usage key (usage uses the same names for these)
    rows = []
    for key, label, unit in LIMITS:
        cap = limits.get(key)
        used = usage.get(key) if usage else None
        unlimited = (cap is None or cap < 0)
        pct = None
        over = False
        if used is not None and not unlimited and cap:
            pct = min(100, round(used / cap * 100))
            over = used > cap
        rows.append({'key': key, 'label': label, 'unit': unit, 'used': used,
                     'cap': cap, 'unlimited': unlimited, 'pct': pct, 'over': over})
    return rows
