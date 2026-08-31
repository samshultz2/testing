"""Optional Sentry monitoring: opt-in and degrades gracefully."""
import importlib.util

from utils.monitoring import init_sentry


def test_disabled_without_dsn(app):
    app.config['SENTRY_DSN'] = ''
    assert init_sentry(app) is False


def test_graceful_when_dsn_set(app):
    app.config['SENTRY_DSN'] = 'https://examplePublicKey@o0.ingest.sentry.io/0'
    app.config['SENTRY_TRACES_SAMPLE_RATE'] = 0.0
    result = init_sentry(app)
    if importlib.util.find_spec('sentry_sdk') is None:
        # Package absent -> no-op, no crash.
        assert result is False
    else:
        # Package present -> initialises without error.
        assert result is True
