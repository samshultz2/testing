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
    return out


def save_settings(data):
    clean = {
        'support_email': (data.get('support_email') or '').strip(),
        'support_phone': (data.get('support_phone') or '').strip(),
        'maintenance_mode': bool(data.get('maintenance_mode')),
        'maintenance_message': (data.get('maintenance_message') or '').strip(),
    }
    tenancy.save_content(SETTINGS_KEY, clean)
    return clean
