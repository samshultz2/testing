"""Customer-success intelligence for the platform: a per-tenant health score and
an onboarding-progress checklist.

Both are computed from signals the control plane already has — billing/lifecycle
dates, the operator's manual risk flag, and the live usage counts read for the
tenant profile — so nothing is invented. The health score is a leading churn
indicator; onboarding progress shows how far a new school has actually got.
"""
from __future__ import annotations

import datetime as _dt

from utils import billing


def health_score(tenant):
    """Return {'score':0-100, 'band':'healthy|watch|at_risk', 'reasons':[...]}.
    Higher is healthier. The owner tenant is always fully healthy."""
    st = billing.status(tenant)
    if st['owner']:
        return {'score': 100, 'band': 'healthy', 'reasons': ['Owner account']}

    score = 100
    reasons = []
    status = getattr(tenant, 'status', 'active')

    if status == 'suspended':
        score -= 60
        reasons.append('Suspended')
    elif status == 'archived':
        score -= 70
        reasons.append('Archived')

    dl = st['days_left']
    if not st['active']:
        score -= 45
        reasons.append('Access lapsed (unpaid)')
    elif dl is not None and dl <= 3:
        score -= 20
        reasons.append(f'Access ends in {dl}d')

    if st['on_trial']:
        score -= 10
        reasons.append('Still on trial (not yet paying)')

    if getattr(tenant, 'auto_renew_last_error', None):
        score -= 25
        reasons.append('Auto-renew is failing')

    # The operator's manual churn-risk flag (set on the tenant profile).
    risk = (getattr(tenant, 'risk', None) or '').lower()
    if risk == 'high':
        score -= 35
        reasons.append('Flagged high churn-risk')
    elif risk == 'watch':
        score -= 15
        reasons.append('Flagged to watch')

    # Brand-new schools are "onboarding", not unhealthy — note it, don't punish.
    created = getattr(tenant, 'created_at', None)
    if created and (_dt.datetime.utcnow() - created).days <= 3:
        reasons.append('New — onboarding')

    score = max(0, min(100, score))
    band = 'healthy' if score >= 70 else 'watch' if score >= 40 else 'at_risk'
    if not reasons:
        reasons.append('Active & paying')
    return {'score': score, 'band': band, 'reasons': reasons}


# Onboarding milestones, each keyed to a live-usage count.
_ONBOARDING = [
    ('branches', 'Branch / campus set up'),
    ('users', 'Admin & staff logins created'),
    ('staff', 'Staff records added'),
    ('students', 'Students enrolled'),
]


def onboarding_progress(usage):
    """A checklist of setup milestones from live usage, with a completion %.
    Returns {'steps':[{key,label,done}], 'done':n, 'total':n, 'pct':0-100}."""
    steps = []
    done = 0
    for key, label in _ONBOARDING:
        n = (usage or {}).get(key)
        ok = bool(n and n > 0)
        if ok:
            done += 1
        steps.append({'key': key, 'label': label, 'done': ok, 'count': n})
    total = len(_ONBOARDING)
    return {'steps': steps, 'done': done, 'total': total,
            'pct': round(done / total * 100) if total else 0}
