"""Marketing homepage content — served by the app, editable from /platform.

The content lives in the control-plane DB (utils.tenancy.SiteContent) so the
marketing/sales team can change copy, features, pricing and FAQ from the
platform dashboard at any time — no code change, no redeploy, and Cloudflare
only ever handles DNS. Anything not overridden falls back to the defaults here.
"""
from __future__ import annotations

from flask import current_app

from utils import tenancy

HOMEPAGE_KEY = 'homepage'

# Sensible defaults (the copy the site ships with). Editing on /platform stores
# an override document; get_homepage() merges the override over these.
DEFAULTS = {
    'brand': 'EduSyncra',
    'hero_title': 'Run your whole school from one private portal.',
    'hero_subtitle': 'Students, staff, results, exams, fees and payroll — one '
                     'secure place. Your own subdomain, your own isolated '
                     'database, set up automatically.',
    'hero_cta': 'Start free trial',
    'trial_note': '3 days free — no card required',
    'price_naira': None,          # None → derive from TENANT_PRICE_KOBO at render
    'price_period': 'month',
    'features': [
        {'title': 'Your own private portal',
         'body': 'A dedicated subdomain and an isolated database — your data '
                 'never mixes with another school’s.'},
        {'title': 'Everything in one place',
         'body': 'Students, staff, results, exams (CBT/Mock), attendance, fees '
                 'and payroll — one system, one login.'},
        {'title': 'Branches & arms, or keep it simple',
         'body': 'Run many campuses with per-branch admins, or a single school '
                 'with no branches at all.'},
        {'title': 'Results & report cards',
         'body': 'Broadsheets, report cards, Mock-WAEC and JAMB snapshots, ready '
                 'to print with your own logo.'},
        {'title': 'Parents & students',
         'body': 'Parent and student portals with results, attendance and '
                 'fee status — on any device.'},
        {'title': 'Set up in minutes',
         'body': 'Register, confirm your email, and your portal is provisioned '
                 'automatically. No installs.'},
    ],
    'steps': [
        {'title': 'Register your school',
         'body': 'Pick a name and a subdomain, and enter your admin email.'},
        {'title': 'Confirm your email',
         'body': 'Click the link we email you — that verifies you own the address.'},
        {'title': 'Your portal is created',
         'body': 'We set up your private portal and admin login automatically, '
                 'then you’re in.'},
    ],
    'faqs': [
        {'q': 'Is there a free trial?',
         'a': 'Yes — every new school gets 3 days free, no card required. After '
              'that you subscribe to keep your portal active.'},
        {'q': 'Is my data separate from other schools?',
         'a': 'Completely. Each school gets its own database on its own '
              'subdomain — nothing is shared.'},
        {'q': 'Do I need branches?',
         'a': 'No. The app works for a single school with no branches, and '
              'scales up to many campuses with per-branch admins.'},
        {'q': 'How do I pay?',
         'a': 'Securely online from your portal’s billing page once your '
              'trial starts. You can also be granted time by the platform team.'},
    ],
    'footer': '© EduSyncra — school management, simplified.',
}


def _price_naira():
    kobo = (current_app.config.get('TENANT_PRICE_KOBO', 0) or 0)
    return int(kobo // 100)


def get_homepage():
    """Merged homepage content: stored overrides on top of DEFAULTS, with the
    price derived from config when not explicitly set."""
    content = dict(DEFAULTS)
    stored = None
    try:
        stored = tenancy.get_content(HOMEPAGE_KEY)
    except Exception:
        stored = None
    if stored:
        content.update({k: v for k, v in stored.items() if v is not None})
    if not content.get('price_naira'):
        content['price_naira'] = _price_naira()
    # Keep trial note in step with the configured trial length if left default.
    return content


def save_homepage(content):
    tenancy.save_content(HOMEPAGE_KEY, content)


# --- helpers for the simple line-based editor -------------------------------
# Features/steps/FAQs are edited as "Title | body" lines so non-developers can
# maintain them without touching JSON.

def parse_pairs(text, keys):
    """Parse a textarea of 'left | right' lines into a list of dicts using the
    two given keys. Blank lines are skipped."""
    out = []
    for line in (text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        left, sep, right = line.partition('|')
        out.append({keys[0]: left.strip(), keys[1]: right.strip()})
    return out


def format_pairs(items, keys):
    """Render a list of dicts back to 'left | right' lines for the editor."""
    return '\n'.join(f"{it.get(keys[0], '')} | {it.get(keys[1], '')}"
                     for it in (items or []))
