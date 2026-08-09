"""Slow-request performance logging (roadmap #4 — observability)."""
import logging

from flask import Flask

from utils.perf_logging import init_perf_logging


def _app(slow_ms):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    app.config['SLOW_REQUEST_MS'] = slow_ms
    init_perf_logging(app)

    @app.route('/ping')
    def ping():
        return 'ok'

    msgs = []
    h = logging.Handler()
    h.emit = lambda record: msgs.append(record.getMessage())
    app.logger.addHandler(h)
    app.logger.setLevel(logging.WARNING)
    return app, msgs


def test_slow_request_is_logged():
    app, msgs = _app(slow_ms=0)        # 0ms threshold → everything counts as slow
    app.test_client().get('/ping')
    assert any('SLOW REQUEST' in m and '/ping' in m for m in msgs)


def test_fast_request_not_logged():
    app, msgs = _app(slow_ms=100000)   # nothing is this slow
    app.test_client().get('/ping')
    assert not any('SLOW REQUEST' in m for m in msgs)
