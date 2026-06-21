"""Shared pytest fixtures. Each test run uses a fresh temporary database."""
import os
import re
import tempfile

import pytest

os.environ['POSYHUB_TESTING'] = '1'
# Legacy shared-password login now has no built-in password and is off by
# default; the suite exercises it, so opt in with a known test password before
# config is imported (real env vars still win via setdefault).
os.environ.setdefault('ENABLE_LEGACY_LOGIN', '1')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-secret-pw')

from app import create_app  # noqa: E402
from config import Config  # noqa: E402


@pytest.fixture(scope='session')
def app():
    tmpdir = tempfile.mkdtemp()

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(tmpdir, 'test.db')
        BACKUP_RETENTION = 0

    return create_app(TestConfig)


@pytest.fixture()
def client(app):
    return app.test_client()


def login_token(client):
    html = client.get('/login').get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def page_token(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


@pytest.fixture()
def auth_client(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client
