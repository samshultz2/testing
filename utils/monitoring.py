"""Optional Sentry error monitoring.

Fully opt-in and gracefully degrading:
  * disabled unless ``SENTRY_DSN`` is set;
  * a no-op (with a logged hint) if the ``sentry-sdk`` package isn't installed,
    so the app still runs.

This is a *separate* layer from utils.error_tracking (the always-on, no-infra
in-app Error Log + email alerts). Enable both, either, or neither.
"""
import logging

_log = logging.getLogger('posyhub.monitoring')


def init_sentry(app):
    """Initialise Sentry if configured and available. Returns True when active."""
    dsn = app.config.get('SENTRY_DSN', '')
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        _log.warning('SENTRY_DSN is set but sentry-sdk is not installed. '
                     'Run: pip install "sentry-sdk[flask]"')
        return False
    try:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=app.config.get('SENTRY_TRACES_SAMPLE_RATE', 0.0),
            environment=app.config.get('SENTRY_ENVIRONMENT') or None,
            send_default_pii=False,
        )
        _log.info('Sentry monitoring enabled.')
        return True
    except Exception as exc:
        _log.warning('Sentry init failed: %s', exc)
        return False
