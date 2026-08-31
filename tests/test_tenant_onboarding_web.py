"""Multi-tenancy Stage 3 onboarding routes.

Default: a school is created instantly on /register (database + subdomain + admin
+ trial), protected by per-IP rate limiting. Opt-in: an email-verification link
before provisioning (REGISTRATION_AUTO_PROVISION=0)."""
import re
import pytest

APEX = {'Host': 'edusyncra.test'}


def _mt(tmp_path, monkeypatch, **cfg):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, tenant_runtime
    from utils.security import login_limiter
    tenancy._reset_engine()
    tenant_runtime.reset_engines()
    login_limiter._attempts.clear()          # isolate per-IP registration counters
    tenancy.init_control_plane()
    from app import create_app
    from config import Config

    class MT(Config):
        TESTING = True
        MULTI_TENANT = True
        TENANT_BASE_DOMAIN = 'edusyncra.test'
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'fallback.db')

    for k, v in cfg.items():
        setattr(MT, k, v)
    return create_app(MT)


@pytest.fixture()
def mt_app(tmp_path, monkeypatch):
    app = _mt(tmp_path, monkeypatch)
    yield app
    from utils import tenancy, tenant_runtime
    tenant_runtime.reset_engines()
    tenancy._reset_engine()


def _csrf(client):
    html = client.get('/register', headers=APEX).get_data(as_text=True)
    return re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)


def test_verify_before_provision_is_the_default(mt_app):
    """By default a school must confirm its email before ANY database is made."""
    from utils import tenancy
    c = mt_app.test_client()
    r = c.post('/register', headers=APEX,
               data={'name': 'Pioneer', 'subdomain': 'pioneer',
                     'admin_email': 'head@pioneer.test', '_csrf_token': _csrf(c)})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # recorded as pending — NOT provisioned yet
    t = tenancy.get_tenant('pioneer')
    assert t is not None and t.status == 'pending' and t.database_url is None
    # confirmation link (shown inline in dev because SMTP isn't configured)
    m = re.search(r'/verify/pioneer/[A-Za-z0-9_\-]+', body)
    assert m, 'verification link not shown'
    # clicking it verifies AND provisions
    r2 = c.get(m.group(0), headers=APEX)
    assert r2.status_code == 200 and 'is ready' in r2.get_data(as_text=True)
    t = tenancy.get_tenant('pioneer')
    assert t.status == 'active' and t.database_url
    # a second click can't re-provision
    assert c.get(m.group(0), headers=APEX).status_code == 400


def test_instant_provisioning_when_explicitly_enabled(tmp_path, monkeypatch):
    app = _mt(tmp_path, monkeypatch, REGISTRATION_AUTO_PROVISION=True)
    from utils import tenancy, billing, tenant_runtime
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/register', headers=APEX).get_data(as_text=True)).group(1)
    r = c.post('/register', headers=APEX,
               data={'name': 'Fast', 'subdomain': 'fast', 'admin_email': 'f@x.test', '_csrf_token': tok})
    assert r.status_code == 200 and 'is ready' in r.get_data(as_text=True)
    t = tenancy.get_tenant('fast')
    assert t.status == 'active' and billing.on_trial(t)
    tenant_runtime.reset_engines(); tenancy._reset_engine()


def test_signup_stamps_chosen_tier(tmp_path, monkeypatch):
    """The capability tier picked at signup is set on the tenant so the school
    trials — and later pays for — exactly the plan they chose."""
    app = _mt(tmp_path, monkeypatch, REGISTRATION_AUTO_PROVISION=True)
    from utils import tenancy, tenant_runtime
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/register?tier=premium', headers=APEX).get_data(as_text=True)).group(1)
    r = c.post('/register', headers=APEX,
               data={'name': 'Tiered', 'subdomain': 'tiered', 'admin_email': 't@x.test',
                     'tier': 'premium', 'cycle': 'annual', '_csrf_token': tok})
    assert r.status_code == 200 and 'is ready' in r.get_data(as_text=True)
    assert tenancy.get_tenant('tiered').tier == 'premium'
    # a bogus tier is ignored (school left grandfathered, no tier)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/register', headers=APEX).get_data(as_text=True)).group(1)
    c.post('/register', headers=APEX,
           data={'name': 'Notier', 'subdomain': 'notier', 'admin_email': 'n@x.test',
                 'tier': 'bogus', '_csrf_token': tok})
    assert not (tenancy.get_tenant('notier').tier or '')
    tenant_runtime.reset_engines(); tenancy._reset_engine()


def test_registration_is_ip_rate_limited(tmp_path, monkeypatch):
    app = _mt(tmp_path, monkeypatch, REGISTRATION_MAX_PER_HOUR=2, REGISTRATION_MAX_PER_DAY=2)
    from utils import tenancy
    c = app.test_client()
    ip = {'REMOTE_ADDR': '203.0.113.7'}

    def reg(sub):
        tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                        c.get('/register', headers=APEX, environ_base=ip).get_data(as_text=True)).group(1)
        return c.post('/register', headers=APEX, environ_base=ip,
                      data={'name': sub, 'subdomain': sub, 'admin_email': f'{sub}@x.test',
                            '_csrf_token': tok})

    assert reg('s1a').status_code == 200
    assert reg('s1b').status_code == 200
    blocked = reg('s1c')                              # third from this IP
    assert blocked.status_code == 429
    assert tenancy.get_tenant('s1c') is None          # not created
    from utils import tenant_runtime
    tenant_runtime.reset_engines(); tenancy._reset_engine()


def test_bad_subdomain_is_reported(mt_app):
    c = mt_app.test_client()
    r = c.post('/register', headers=APEX,
               data={'name': 'X', 'subdomain': 'Bad Sub!', 'admin_email': 'x@y.test', '_csrf_token': _csrf(c)})
    assert r.status_code == 200 and 'Invalid subdomain' in r.get_data(as_text=True)


def test_registration_is_404_in_single_tenant_mode(app):
    assert app.test_client().get('/register').status_code == 404
