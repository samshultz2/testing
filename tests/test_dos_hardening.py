"""Abuse / DoS hardening: the global per-IP throttle, per-file OCR metering,
and the oversize-upload (413) handler."""
from config import Config
from utils.security import global_rate_exceeded, charge_bucket


def test_global_rate_exceeded_caps_per_key():
    key = 'test:global:198.51.100.7'
    # The first `max` requests pass; the next one trips the ceiling.
    assert all(not global_rate_exceeded(key, 5, 60) for _ in range(5))
    assert global_rate_exceeded(key, 5, 60)


def test_global_rate_is_isolated_per_key():
    # One IP tripping its ceiling must not throttle a different IP.
    assert all(not global_rate_exceeded('test:global:a', 2, 60) for _ in range(2))
    assert global_rate_exceeded('test:global:a', 2, 60)
    assert not global_rate_exceeded('test:global:b', 2, 60)


def test_charge_bucket_meters_and_caps(app):
    # A 3-hit budget: three charges are admitted, the fourth is refused — this is
    # what makes a batch of files draw down a shared budget one unit at a time.
    with app.test_request_context('/'):
        b = 'test_meter_bucket'
        outcomes = [charge_bucket(b, 3, 10) for _ in range(4)]
    assert outcomes == [False, False, False, True]


def test_global_throttle_blocks_flood_when_enabled(app):
    # The before_request guard is skipped under TESTING; flip it on with a tiny
    # ceiling to prove the wiring actually sheds a flood with 429.
    app.config['TESTING'] = False
    app.config['GLOBAL_RATE_PER_MIN'] = 3
    try:
        client = app.test_client()
        codes = [client.get('/login').status_code for _ in range(6)]
        assert codes[0] != 429          # early requests get through
        assert codes[-1] == 429         # the flood is capped
    finally:
        app.config['TESTING'] = True
        app.config['GLOBAL_RATE_PER_MIN'] = Config.GLOBAL_RATE_PER_MIN


def test_oversize_upload_returns_413(app):
    original = app.config.get('MAX_CONTENT_LENGTH')
    app.config['MAX_CONTENT_LENGTH'] = 64
    try:
        client = app.test_client()
        r = client.post('/login', data={'x': 'y' * 500})
        assert r.status_code == 413
        assert b'too large' in r.get_data().lower()
    finally:
        app.config['MAX_CONTENT_LENGTH'] = original if original is not None else Config.MAX_CONTENT_LENGTH
