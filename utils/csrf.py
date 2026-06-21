"""
CSRF protection for PosyHub.

A per-session token is required for all state-changing requests (POST/PUT/
PATCH/DELETE). The token is exposed to templates as ``csrf_token()`` and in a
``<meta name="csrf-token">`` tag; a small script in the base template injects it
into every form and into ``fetch`` calls, so individual templates don't each
need to add it.
"""
import hmac
import secrets
from functools import wraps

from flask import session, request, abort, g

_SESSION_KEY = '_csrf_token'
_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}
# Endpoints called by external services or device-side scripts (no usable
# CSRF token). `parent.pay_webhook` is Paystack; `main.client_error` is the
# diagnostic JS error reporter (rate-limited, no state change).
_EXEMPT_ENDPOINTS = {'parent.pay_webhook', 'main.client_error'}


def generate_csrf_token():
    """Return the session's CSRF token, creating one if needed."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        session[_SESSION_KEY] = token
    return token


def rotate_csrf_token():
    """Issue a brand-new CSRF token. Call on login/logout so a token captured
    before authentication can't be reused against the new session."""
    token = secrets.token_hex(32)
    session[_SESSION_KEY] = token
    return token


def _submitted_token():
    return (
        request.form.get('_csrf_token')
        or request.headers.get('X-CSRFToken')
        or request.headers.get('X-CSRF-Token')
    )


def validate_csrf():
    """Return True if the request carries a valid CSRF token."""
    expected = session.get(_SESSION_KEY)
    submitted = _submitted_token()
    if not expected or not submitted:
        return False
    return hmac.compare_digest(str(expected), str(submitted))


def csrf_protect(f):
    """Decorator form of CSRF protection (kept for explicit per-route use)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method not in _SAFE_METHODS and not validate_csrf():
            abort(400, description='Invalid or missing CSRF token. Please reload and try again.')
        return f(*args, **kwargs)
    return decorated


def init_csrf(app):
    """Enable global CSRF protection and expose the token to templates."""

    @app.before_request
    def _csrf_before_request():
        if request.method in _SAFE_METHODS:
            return
        if request.endpoint in _EXEMPT_ENDPOINTS or getattr(g, '_csrf_exempt', False):
            return
        if not validate_csrf():
            abort(400, description='Invalid or missing CSRF token. Please reload the page and try again.')

    @app.context_processor
    def _inject_csrf():
        return {'csrf_token': generate_csrf_token}
