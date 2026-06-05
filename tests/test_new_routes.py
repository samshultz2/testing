"""Smoke + behavior tests for the newer routes."""
from tests.conftest import page_token


def test_readiness_and_import_pages(auth_client):
    for path in ['/results/readiness', '/results/import', '/results/scan/batch?exam=waec',
                 '/results/scan/batch?exam=jamb', '/results/cutoffs']:
        assert auth_client.get(path).status_code == 200, path


def test_import_templates_download(auth_client):
    for exam in ('waec', 'jamb'):
        r = auth_client.get(f'/results/import/template/{exam}')
        assert r.status_code == 200
        assert 'spreadsheet' in r.headers.get('Content-Type', '')


def test_audit_log_admin_only(auth_client):
    assert auth_client.get('/audit').status_code == 200  # admin via legacy login


def test_audit_log_blocks_teacher(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['logged_in'] = True
        sess['role'] = 'teacher'
        sess['user'] = 'T'
    # admin_required redirects non-admins
    assert client.get('/audit').status_code in (302, 303)


def test_cutoffs_save_requires_csrf(auth_client):
    # No token -> blocked by the global CSRF layer
    r = auth_client.post('/results/cutoffs/save', data={'course_name': 'X'})
    assert r.status_code == 400


def test_cutoff_seed_present_for_advisor(app):
    with app.app_context():
        from models import UniversityCutoff
        assert UniversityCutoff.query.filter_by(university_name='General Requirements').count() >= 30
