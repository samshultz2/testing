"""
Production hardening wiring: reverse-proxy support, security response headers,
request/error logging, and a health-check endpoint.

These are safe in every environment — in development they are effectively
no-ops or harmless defaults — so :func:`harden` can be called unconditionally
from the application factory.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from flask import request


def apply_proxy_fix(app):
    """Honour X-Forwarded-* headers when running behind a reverse proxy.

    Enabled only when TRUST_PROXY is truthy, so the app cannot be tricked into
    trusting forwarded headers while exposed directly to clients.
    """
    if not app.config.get('TRUST_PROXY'):
        return
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.logger.info('ProxyFix enabled (trusting X-Forwarded-* headers).')


def forwarded_scheme():
    """The scheme the *client* actually used, read from the proxy's forwarded
    headers (works even without ProxyFix). Falls back to the app-perceived scheme.

    Reading the header directly is what makes the HTTPS redirect below loop-safe:
    a real HTTPS request forwarded by Cloudflare/nginx carries
    ``X-Forwarded-Proto: https`` (or ``CF-Visitor: {"scheme":"https"}``), so it is
    never mistaken for insecure — unlike the old ``request.is_secure`` check that
    saw every request as http when the header wasn't surfaced.
    """
    xfp = request.headers.get('X-Forwarded-Proto')
    if xfp:
        return xfp.split(',')[0].strip().lower()
    cf = request.headers.get('CF-Visitor') or ''
    if '"scheme":"https"' in cf.replace(' ', ''):
        return 'https'
    if '"scheme":"http"' in cf.replace(' ', ''):
        return 'http'
    return request.scheme


def register_https_redirect(app):
    """Send proxied HTTP visitors to HTTPS — but ONLY when the forwarded proto is
    explicitly 'http', so a real HTTPS request can never be redirected (no loop).
    Enabled by FORCE_HTTPS. Skips health checks and non-idempotent methods (we
    redirect navigations, not form POSTs)."""
    if not app.config.get('FORCE_HTTPS'):
        return
    from flask import redirect

    @app.before_request
    def _https_redirect():
        if request.method not in ('GET', 'HEAD'):
            return None
        if request.path == '/healthz':
            return None
        if forwarded_scheme() != 'http':
            return None                       # already https (or unknown) → leave it
        target = request.url.replace('http://', 'https://', 1)
        return redirect(target, code=301)


def register_security_headers(app):
    """Send security headers on every response.

    Reuses the existing :func:`utils.security.add_security_headers` (which
    carries the app's CSP) and layers HSTS on top for secure requests.
    """
    if not app.config.get('SECURITY_HEADERS', True):
        return

    from utils.security import add_security_headers

    csp_override = app.config.get('CONTENT_SECURITY_POLICY', '')
    hsts = app.config.get('ENABLE_HSTS', False)

    @app.after_request
    def _security_headers(resp):
        resp = add_security_headers(resp)
        if csp_override:
            resp.headers['Content-Security-Policy'] = csp_override
        if hsts and (request.is_secure or forwarded_scheme() == 'https'):
            resp.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains')
        return resp


def configure_logging(app):
    """Log to stderr (always) and optionally a rotating file (LOG_FILE)."""
    level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO'), logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')

    root = logging.getLogger()
    root.setLevel(level)

    if not any(getattr(h, '_posyhub', False) and isinstance(h, logging.StreamHandler)
               and not isinstance(h, RotatingFileHandler) for h in root.handlers):
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh._posyhub = True
        root.addHandler(sh)

    log_file = app.config.get('LOG_FILE')
    if log_file:
        abspath = os.path.abspath(log_file)
        already = any(getattr(h, 'baseFilename', None) == abspath
                      for h in root.handlers)
        if not already:
            try:
                os.makedirs(os.path.dirname(abspath), exist_ok=True)
                fh = RotatingFileHandler(abspath, maxBytes=5 * 1024 * 1024,
                                         backupCount=5)
                fh.setFormatter(fmt)
                fh._posyhub = True
                root.addHandler(fh)
            except Exception:
                app.logger.warning('Could not open LOG_FILE %s; stderr only', log_file)

    app.logger.setLevel(level)


def register_healthcheck(app):
    """Expose /healthz for liveness + DB connectivity checks."""
    from sqlalchemy import text
    from models import db

    @app.route('/healthz')
    def _healthz():
        try:
            db.session.execute(text('SELECT 1'))
            return {'status': 'ok'}, 200
        except Exception as exc:  # pragma: no cover - ops path
            app.logger.error('healthcheck DB error: %s', exc)
            return {'status': 'error', 'detail': 'database unavailable'}, 503


def enable_compression(app):
    """Gzip/brotli-compress responses — big win on slow/poor connections.

    No-op if flask-compress isn't installed, so it never breaks startup.
    """
    try:
        from flask_compress import Compress
    except ImportError:
        return
    # Compress HTML/CSS/JS/JSON/SVG; skip already-compressed media.
    app.config.setdefault('COMPRESS_MIMETYPES', [
        'text/html', 'text/css', 'text/xml', 'application/json',
        'application/javascript', 'text/javascript', 'image/svg+xml',
    ])
    app.config.setdefault('COMPRESS_MIN_SIZE', 1024)
    Compress(app)


def secure_external_url(endpoint, **values):
    """``url_for(..., _external=True)`` but forced to the canonical HTTPS scheme
    when appropriate — so a link built inside a request (e.g. a staff invite link)
    is https even though the origin sees the request as http behind the proxy.

    Uses HTTPS when the client came in over https (forwarded header), or when the
    app's PREFERRED_URL_SCHEME is https; otherwise falls back to a normal external
    URL (so local http dev is unaffected)."""
    from flask import url_for, current_app
    try:
        secure = (forwarded_scheme() == 'https'
                  or current_app.config.get('PREFERRED_URL_SCHEME') == 'https'
                  or request.is_secure)
    except Exception:
        secure = False
    if secure:
        return url_for(endpoint, _external=True, _scheme='https', **values)
    return url_for(endpoint, _external=True, **values)


def harden(app, config_class=None):
    """Apply all production hardening. Safe to call in every environment."""
    configure_logging(app)
    apply_proxy_fix(app)
    register_https_redirect(app)
    enable_compression(app)
    register_security_headers(app)
    register_healthcheck(app)
    # expose the https-aware external-URL helper to templates
    app.jinja_env.globals.setdefault('secure_external_url', secure_external_url)

    # Surface production-readiness warnings once at startup.
    if config_class is not None and hasattr(config_class, 'warnings'):
        try:
            for msg in config_class.warnings():
                app.logger.warning('PRODUCTION: %s', msg)
        except Exception:
            pass
