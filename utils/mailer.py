"""SMTP email sender. Disabled until SMTP_HOST + SMTP_FROM are set.

Supports plain-text and HTML (multipart/alternative) bodies, one or many
recipients, and a fire-and-forget async send so request handlers never block on
SMTP. A small :func:`branded_html` helper wraps content in a consistent,
school-branded layout for notification emails (results, receipts, reminders).
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

from config import Config

_log = logging.getLogger('posyhub.mailer')


def is_configured():
    return bool(Config.SMTP_HOST and Config.SMTP_FROM)


def _recipients(to):
    """Normalise ``to`` (str or iterable) to a de-duplicated list of addresses."""
    if not to:
        return []
    if isinstance(to, str):
        to = [to]
    seen, out = set(), []
    for addr in to:
        addr = (addr or '').strip()
        if addr and addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    return out


def send_email(to, subject, body, html=None, attachments=None):
    """Send an email to one or many recipients.

    ``to`` may be a string or a list. ``body`` is the plain-text part; pass
    ``html`` for an HTML alternative. ``attachments`` is an optional list of
    ``(path, filename, mimetype)`` tuples (mimetype may be None). Returns True on
    success, never raises.
    """
    recipients = _recipients(to)
    if not is_configured() or not recipients:
        return False
    try:
        from_name = getattr(Config, 'APP_NAME', '') or ''
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = formataddr((from_name, Config.SMTP_FROM)) if from_name else Config.SMTP_FROM
        msg['To'] = ', '.join(recipients)
        msg.set_content(body or '')
        if html:
            msg.add_alternative(html, subtype='html')
        for path, filename, mimetype in (attachments or []):
            try:
                with open(path, 'rb') as fh:
                    data = fh.read()
                maintype, _, subtype = (mimetype or 'application/octet-stream').partition('/')
                msg.add_attachment(data, maintype=maintype or 'application',
                                   subtype=subtype or 'octet-stream', filename=filename)
            except OSError:
                _log.warning('Skipping missing email attachment: %s', path)
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as s:
            if Config.SMTP_USE_TLS:
                s.starttls(context=ssl.create_default_context())
            if Config.SMTP_USER:
                s.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            s.send_message(msg, to_addrs=recipients)
        return True
    except Exception as exc:
        _log.warning('Email send failed: %s', exc)
        return False


def send_email_async(to, subject, body, html=None):
    """Send in a background thread so the caller (a request) never blocks on
    SMTP. Best-effort; returns immediately. No-op when email is unconfigured."""
    if not is_configured() or not _recipients(to):
        return
    threading.Thread(
        target=send_email, args=(to, subject, body, html),
        daemon=True, name='email-send',
    ).start()


def branded_html(heading, paragraphs, *, button=None, footer=None):
    """Build a simple, consistent HTML email body.

    ``paragraphs`` is a list of strings (plain text, auto-escaped). ``button`` is
    an optional ``{'label': ..., 'url': ...}`` call-to-action. Returns HTML.
    """
    school = getattr(Config, 'APP_NAME', 'School') or 'School'
    parts = [escape(p).replace('\n', '<br>') for p in paragraphs]
    body_html = ''.join(
        f'<p style="margin:0 0 14px;line-height:1.55;color:#374151;">{p}</p>'
        for p in parts
    )
    btn_html = ''
    if button and button.get('url'):
        btn_html = (
            f'<p style="margin:22px 0;"><a href="{escape(button["url"])}" '
            'style="background:#16a34a;color:#fff;text-decoration:none;'
            'padding:11px 20px;border-radius:8px;font-weight:600;display:inline-block;">'
            f'{escape(button.get("label", "Open"))}</a></p>'
        )
    foot = escape(footer) if footer else f'Sent by {escape(school)}.'
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;padding:24px;">'
        '<div style="border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">'
        f'<div style="background:#16a34a;color:#fff;padding:16px 22px;font-size:1.05rem;'
        f'font-weight:700;">{escape(school)}</div>'
        '<div style="padding:22px;">'
        f'<h2 style="margin:0 0 14px;font-size:1.15rem;color:#111827;">{escape(heading)}</h2>'
        f'{body_html}{btn_html}'
        '</div>'
        f'<div style="padding:14px 22px;background:#f9fafb;color:#6b7280;font-size:.8rem;'
        f'border-top:1px solid #e5e7eb;">{foot}</div>'
        '</div></div>'
    )
