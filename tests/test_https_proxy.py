"""Behind a TLS-terminating proxy: external links come out https, and proxied
HTTP visitors are redirected to HTTPS (loop-safe — a real HTTPS request whose
X-Forwarded-Proto is https is never redirected)."""
import os
import tempfile

import pytest

from config import Config


@pytest.fixture()
def https_app():
    class C(Config):
        TESTING = True
        FORCE_HTTPS = True
        PREFERRED_URL_SCHEME = 'https'
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(tempfile.mkdtemp(), 't.db')
    from app import create_app
    return create_app(C)


def test_secure_external_url_is_https(https_app):
    from utils.production import secure_external_url
    with https_app.test_request_context('/', base_url='http://x.edusyncra.site'):
        url = secure_external_url('staff_onboarding.join', token='tok123')
    assert url.startswith('https://') and '/join/tok123' in url


def test_proxied_http_redirects_to_https(https_app):
    c = https_app.test_client()
    r = c.get('/students', headers={'X-Forwarded-Proto': 'http'},
              base_url='http://x.edusyncra.site')
    assert r.status_code == 301
    assert r.headers['Location'].startswith('https://')


def test_real_https_is_not_redirected(https_app):
    """X-Forwarded-Proto: https must NOT be redirected (that was the old loop)."""
    c = https_app.test_client()
    r = c.get('/students', headers={'X-Forwarded-Proto': 'https'},
              base_url='http://x.edusyncra.site')
    assert r.status_code != 301                      # not our redirect (login 302 is fine)
    if r.status_code in (301, 302):
        assert not (r.status_code == 301 and r.headers.get('Location', '').startswith('https://x.edusyncra.site/students'))


def test_cf_visitor_header_honoured(https_app):
    c = https_app.test_client()
    r = c.get('/students', headers={'CF-Visitor': '{"scheme":"https"}'},
              base_url='http://x.edusyncra.site')
    assert r.status_code != 301                      # treated as secure


def test_healthz_and_post_not_redirected(https_app):
    c = https_app.test_client()
    assert c.get('/healthz', headers={'X-Forwarded-Proto': 'http'},
                 base_url='http://x.edusyncra.site').status_code == 200
    # a POST is never turned into a redirect (would drop the body)
    r = c.post('/login', headers={'X-Forwarded-Proto': 'http'},
               base_url='http://x.edusyncra.site', data={})
    assert r.status_code != 301
