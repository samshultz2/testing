"""Minimal SMTP email sender. Disabled until SMTP_HOST + SMTP_FROM are set."""
import smtplib
import ssl
from email.message import EmailMessage

from config import Config


def is_configured():
    return bool(Config.SMTP_HOST and Config.SMTP_FROM)


def send_email(to, subject, body):
    """Send a plain-text email. Returns True on success, never raises."""
    if not is_configured() or not to:
        return False
    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = Config.SMTP_FROM
        msg['To'] = to
        msg.set_content(body)
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as s:
            if Config.SMTP_USE_TLS:
                s.starttls(context=ssl.create_default_context())
            if Config.SMTP_USER:
                s.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception:
        return False
