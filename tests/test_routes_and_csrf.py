"""Smoke tests for key routes and CSRF enforcement."""
from config import Config
from tests.conftest import login_token, page_token


def test_login_requires_csrf(client):
    # No token -> rejected
    assert client.post('/login', data={'password': Config.ADMIN_PASSWORD}).status_code == 400


def test_login_with_csrf_succeeds(client):
    token = login_token(client)
    r = client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    assert r.status_code in (302, 303)


def test_protected_post_blocked_without_token(auth_client):
    # bulk-stream is a state-changing endpoint
    r = auth_client.post('/students/bulk-stream', data={'student_ids': ['1'], 'stream': 'Science'})
    assert r.status_code == 400


def test_protected_post_allowed_with_header(auth_client):
    token = page_token(auth_client)
    r = auth_client.post('/students/bulk-stream',
                         data={'student_ids': [], 'stream': 'Science'},
                         headers={'X-CSRFToken': token})
    # empty selection is a 400 from the route itself, not the CSRF layer
    assert r.status_code in (200, 400)
    assert b'CSRF' not in r.data


def test_key_pages_load(auth_client):
    for path in ['/', '/students', '/results/waec', '/results/jamb',
                 '/results/analytics', '/results/waec/scan', '/results/jamb/scan',
                 '/results/scan/batch?exam=waec', '/mock-jamb/']:
        assert auth_client.get(path).status_code == 200, path


def test_service_worker_served_at_root(client):
    r = client.get('/sw.js')
    assert r.status_code == 200
    assert 'javascript' in r.headers.get('Content-Type', '')
    assert r.headers.get('Service-Worker-Allowed') == '/'
