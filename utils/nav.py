"""Post-login return-to-page ("next") helpers.

When a logged-out user hits a protected page we bounce them to the login page
with a ``?next=`` pointing back at where they were, then send them there after a
successful login — so they continue where they left off instead of always
landing on the dashboard.

``next`` is only ever honoured when it is a **same-site relative path** (starts
with a single ``/``), so it can't be used as an open-redirect to another site.
"""
from urllib.parse import urlparse

from flask import request, url_for


def login_url():
    """The login URL, carrying a ?next= back to the current GET page.

    Only GET pages are remembered (replaying a POST after login would be wrong),
    and never the auth pages themselves (login/logout/mfa)."""
    nxt = None
    ep = request.endpoint or ''
    if request.method == 'GET' and not ep.startswith('auth.'):
        nxt = request.full_path
        if nxt.endswith('?'):                 # full_path appends a bare '?' when no query
            nxt = nxt[:-1]
    return url_for('auth.login', next=nxt) if nxt else url_for('auth.login')


def safe_next(raw, fallback=None):
    """Return ``raw`` only if it is a safe same-site relative path; else fallback.

    Rejects absolute URLs, scheme-relative ``//host`` URLs, and anything with a
    scheme or host — the classic open-redirect vectors."""
    if not raw or not isinstance(raw, str):
        return fallback
    if not raw.startswith('/') or raw.startswith('//') or raw.startswith('/\\'):
        return fallback
    p = urlparse(raw)
    if p.scheme or p.netloc:
        return fallback
    return raw
