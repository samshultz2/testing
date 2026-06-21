"""Regression tests for the legacy shared-password login hardening (audit C1).

The old code shipped a hardcoded default password ("posyhubcomng") and enabled
legacy login by default, granting unauthenticated central-admin to anyone. The
fix removes the built-in password and makes legacy login inert unless explicitly
enabled AND configured with a strong ADMIN_PASSWORD.
"""
import os

from config import Config
from tests.conftest import login_token


def _attempt(client, password):
    tok = login_token(client)
    return client.post('/login', data={'password': password, '_csrf_token': tok},
                       follow_redirects=False)


def test_old_default_password_is_rejected(app):
    """The historically-shipped default password must no longer log anyone in."""
    client = app.test_client()
    _attempt(client, 'posyhubcomng')
    with client.session_transaction() as sess:
        assert not sess.get('logged_in'), 'default password should not authenticate'


def test_blank_password_does_not_authenticate(app):
    client = app.test_client()
    _attempt(client, '')
    with client.session_transaction() as sess:
        assert not sess.get('logged_in')


def test_configured_admin_password_still_works(app):
    """With ENABLE_LEGACY_LOGIN + a configured ADMIN_PASSWORD (set in conftest),
    the legacy path authenticates as central admin — the supported use."""
    assert Config.ADMIN_PASSWORD, 'conftest should configure a test ADMIN_PASSWORD'
    client = app.test_client()
    _attempt(client, Config.ADMIN_PASSWORD)
    with client.session_transaction() as sess:
        assert sess.get('logged_in') is True
        assert sess.get('role') == 'admin'


def test_no_builtin_default_in_source():
    """The source must not carry a usable built-in admin password."""
    import config as cfg
    src = open(cfg.__file__, encoding='utf-8').read()
    assert 'posyhubcomng' not in src, 'remove the hardcoded default password'
    # ADMIN_PASSWORD must derive only from the environment (no literal fallback).
    assert os.environ.get('ADMIN_PASSWORD') == Config.ADMIN_PASSWORD
