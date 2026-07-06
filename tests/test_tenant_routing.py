"""Multi-tenancy Stage 0: request-time routing.

Builds a MULTI_TENANT app over two provisioned schools (SQLite) and drives it
through the real request path with per-school Host headers to prove:
  * a request routes to the right school's database,
  * a session cookie minted for one school is rejected on another,
  * an unknown subdomain 404s,
  * with the flag OFF nothing changes,
  * the current database can be adopted as tenant #1 untouched.
"""
import re
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as SASession

P1 = 'Zebra!Mango42Q'
P2 = 'Kite#River88Lp'


@pytest.fixture()
def mt(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, provisioning, tenant_runtime
    tenancy._reset_engine()
    tenant_runtime.reset_engines()
    tenancy.init_control_plane()
    # two schools, each with a known admin password so we can prove routing
    tenancy.register_tenant('Pioneer', 'pioneer', 'a@pioneer.test')
    tenancy.register_tenant('Summit', 'summit', 'b@summit.test')
    provisioning.provision('pioneer', admin_password=P1)
    provisioning.provision('summit', admin_password=P2)

    from app import create_app
    from config import Config

    class MTConfig(Config):
        TESTING = True
        MULTI_TENANT = True
        TENANT_BASE_DOMAIN = 'posyhub.test'
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'fallback.db')
        WTF_CSRF_ENABLED = False

    app = create_app(MTConfig)
    yield app, tenancy
    tenant_runtime.reset_engines()
    tenancy._reset_engine()


def _login(client, host, username, password):
    html = client.get('/login', headers={'Host': host}).get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html)
    token = m.group(1) if m else ''
    return client.post('/login', headers={'Host': host},
                       data={'username': username, 'password': password, '_csrf_token': token})


def _authed_on(client, host):
    """True if the client has an authenticated session for this host. (Read via a
    real request with the Host header — session_transaction can't see a cookie
    scoped to a subdomain host.) A must-change-password user is redirected to
    /change-password, which still counts as authed; only a bounce to /login is not."""
    r = client.get('/students', headers={'Host': host})
    if r.status_code == 200:
        return True
    if r.status_code == 302:
        return '/login' not in (r.headers.get('Location') or '')
    return False


def test_host_routes_to_the_right_school(mt):
    app, _ = mt
    # Pioneer's admin password works on pioneer's host...
    c = app.test_client()
    _login(c, 'pioneer.posyhub.test', 'admin', P1)
    assert _authed_on(c, 'pioneer.posyhub.test')

    # ...but that same password must NOT work on summit (different database,
    # different admin password) — proves the query hit summit's DB, not pioneer's.
    c2 = app.test_client()
    _login(c2, 'summit.posyhub.test', 'admin', P1)
    assert not _authed_on(c2, 'summit.posyhub.test')
    # summit's own password works on summit
    c3 = app.test_client()
    _login(c3, 'summit.posyhub.test', 'admin', P2)
    assert _authed_on(c3, 'summit.posyhub.test')


def test_cross_tenant_cookie_is_rejected(mt):
    app, _ = mt
    c = app.test_client()
    _login(c, 'pioneer.posyhub.test', 'admin', P1)
    assert _authed_on(c, 'pioneer.posyhub.test')  # authed on pioneer
    # Reuse the SAME cookie against summit's host: routing must drop it.
    r = c.get('/students', headers={'Host': 'summit.posyhub.test'})
    assert r.status_code == 302 and '/login' in (r.headers.get('Location') or '')


def test_unknown_subdomain_404s(mt):
    app, _ = mt
    c = app.test_client()
    assert c.get('/login', headers={'Host': 'nosuch.posyhub.test'}).status_code == 404


def test_apex_host_has_no_tenant(mt):
    app, _ = mt
    c = app.test_client()
    # The bare base domain resolves to no school (marketing/apex host).
    r = c.get('/login', headers={'Host': 'posyhub.test'})
    assert r.status_code in (200, 302)            # not a 404, just no tenant bound


def test_flag_off_is_a_noop(app):
    """With MULTI_TENANT off (the standard app fixture), routing does nothing and
    the single-school login works as always."""
    from config import Config
    assert Config.MULTI_TENANT is False
    from tests.conftest import login_token
    c = app.test_client()
    t = login_token(c)
    r = c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': t})
    assert r.status_code == 302
    with c.session_transaction() as s:
        assert s.get('logged_in') and s.get('t') is None    # no tenant stamped


def test_adopt_current_school_leaves_db_untouched(tmp_path, monkeypatch):
    """The existing database is registered as tenant #1 without being modified."""
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    from utils import tenancy, onboarding
    tenancy._reset_engine()
    # An existing populated DB with a marker table the app doesn't define.
    existing = 'sqlite:///' + str(tmp_path / 'existing.db')
    eng = create_engine(existing)
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE marker (note TEXT)'))
        conn.execute(text("INSERT INTO marker VALUES ('do-not-touch')"))
    eng.dispose()

    t = onboarding.adopt_current_school('pioneer', 'Pioneer', existing, 'head@pioneer.test')
    assert t.status == 'active' and t.database_url == existing

    # The database is byte-unchanged: marker row still present, nothing dropped.
    eng = create_engine(existing)
    with SASession(eng) as s:
        assert s.execute(text('SELECT note FROM marker')).scalar() == 'do-not-touch'
    eng.dispose()
    tenancy._reset_engine()
