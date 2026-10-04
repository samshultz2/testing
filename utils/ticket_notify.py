"""Support-ticket notifications (control plane).

Tickets and their messages live in the control-plane database (see
``utils/tenancy.SupportTicket``/``TicketMessage``), not in any school's own
database — so neither side of a ticket conversation can use the per-tenant
in-app bell (``utils/notify.py``) to hear about it. Email is the one channel
that reaches both sides without switching database context:

- A school creating or replying to a ticket emails the platform's own
  support inbox (``platform_settings.support_email``), the same address the
  school is shown as its contact.
- The platform operator replying emails the school's registered
  ``Tenant.admin_email`` directly, with a link back to their support
  portal.

Best-effort throughout: a failure here must never break saving the ticket
message that triggered it.
"""
from __future__ import annotations

from flask import current_app

from utils import mailer


def _ticket_url_for_school(ticket):
    """The school's own support-thread URL, built the same way the
    impersonation hand-off link is (routes/platform.py) since this runs
    outside that school's app context and can't use url_for against it."""
    base = current_app.config.get('TENANT_BASE_DOMAIN', '')
    if base:
        return f'https://{ticket.subdomain}.{base}/support/{ticket.id}'
    return f'/support/{ticket.id}'   # single-host (dev / no base domain)


def notify_operator_of_ticket_activity(ticket, body, *, is_new):
    """Email the platform's support inbox that a school opened or replied to
    a ticket. No-op when no support inbox is configured or mail isn't set up
    — the operator still sees it via the open-ticket count in the console."""
    try:
        from utils import platform_settings
        to = (platform_settings.get_settings() or {}).get('support_email')
        if not to or not mailer.is_configured():
            return
        verb = 'opened' if is_new else 'replied to'
        subject = f'[Support] {ticket.subdomain} {verb} ticket #{ticket.id}: {ticket.subject}'
        text = (f'{ticket.subdomain} {verb} a support ticket.\n\n'
               f'Subject: {ticket.subject}\n\n{body}\n\n'
               f'Reply from the platform console: /platform/tickets/{ticket.id}')
        mailer.send_email_async(to, subject, text)
    except Exception:
        pass


def notify_school_of_reply(ticket, body):
    """Email the school's registered admin address that the platform
    operator replied to their ticket. No-op when the tenant has no
    admin_email on file or mail isn't configured."""
    try:
        if not mailer.is_configured():
            return
        from utils import tenancy
        t = tenancy.get_tenant(ticket.subdomain)
        to = getattr(t, 'admin_email', None) if t else None
        if not to:
            return
        link = _ticket_url_for_school(ticket)
        subject = f'Reply to your support ticket: {ticket.subject}'
        html = mailer.branded_html(
            'New reply on your support ticket',
            [f'Subject: {ticket.subject}', body],
            button={'label': 'View the conversation', 'url': link},
            footer='Sent by EduSyncra Support.')
        text = f'{body}\n\nView the conversation: {link}'
        mailer.send_email_async(to, subject, text, html=html)
    except Exception:
        pass
