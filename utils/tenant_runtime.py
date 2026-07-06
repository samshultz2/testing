"""Request-time tenant routing (Stage 0).

Active ONLY when ``Config.MULTI_TENANT`` is on. When off, every function here is
a no-op and the app runs exactly as a single-school install — the current
database is never touched.

When on, each request is resolved to its school from the host subdomain, and
``db.session`` is bound to that school's database engine for the request (via the
``_TenantRoutingSession.get_bind`` override in ``models``). One engine is cached
per school database.
"""
from __future__ import annotations

import threading

from flask import g, request, session, abort, current_app

from utils import tenancy

_engines = {}
_lock = threading.Lock()


def _engine_for(url):
    from sqlalchemy import create_engine
    with _lock:
        eng = _engines.get(url)
        if eng is None:
            opts = (dict(current_app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}))
                    if url.startswith('postgresql') else {})
            eng = create_engine(url, **opts)
            _engines[url] = eng
        return eng


def reset_engines():
    """Dispose + drop cached tenant engines (tests / config changes)."""
    with _lock:
        for eng in _engines.values():
            try:
                eng.dispose()
            except Exception:
                pass
        _engines.clear()


def subdomain_from_host(host, base_domain=''):
    """The school slug from a request host, or None for the apex/marketing host.

    ``pioneer.posyhub.app`` -> ``pioneer`` (using base_domain). Also supports
    ``<slug>.localhost`` / ``<slug>.lvh.me`` for local dev.
    """
    if not host:
        return None
    host = host.split(':')[0].lower().rstrip('.')     # strip port + trailing dot
    base = (base_domain or '').lower()
    if base and host.endswith('.' + base):
        return host[:-(len(base) + 1)].split('.')[-1] or None
    for suffix in ('.localhost', '.lvh.me'):
        if host.endswith(suffix):
            return host[:-len(suffix)].split('.')[-1] or None
    return None


def route_tenant():
    """before_request: resolve host -> tenant -> engine and bind it for this
    request. No-op when MULTI_TENANT is off."""
    if not current_app.config.get('MULTI_TENANT') or request.endpoint == 'static':
        return None
    g.tenant = None
    cfg = current_app.config
    sub = subdomain_from_host(request.host, cfg.get('TENANT_BASE_DOMAIN', ''))
    if not sub:
        # Bare apex host: serve the configured owner school there (so the
        # pre-existing school keeps edusyncra.site), else it's the marketing site.
        sub = cfg.get('APEX_TENANT') or None
        if not sub:
            return None
    elif sub in cfg.get('RESERVED_SUBDOMAINS', set()):
        return None            # platform host (marketing / registration) — no school
    t = tenancy.get_tenant(sub)
    if t is None or t.status != 'active' or not t.database_url:
        abort(404)             # unknown or not-yet-active school
    g.tenant = t
    g.tenant_engine = _engine_for(t.database_url)
    # Bind the session cookie to this tenant: a cookie minted for another school
    # is not honoured here (defence-in-depth beyond the browser's host scoping).
    if session.get('logged_in') and session.get('t') and session.get('t') != sub:
        session.clear()
    return None


def current_tenant():
    """The Tenant for this request, or None (apex host / single-school mode)."""
    return getattr(g, 'tenant', None)


# Endpoints still reachable while a school is locked out for non-payment: the
# billing pages themselves, logout, and static assets.
_BILLING_ALLOWED = {'billing.index', 'billing.start_payment', 'billing.callback',
                    'billing.webhook', 'auth.logout', 'auth.login', 'static'}


def enforce_billing():
    """before_request: if this school's trial/subscription has lapsed, lock it to
    the billing page until it pays. The owner school is exempt. No-op in
    single-school mode or on the marketing host."""
    if not current_app.config.get('MULTI_TENANT'):
        return None
    t = current_tenant()
    if t is None:
        return None
    from utils import billing
    if not billing.is_locked_out(t):
        return None
    ep = request.endpoint or ''
    if ep in _BILLING_ALLOWED:
        return None
    from flask import redirect, url_for
    if request.headers.get('X-Requested-With') == 'fetch' or request.is_json:
        abort(402)                 # Payment Required
    return redirect(url_for('billing.index'))


def bind_session_to_current_tenant():
    """Stamp the resolved tenant into the session at login, so the cookie is
    only valid on that school's subdomain. No-op in single-school mode."""
    t = current_tenant()
    if t is not None:
        session['t'] = t.subdomain


def tenant_upload_folder(app=None, tenant=None):
    """Per-school upload directory (``<UPLOAD_FOLDER>/<subdomain>``) when a tenant
    is in scope, else the base folder.

    NB: this app currently processes uploads in memory (OCR / imports read the
    file and discard it; photos are stored inline) — nothing persistent is
    written here — so cross-tenant file isolation is already satisfied. This
    helper exists so any *future* persistent upload is namespaced per school by
    construction. Use it instead of reading ``UPLOAD_FOLDER`` directly."""
    import os
    from flask import current_app
    app = app or current_app
    base = app.config.get('UPLOAD_FOLDER')
    t = tenant if tenant is not None else current_tenant()
    if t is not None and base:
        path = os.path.join(base, t.subdomain)
        os.makedirs(path, exist_ok=True)
        return path
    return base
