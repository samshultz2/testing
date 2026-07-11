"""Granular platform-admin capabilities.

Access to the console still requires being an admin on the owner school's host
(see routes.platform.platform_admin_required). On top of that, *within* the
console, individual admins can be limited to a subset of capabilities.

Roles live in the control plane (SiteContent key ``platform_team``) as
``{username: [cap, ...]}``. The rules:

  * a ``super_admin`` always has every capability;
  * an admin listed in the team map has exactly the capabilities granted;
  * an admin NOT listed keeps full access — so existing single-operator setups
    are unchanged until someone is deliberately given a limited role.
"""
from __future__ import annotations

TEAM_KEY = 'platform_team'

# key, label — the grantable capabilities.
CAPS = [
    ('manage_tenants', 'Manage tenants (suspend / delete / bulk / notes)'),
    ('manage_billing', 'Manage billing (grant days / record payments)'),
    ('manage_plans', 'Manage subscription plans (pricing)'),
    ('view_revenue', 'View subscriptions & revenue'),
    ('view_analytics', 'View analytics'),
    ('manage_settings', 'Edit the marketing homepage'),
    ('export_reports', 'Export reports (CSV)'),
]
CAP_KEYS = [k for k, _ in CAPS]


def get_team():
    from utils import tenancy
    try:
        data = tenancy.get_content(TEAM_KEY) or {}
    except Exception:
        data = {}
    return {k: [c for c in v if c in CAP_KEYS]
            for k, v in data.items() if isinstance(v, list)}


def save_team(team):
    from utils import tenancy
    clean = {k.strip(): sorted(set(c for c in v if c in CAP_KEYS))
             for k, v in (team or {}).items() if k and k.strip()}
    tenancy.save_content(TEAM_KEY, clean)


def caps_for(username, is_super):
    """The capability set for a platform admin (a set of cap keys)."""
    if is_super:
        return set(CAP_KEYS)
    team = get_team()
    if username in team:
        return set(team[username])
    return set(CAP_KEYS)          # not restricted → full access (backwards-compatible)


def can(cap):
    """True if the current session's admin holds ``cap``."""
    from flask import session
    is_super = session.get('role') == 'super_admin'
    return cap in caps_for(session.get('username') or '', is_super)
