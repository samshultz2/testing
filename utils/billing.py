"""Tenant billing state machine (multi-tenancy).

A new school gets a free trial; after it ends they must pay to keep access, and
if they stay unpaid past a grace period their database is deleted. The **owner**
school (`plan == 'owner'`) is exempt from all of this — free forever.

State is derived from the registry dates, not a stored status, so it's always
correct without a job having to flip flags:

    owner                      -> always active
    now <= access_until        -> active   (trial or paid)
    access_until < now         -> blocked  (locked out, pay to restore)
    now > access_until + grace -> reapable (database will be deleted)

where ``access_until = max(trial_ends_at, paid_until)``.
"""
from __future__ import annotations

import datetime as _dt

from config import Config


def _now():
    return _dt.datetime.utcnow()


def is_owner(tenant):
    return getattr(tenant, 'plan', None) == 'owner'


def access_until(tenant):
    """The latest moment this school currently has access (or None if never set)."""
    dates = [d for d in (getattr(tenant, 'trial_ends_at', None),
                         getattr(tenant, 'paid_until', None)) if d]
    return max(dates) if dates else None


def is_active(tenant):
    """True if the school may be used right now."""
    if is_owner(tenant):
        return True
    until = access_until(tenant)
    return until is not None and _now() <= until


def is_blocked(tenant):
    """True if access should be denied (expired, pay to restore) — never for owner."""
    return not is_active(tenant)


def is_reapable(tenant, grace_days=None):
    """True if the unpaid grace period has fully elapsed and the database may be
    deleted. Never for the owner or a still-active school."""
    if is_owner(tenant):
        return False
    until = access_until(tenant)
    if until is None:
        return False
    grace = Config.TENANT_BILLING_GRACE_DAYS if grace_days is None else grace_days
    return _now() > until + _dt.timedelta(days=grace)


def days_left(tenant):
    """Whole days of access remaining (negative if expired; None for owner)."""
    if is_owner(tenant):
        return None
    until = access_until(tenant)
    if until is None:
        return 0
    return (until - _now()).days


def on_trial(tenant):
    """True while the school is inside its free trial (no payment yet)."""
    if is_owner(tenant):
        return False
    return (getattr(tenant, 'paid_until', None) is None
            and getattr(tenant, 'trial_ends_at', None) is not None
            and is_active(tenant))


def start_trial(subdomain, days=None):
    """Begin the free trial for a newly-provisioned school."""
    from utils import tenancy
    days = Config.TENANT_TRIAL_DAYS if days is None else days
    return tenancy.set_billing(subdomain, plan='standard',
                               trial_ends_at=_now() + _dt.timedelta(days=days))


def record_payment(subdomain, days=None):
    """Apply a successful payment: extend paid access by ``days`` (default one
    plan period), from whichever is later — now or the current paid_until."""
    from utils import tenancy
    days = Config.TENANT_PLAN_DAYS if days is None else days
    t = tenancy.get_tenant(subdomain)
    if t is None:
        raise ValueError(f'No such school: {subdomain}')
    base = max(_now(), t.paid_until or _now())
    res = tenancy.set_billing(subdomain, plan='standard',
                              paid_until=base + _dt.timedelta(days=days))
    tenancy.clear_notice(subdomain)      # new paid cycle -> reminders reset
    return res


def status(tenant):
    """A small dict for the billing page / API."""
    return {
        'plan': getattr(tenant, 'plan', 'standard'),
        'owner': is_owner(tenant),
        'active': is_active(tenant),
        'on_trial': on_trial(tenant),
        'days_left': days_left(tenant),
        'access_until': access_until(tenant),
        'paid_until': getattr(tenant, 'paid_until', None),
    }
