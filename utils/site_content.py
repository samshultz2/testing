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
    'hero_kicker': 'For nurseries, primary & secondary schools — and school groups',
    'nigeria_note': 'Built for Nigerian schools — WAEC, JAMB, NECO and term-based '
                    'report cards out of the box — and adaptable to other systems.',
    'security': [
        {'title': 'Isolated per-school database',
         'body': 'Your records live in their own database — never mixed with '
                 'another school’s.'},
        {'title': 'Encrypted, automatic backups',
         'body': 'Data is encrypted at rest and backed up daily, so nothing is '
                 'ever lost.'},
        {'title': 'Role-based access & audit logs',
         'body': 'Every user sees only what they should, and sensitive actions '
                 'are logged.'},
        {'title': 'Secure cloud hosting',
         'body': 'Runs on secure cloud infrastructure with 99.9% uptime — '
                 'available anywhere, on any device.'},
    ],
    'contact': {
        'email': 'hello@edusyncra.site',
        'phone': '+234 800 000 0000',
        'whatsapp': '2348000000000',      # digits only, for wa.me links
    },
    # Legal-document fields (editable from /platform/homepage → Legal). Blank
    # values fall back to sensible defaults at render time: legal_entity → brand,
    # legal_effective → today's date, dpo_email → contact.email.
    'legal_entity': '',       # registered company name, e.g. "EduSyncra Technologies Ltd"
    'legal_effective': '',    # effective date shown on the legal pages, e.g. "1 August 2026"
    'dpo_email': '',          # data-protection / privacy contact address
    'subprocessors': [        # third parties that process data to run the service
        {'name': 'Cloud hosting provider', 'purpose': 'Secure hosting, storage and backups of the platform and its databases'},
        {'name': 'Paystack', 'purpose': 'Processing of subscription card and bank payments'},
        {'name': 'Email delivery provider', 'purpose': 'Sending transactional and notification emails'},
        {'name': 'SMS / WhatsApp messaging provider', 'purpose': 'Delivering SMS and WhatsApp messages to parents and staff'},
    ],
    'faqs': [
        {'q': 'Is there a free trial?',
         'a': 'Yes — every new school gets 3 days free, no card required. After '
              'that you subscribe to keep your portal active.'},
        {'q': 'How long does setup take?',
         'a': 'Minutes. You register, confirm your email, and your private portal '
              'and admin login are provisioned automatically — no installs.'},
        {'q': 'Is training provided?',
         'a': 'The app is designed to need little or no training, and our team '
              'helps you get started. Guided workflows walk you through each step.'},
        {'q': 'Can we import our existing student data?',
         'a': 'Yes. Students and other records can be imported from spreadsheets, '
              'so you don’t start from scratch.'},
        {'q': 'Does it support multiple branches?',
         'a': 'Yes. Run many campuses with per-branch admins, or a single school '
              'with no branches at all — it scales with you.'},
        {'q': 'Can parents and students access the system?',
         'a': 'Yes — parents and students get their own portals for results, '
              'attendance and fee status, on any device.'},
        {'q': 'Is my data secure and separate from other schools?',
         'a': 'Completely. Each school gets its own encrypted database on its own '
              'subdomain, with daily backups and role-based access — nothing is shared.'},
        {'q': 'What payment methods are supported?',
         'a': 'Secure online payment (card and bank transfer) from your portal’s '
              'billing page once your trial starts.'},
        {'q': 'Can we cancel anytime?',
         'a': 'Yes. There’s no lock-in — you can stop whenever you like and your '
              'data stays yours.'},
    ],
    'testimonials': [
        {'name': 'Mrs. Adeyemi, Principal', 'quote': 'Result processing that took '
         'us a week now takes an afternoon. Report cards are ready the same day.'},
        {'name': 'Mr. Okoro, Proprietor', 'quote': 'One portal for three campuses. '
         'I can see fees, attendance and results across every branch from my phone.'},
        {'name': 'Mrs. Bello, Admin', 'quote': 'Parents stopped calling for results '
         '— they just check the portal. Setup took minutes, not weeks.'},
    ],
    'footer': '© EduSyncra — school management, simplified.',
}


def _price_naira():
    """The headline price shown on the homepage — always the live Monthly tier,
    so pricing has a single source (the /platform/pricing editor)."""
    try:
        from utils.plans import tenant_plans
        for p in tenant_plans():
            if p['id'] == 'monthly':
                return p['price_naira']
    except Exception:
        pass
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
    # Price is owned by the pricing editor (the Monthly tier), not the homepage
    # editor — one source of truth, so the two can never drift apart.
    content['price_naira'] = _price_naira()
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
