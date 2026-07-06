"""Platform super-admin dashboard: cross-school view + controls, reachable only
by an admin on the owner school's host."""
import re
import os
import datetime as dt
import pytest


@pytest.fixture()
def mt(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, provisioning, tenant_runtime
    tenancy._reset_engine()
    tenant_runtime.reset_engines()
    tenancy.init_control_plane()
    # the owner school (served on the apex) + two customer schools
    tenancy.register_tenant('My School', 'owner', 'me@edusyncra.test')
    provisioning.provision('owner', admin_password='Zebra!Mango42Q')
    tenancy.set_billing('owner', plan='owner', trial_ends_at=None)   # grandfathered
    tenancy.register_tenant('Alpha', 'alpha', 'a@alpha.test')
    provisioning.provision('alpha')
    tenancy.register_tenant('Beta', 'beta', 'b@beta.test')
    provisioning.provision('beta')

    # owner admin has already set their password
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as _S
    from models import User
    eng = create_engine(tenancy.get_tenant('owner').database_url)
    with _S(eng) as s:
        u = s.query(User).filter_by(username='admin').first()
        u.must_change_password = False
        s.commit()
    eng.dispose()

    from app import create_app
    from config import Config

    class MT(Config):
        TESTING = True
        MULTI_TENANT = True
        TENANT_BASE_DOMAIN = 'edusyncra.test'
        APEX_TENANT = 'owner'
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'fallback.db')

    yield create_app(MT), tenancy
    tenant_runtime.reset_engines()
    tenancy._reset_engine()


def _login_owner(app):
    c = app.test_client()
    H = {'Host': 'edusyncra.test'}           # apex -> owner school
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    return c


def test_dashboard_lists_all_schools_for_owner_admin(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for name in ('My School', 'Alpha', 'Beta'):
        assert name in body
    assert 'Owner · free' in body


def test_dashboard_is_404_from_a_customer_host(mt):
    app, _ = mt
    c = _login_owner(app)
    # same session, but on a customer subdomain -> not the owner -> hidden
    assert c.get('/platform/', headers={'Host': 'alpha.edusyncra.test'}).status_code in (404, 302)


def test_dashboard_hidden_without_login(mt):
    app, _ = mt
    c = app.test_client()
    r = c.get('/platform/', headers={'Host': 'edusyncra.test'})
    assert r.status_code in (302, 404)       # bounced to login / hidden


def test_grant_and_delete_actions(mt):
    app, tenancy = mt
    from utils import billing
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/', headers=H).get_data(as_text=True)).group(1)

    # grant 30 days to alpha
    c.post('/platform/alpha/grant', headers=H, data={'days': '30', '_csrf_token': tok})
    assert billing.is_active(tenancy.get_tenant('alpha'))
    assert (tenancy.get_tenant('alpha').paid_until - dt.datetime.utcnow()).days >= 29

    # delete beta (requires typed confirmation)
    beta_db = tenancy.get_tenant('beta').database_url.replace('sqlite:///', '')
    assert os.path.exists(beta_db)
    c.post('/platform/beta/delete', headers=H, data={'confirm': 'beta', '_csrf_token': tok})
    assert tenancy.get_tenant('beta') is None       # registry row gone
    assert not os.path.exists(beta_db)              # database deleted

    # the owner can never be deleted
    r = c.post('/platform/owner/delete', headers=H, data={'confirm': 'owner', '_csrf_token': tok})
    assert r.status_code == 404
    assert tenancy.get_tenant('owner') is not None


def test_bulk_suspend_and_delete(mt):
    app, tenancy = mt
    import os
    from utils import provisioning
    # add two more customer schools to act on in bulk
    tenancy.register_tenant('Gamma', 'gamma'); provisioning.provision('gamma')
    tenancy.register_tenant('Delta', 'delta'); provisioning.provision('delta')
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/', headers=H).get_data(as_text=True)).group(1)

    # bulk suspend two schools (+ owner in the list, which must be skipped)
    c.post('/platform/bulk', headers=H,
           data={'action': 'suspend', 'subdomains': ['gamma', 'delta', 'owner'], '_csrf_token': tok})
    assert tenancy.get_tenant('gamma').status == 'suspended'
    assert tenancy.get_tenant('delta').status == 'suspended'
    assert tenancy.get_tenant('owner').status == 'active'          # owner untouched

    # bulk delete requires the confirm flag
    gamma_db = tenancy.get_tenant('gamma').database_url.replace('sqlite:///', '')
    c.post('/platform/bulk', headers=H,
           data={'action': 'delete', 'subdomains': ['gamma', 'delta'], '_csrf_token': tok})
    assert tenancy.get_tenant('gamma') is not None                 # no confirm -> nothing deleted
    c.post('/platform/bulk', headers=H,
           data={'action': 'delete', 'subdomains': ['gamma', 'delta'],
                 'confirm_delete': 'yes', '_csrf_token': tok})
    assert tenancy.get_tenant('gamma') is None and tenancy.get_tenant('delta') is None
    assert not os.path.exists(gamma_db)
