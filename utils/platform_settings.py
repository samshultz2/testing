"""Global platform settings (control-plane), editable from /platform/settings.

Small, operational knobs that aren't per-tenant: the platform's own support
contact (shown to schools) and a maintenance-mode switch that raises a banner
across every school's portal. Stored as a SiteContent document so changes are
live with no redeploy.
"""
from __future__ import annotations

from utils import tenancy

SETTINGS_KEY = 'platform_settings'

DEFAULTS = {
    'support_email': '',
    'support_phone': '',
    'maintenance_mode': False,
    'maintenance_message': '',
    # Plan auto-assigned to a school the first time it pays (blank tenants are
    # otherwise grandfathered). 'premium' = all features on, so it never removes
    # access; set to a stricter tier to enforce plans on new paying customers.
    'default_paid_tier': 'premium',
    # Usernames who must approve a school deletion requested by someone else.
    # Empty = no second approval (a solo operator deletes directly).
    'delete_approvers': [],
}


def get_settings():
    out = dict(DEFAULTS)
    try:
        stored = tenancy.get_content(SETTINGS_KEY) or {}
    except Exception:
        stored = {}
    for k in DEFAULTS:
        if k in stored and stored[k] is not None:
            out[k] = stored[k]
    out['maintenance_mode'] = bool(out.get('maintenance_mode'))
    out['delete_approvers'] = [str(x) for x in (out.get('delete_approvers') or []) if str(x).strip()]
    return out


def save_settings(data):
    current = get_settings()
    tier = (data.get('default_paid_tier') or current.get('default_paid_tier') or 'premium').strip().lower()
    if tier not in ('free', 'basic', 'premium', 'enterprise'):
        tier = 'premium'
    approvers = data.get('delete_approvers')
    if approvers is None:                       # field not on the form → keep as is
        approvers = current.get('delete_approvers')
    clean = {
        'support_email': (data.get('support_email') or '').strip(),
        'support_phone': (data.get('support_phone') or '').strip(),
        'maintenance_mode': bool(data.get('maintenance_mode')),
        'maintenance_message': (data.get('maintenance_message') or '').strip(),
        'default_paid_tier': tier,
        'delete_approvers': sorted({str(x).strip() for x in (approvers or []) if str(x).strip()}),
    }
    tenancy.save_content(SETTINGS_KEY, clean)
    return clean
