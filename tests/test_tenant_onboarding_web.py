"""Multi-tenancy Stage 3: the public registration + verification routes drive the
automatic pipeline (register -> email link -> verify -> auto-provision)."""
import re
import pytest

APEX = {'Host': 'posyhub.test'}


@pytest.fixture()
def mt_app(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, tenant_runtime
    tenancy._reset_engine()
    tenant_runtime.reset_engines()
    tenancy.init_control_plane()
    from app import create_app
    from config import Config

    class MT(Config):
        TESTING = True
        MULTI_TENANT = True
        TENANT_BASE_DOMAIN = 'posyhub.test'
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'fallback.db')

    yield create_app(MT)
    tenant_runtime.reset_engines()
    tenancy._reset_engine()


def _csrf(client):
    html = client.get('/register', headers=APEX).get_data(as_text=True)
    return re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)


def test_register_then_verify_auto_provisions(mt_app):
    from utils import tenancy
    c = mt_app.test_client()
    assert c.get('/register', headers=APEX).status_code == 200

    r = c.post('/register', headers=APEX,
               data={'name': 'Pioneer', 'subdomain': 'pioneer',
                     'admin_email': 'head@pioneer.test', '_csrf_token': _csrf(c)})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # school recorded as pending, awaiting verification
    t = tenancy.get_tenant('pioneer')
    assert t is not None and t.status == 'pending'
    # dev-mode verification link is shown (no mail configured in tests)
    m = re.search(r'/verify/pioneer/[A-Za-z0-9_\-]+', body)
    assert m, 'verification link not shown'

    # Clicking the link verifies AND provisions everything automatically.
    r2 = c.get(m.group(0), headers=APEX)
    assert r2.status_code == 200 and 'is ready' in r2.get_data(as_text=True)
    t = tenancy.get_tenant('pioneer')
    assert t.status == 'active' and t.database_url

    # A second click can't re-provision.
    r3 = c.get(m.group(0), headers=APEX)
    assert r3.status_code == 400


def test_bad_subdomain_is_reported(mt_app):
    c = mt_app.test_client()
    r = c.post('/register', headers=APEX,
               data={'name': 'X', 'subdomain': 'Bad Sub!',
                     'admin_email': 'x@y.test', '_csrf_token': _csrf(c)})
    assert r.status_code == 200 and 'Invalid subdomain' in r.get_data(as_text=True)


def test_registration_is_404_in_single_tenant_mode(app):
    # the standard app fixture has MULTI_TENANT off
    assert app.test_client().get('/register').status_code == 404
