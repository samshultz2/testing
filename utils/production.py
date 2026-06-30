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


def register_https_redirect(app):
    """Behind a trusted proxy, force HTTPS: redirect any plain-HTTP request to
    its https URL (308 preserves method + body). No-op without TRUST_PROXY, so a
    direct LAN/dev deployment is unaffected. With ProxyFix in place,
    ``request.is_secure`` reflects the proxy's X-Forwarded-Proto, so an insecure
    request here is genuinely plain HTTP that should be upgraded.
    """
    if not app.config.get('TRUST_PROXY'):
        return

    @app.before_request
    def _force_https():
        if request.is_secure:
            return None
        host = (request.host or '').split(':')[0]
        if request.path == '/healthz' or host in ('localhost', '127.0.0.1'):
            return None  # internal probes / local access stay reachable
        from flask import redirect
        return redirect(request.url.replace('http://', 'https://', 1), code=308)


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
        if hsts and request.is_secure:
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


def harden(app, config_class=None):
    """Apply all production hardening. Safe to call in every environment."""
    configure_logging(app)
    apply_proxy_fix(app)
    register_https_redirect(app)
    enable_compression(app)
    register_security_headers(app)
    register_healthcheck(app)

    # Surface production-readiness warnings once at startup.
    if config_class is not None and hasattr(config_class, 'warnings'):
        try:
            for msg in config_class.warnings():
                app.logger.warning('PRODUCTION: %s', msg)
        except Exception:
            pass
