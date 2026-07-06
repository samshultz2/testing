"""Billing lifecycle reminder emails (multi-tenancy).

A daily job (scripts/billing_cron.py) calls run_notifications(), which emails each
school the right reminder for where it is in the subscription lifecycle — once per
stage. State ("which reminder did we last send") lives in the control plane
(tenancy.BillingNotice) and is reset on payment.

Timeline (relative to access_until = max(trial_ends_at, paid_until)):

    trial, 1 day before end        -> 'trial_ending'  "your trial ends tomorrow"
    subscription, 7 days before    -> 'sub_7d'         "renews in a week"
    subscription, 1 day before     -> 'sub_1d'         "renew tomorrow" + link
    1 day after access ended       -> 'lapsed'         "locked out — renew" + link
    1 day before the grace ends    -> 'purge_soon'     "data deleted tomorrow" + link
    grace fully elapsed            -> (no email; the reaper deletes the database)
"""
from __future__ import annotations

import datetime as _dt

from config import Config
from utils import billing, mailer


def _now():
    return _dt.datetime.utcnow()


def due_notice(t, now=None):
    """Which lifecycle reminder (if any) is due for this school right now."""
    now = now or _now()
    if billing.is_owner(t):
        return None
    au = billing.access_until(t)
    if au is None:
        return None
    grace = Config.TENANT_BILLING_GRACE_DAYS
    paid = getattr(t, 'paid_until', None)
    trial = getattr(t, 'trial_ends_at', None)
    day = _dt.timedelta(days=1)

    # --- access has ended: lockout -> purge window ---
    if now >= au:
        if now >= au + _dt.timedelta(days=grace):
            return None                         # past grace: the reaper handles it
        if now >= au + _dt.timedelta(days=grace - 1):
            return 'purge_soon'
        if now >= au + day:
            return 'lapsed'
        return None                             # first day locked out; email at +1 day

    # --- still active ---
    if paid and paid >= au:                     # subscribed (payment drives access)
        if now >= paid - day:
            return 'sub_1d'
        if now >= paid - _dt.timedelta(days=7):
            return 'sub_7d'
        return None

    # on trial (no payment yet)
    if trial and now >= trial - day:
        return 'trial_ending'
    return None


def notice_content(t, marker, link, days_left=None):
    """(subject, text_body, html_body) for one reminder."""
    name = t.name
    grace = Config.TENANT_BILLING_GRACE_DAYS
    btn = {'label': 'Renew subscription', 'url': link} if link else None

    if marker == 'trial_ending':
        subject = f'Your {name} free trial ends tomorrow'
        paras = [f'Your free trial for {name} ends tomorrow.',
                 'Subscribe now to keep access without interruption — pick monthly, '
                 'termly or annual on your billing page.']
        btn = {'label': 'Choose a plan', 'url': link} if link else None
    elif marker == 'sub_7d':
        subject = f'{name}: your subscription renews in a week'
        paras = [f'Your subscription for {name} ends in 7 days.',
                 'Renew any time to add another period — longer plans save more.']
    elif marker == 'sub_1d':
        subject = f'{name}: your subscription ends tomorrow — renew now'
        paras = [f'Your subscription for {name} ends tomorrow.',
                 'Renew now so your portal keeps working without any interruption.']
    elif marker == 'lapsed':
        subject = f'{name} is locked — renew to restore access'
        paras = [f'Your subscription for {name} has ended, so the portal is now locked.',
                 'You can still sign in, but pages are unavailable until you renew.',
                 f'Your data is kept safe for {grace} days. Renew before then to restore '
                 'everything exactly as it was.']
    elif marker == 'purge_soon':
        subject = f'Final notice: {name} data is deleted tomorrow'
        paras = [f'{name} has been unpaid past its grace period.',
                 'Tomorrow the school’s database and subdomain are permanently deleted '
                 'and cannot be recovered.',
                 'Renew today to keep your data.']
    else:
        return None

    text = '\n\n'.join(paras) + (f'\n\nRenew: {link}' if link else '')
    html = mailer.branded_html(subject, paras, button=btn)
    return subject, text, html


def run_notifications(now=None, send=True):
    """Send every due reminder that hasn't been sent for its stage yet.

    Returns a list of (subdomain, marker) actually notified. Idempotent within a
    stage: the marker is stored so re-running the same day sends nothing new."""
    from utils import tenancy
    now = now or _now()
    base = Config.TENANT_BASE_DOMAIN
    done = []
    for t in tenancy.list_tenants():
        if t.status != 'active' or billing.is_owner(t):
            continue
        marker = due_notice(t, now)
        if not marker:
            continue
        if tenancy.get_notice(t.subdomain) == marker:
            continue                            # already sent this stage
        if not t.admin_email:
            continue
        link = f'https://{t.subdomain}.{base}/billing/' if base else None
        built = notice_content(t, marker, link)
        if not built:
            continue
        subject, text, html = built
        if send:
            try:
                mailer.send_email(t.admin_email, subject, text, html=html)
            except Exception:
                continue                        # don't let one bad address stop the run
            tenancy.set_notice(t.subdomain, marker)
        done.append((t.subdomain, marker))
    return done
