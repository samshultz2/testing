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


def test_overview_loads_for_owner_admin(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Command center' in body and 'recurring revenue' in body.lower()
    # command palette + global search shell is present on every console page
    assert 'cmdTrigger' in body and '/platform/search' in body


def test_global_search_finds_school(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/search?q=alph', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    data = r.get_json()
    labels = [x['label'] for x in data['results']]
    assert any('Alpha' == l for l in labels), labels
    # a page destination is always searchable
    r2 = c.get('/platform/search?q=analytics', headers={'Host': 'edusyncra.test'})
    assert any(x['type'] == 'page' for x in r2.get_json()['results'])


def test_schools_page_lists_all_schools_for_owner_admin(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/schools', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    for name in ('My School', 'Alpha', 'Beta'):
        assert name in body
    assert 'Owner · free' in body


def test_subscriptions_page_loads(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/subscriptions', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # billing console: forecast, auto-renew coverage and the payments ledger
    assert 'Renewal forecast' in body
    assert 'Auto-renew coverage' in body
    assert 'Payments ledger' in body


def test_payments_ledger_csv_export(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/subscriptions/payments.csv', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    assert 'text/csv' in r.headers.get('Content-Type', '')
    assert 'Date,School,Subdomain,Reference' in r.get_data(as_text=True)


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
                    c.get('/platform/schools', headers=H).get_data(as_text=True)).group(1)

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
                    c.get('/platform/schools', headers=H).get_data(as_text=True)).group(1)

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


def test_tenant_profile_loads(mt):
    app, _ = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    r = c.get('/platform/tenant/alpha', headers=H)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Alpha' in body
    for sec in ('General information', 'Live usage', 'Subscription', 'Quick actions',
                'Internal notes'):
        assert sec in body


def test_tenant_notes_and_tags_persist(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)).group(1)
    c.post('/platform/tenant/alpha/notes', headers=H,
           data={'notes': 'Priority customer — three campuses.',
                 'tags': 'priority,  multi-branch ', '_csrf_token': tok})
    t = tenancy.get_tenant('alpha')
    assert t.notes == 'Priority customer — three campuses.'
    assert t.tags == 'priority, multi-branch'          # normalised
    body = c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)
    assert 'Priority customer' in body and 'multi-branch' in body


def test_tenant_crm_fields_persist_and_render(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)).group(1)
    c.post('/platform/tenant/alpha/notes', headers=H,
           data={'notes': 'Key account.', 'tags': 'multi-branch',
                 'account_manager': 'Grace O.', 'priority': 'vip', 'risk': 'watch',
                 '_csrf_token': tok})
    t = tenancy.get_tenant('alpha')
    assert t.priority == 'vip' and t.risk == 'watch' and t.account_manager == 'Grace O.'
    body = c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)
    assert 'VIP' in body and 'Grace O.' in body and 'Watch' in body


def test_tenant_timeline_shows_events(mt):
    app, _ = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    body = c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)
    assert 'Activity timeline' in body
    assert 'Registered' in body and 'Provisioned' in body   # real lifecycle events


def test_archive_and_restore(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)).group(1)
    # archive: keeps the registry row (unlike delete) but takes it offline
    c.post('/platform/alpha/archive', headers=H, data={'_csrf_token': tok})
    assert tenancy.get_tenant('alpha').status == 'archived'
    # archived tenant is unreachable on its own host (tenant_runtime only serves active)
    assert c.get('/', headers={'Host': 'alpha.edusyncra.test'}).status_code in (404, 302, 503)
    # restore: back online
    c.post('/platform/alpha/archive', headers=H, data={'_csrf_token': tok})
    assert tenancy.get_tenant('alpha').status == 'active'
    # the owner can never be archived
    r = c.post('/platform/owner/archive', headers=H, data={'_csrf_token': tok})
    assert r.status_code == 404
    assert tenancy.get_tenant('owner').status == 'active'


def test_features_editor_loads_and_saves(mt):
    app, _ = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    r = c.get('/platform/features', headers=H)
    assert r.status_code == 200
    assert 'Plans &amp; features' in r.get_data(as_text=True) or 'Plans & features' in r.get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', r.get_data(as_text=True)).group(1)
    # turn OFF mock exams for premium and cap premium students at 999
    data = {'_csrf_token': tok, 'premium__l__students': '999'}
    # (omitting premium__f__mock_exams unchecks it)
    c.post('/platform/features', headers=H, data=data)
    from utils import entitlements as ent
    tiers = ent.get_tiers()
    assert tiers['premium']['features']['mock_exams'] is False
    assert tiers['premium']['limits']['students'] == 999


def test_tenant_tier_and_overrides(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    r = c.get('/platform/tenant/alpha', headers=H)
    assert 'Plan &amp; entitlements' in r.get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', r.get_data(as_text=True)).group(1)
    # set Free tier but override mock_exams ON for this one school
    c.post('/platform/tenant/alpha/tier', headers=H,
           data={'_csrf_token': tok, 'tier': 'free', 'ov__mock_exams': 'on'})
    t = tenancy.get_tenant('alpha')
    assert t.tier == 'free'
    from utils import entitlements as ent
    res = ent.resolve(t)
    assert res['features']['mock_exams'] is True          # override beats the Free tier
    assert 'mock_exams' in res['overridden']['features']


def test_impersonation_requires_reason(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)).group(1)
    r = c.post('/platform/tenant/alpha/impersonate', headers=H,
               data={'reason': '', '_csrf_token': tok})
    # bounced back to the profile, no grant minted
    assert r.status_code in (302, 303)
    assert tenancy.list_impersonations() == []


def test_impersonation_full_flow(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/tenant/alpha', headers=H).get_data(as_text=True)).group(1)
    r = c.post('/platform/tenant/alpha/impersonate', headers=H,
               data={'reason': 'ticket #42', 'minutes': '30', '_csrf_token': tok})
    assert r.status_code == 302
    loc = r.headers['Location']
    assert 'alpha.edusyncra.test/impersonate/' in loc
    token = loc.rstrip('/').rsplit('/', 1)[1]

    # exchange the token on the school's own host (fresh client)
    tc = app.test_client()
    TH = {'Host': 'alpha.edusyncra.test'}
    r2 = tc.get('/impersonate/' + token, headers=TH)
    assert r2.status_code == 302                       # session established
    # the read-only support banner appears on the school's pages
    body = tc.get('/', headers=TH, follow_redirects=True).get_data(as_text=True)
    assert 'Support view' in body and 'read-only' in body
    # read-only: any write is refused
    assert tc.post('/', headers=TH).status_code == 403
    # start + a real audit trail entry exist
    assert any(a.action == 'impersonate_start' for a in tenancy.list_platform_audit())
    # operator ends the session
    tc.get('/impersonate/stop', headers=TH)
    assert tc.get('/', headers=TH, follow_redirects=True).status_code == 200
    body2 = tc.get('/', headers=TH, follow_redirects=True).get_data(as_text=True)
    assert 'Support view' not in body2                 # banner gone


def test_impersonation_kill_switch(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    g = tenancy.create_impersonation('boss', 'alpha', 'audit check', ttl_minutes=30)
    tc = app.test_client()
    TH = {'Host': 'alpha.edusyncra.test'}
    tc.get('/impersonate/' + g.token, headers=TH)      # live session
    # kill it from the console
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/impersonation', headers=H).get_data(as_text=True)).group(1)
    c.post('/platform/impersonation/%d/end' % g.id, headers=H, data={'_csrf_token': tok})
    # the next tenant request tears the session down (redirect to login)
    r = tc.get('/', headers=TH)
    assert r.status_code in (301, 302)
    assert 'login' in r.headers.get('Location', '')


def test_audit_hash_chain_detects_tampering(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/schools', headers=H).get_data(as_text=True)).group(1)
    c.post('/platform/alpha/grant', headers=H, data={'days': '30', '_csrf_token': tok})
    c.post('/platform/beta/suspend', headers=H, data={'_csrf_token': tok})
    # a sealed, verifiable chain
    v = tenancy.verify_audit_chain()
    assert v['ok'] is True and v['checked'] >= 2
    # the audit page shows the integrity badge
    body = c.get('/platform/audit', headers=H).get_data(as_text=True)
    assert 'Tamper-evident chain verified' in body
    # tamper with a row directly in the control plane → chain must break
    with tenancy._session() as s:
        row = s.query(tenancy.PlatformAudit).order_by(tenancy.PlatformAudit.id.asc()).first()
        row.detail = 'silently altered'
        s.commit()
    v2 = tenancy.verify_audit_chain()
    assert v2['ok'] is False and v2['broken_at'] is not None


def test_role_presets():
    from utils import platform_roles as pr
    assert pr.preset_caps('support') == ['manage_tenants', 'view_revenue', 'view_analytics']
    assert pr.role_of(pr.preset_caps('billing')) == 'billing'
    assert pr.role_of(['manage_tenants']) == 'custom'


def test_health_score_and_onboarding():
    from utils import platform_customer_success as cs
    import types
    import datetime as dt
    # a lapsed, high-risk school scores low and lands at-risk
    bad = types.SimpleNamespace(status='active', plan='standard', trial_ends_at=None,
                                paid_until=dt.datetime.utcnow() - dt.timedelta(days=5),
                                auto_renew=0, paystack_auth_code=None,
                                auto_renew_last_error='card declined', risk='high',
                                created_at=dt.datetime.utcnow() - dt.timedelta(days=200))
    h = cs.health_score(bad)
    assert h['band'] == 'at_risk' and h['score'] < 40
    ob = cs.onboarding_progress({'branches': 1, 'users': 1, 'staff': 0, 'students': 0})
    assert ob['done'] == 2 and ob['total'] == 4 and ob['pct'] == 50


def test_tenant_profile_shows_customer_success(mt):
    app, _ = mt
    c = _login_owner(app)
    body = c.get('/platform/tenant/alpha', headers={'Host': 'edusyncra.test'}).get_data(as_text=True)
    assert 'Customer health' in body and 'Onboarding progress' in body


def test_tenant_profile_404_for_unknown(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/tenant/nosuchschool', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 404


def test_tenant_usage_counts_are_read(mt):
    app, tenancy = mt
    from utils.platform_stats import tenant_usage
    t = tenancy.get_tenant('alpha')
    usage = tenant_usage(t.database_url, use_cache=False)
    # a freshly provisioned school has 0 students but the query must succeed (int, not None)
    assert usage['students'] == 0 and usage['branches'] is not None


def test_audit_log_records_actions(mt):
    app, tenancy = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/schools', headers=H).get_data(as_text=True)).group(1)
    c.post('/platform/alpha/grant', headers=H, data={'days': '15', '_csrf_token': tok})
    c.post('/platform/alpha/suspend', headers=H, data={'_csrf_token': tok})
    # audit page shows both, newest first, and links the school
    body = c.get('/platform/audit', headers=H).get_data(as_text=True)
    assert 'grant' in body and 'suspend' in body and 'alpha' in body
    # filter by action
    only = c.get('/platform/audit?action=grant', headers=H).get_data(as_text=True)
    assert 'grant' in only
    # the model recorded the actor + detail
    rows = tenancy.list_platform_audit(subdomain='alpha')
    assert any(r.action == 'grant' and '15' in (r.detail or '') for r in rows)
    assert all(r.actor for r in rows)


def test_overview_kpis_and_totals(mt):
    app, _ = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    body = c.get('/platform/', headers={'Host': 'edusyncra.test'}).get_data(as_text=True)
    assert 'ARR' in body and 'New this month' in body
    assert 'Platform footprint' in body and 'Students' in body   # cross-tenant totals strip
    # KPI cards drill down into the filtered schools list
    assert "filter=trial" in body or "filter=paying" in body


def test_schools_filter_segment(mt):
    app, tenancy = mt
    from utils import billing
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/schools', headers=H).get_data(as_text=True)).group(1)
    # make alpha a paying customer
    c.post('/platform/alpha/grant', headers=H, data={'days': '30', '_csrf_token': tok})
    paying = c.get('/platform/schools?filter=paying', headers=H).get_data(as_text=True)
    assert 'Alpha' in paying and 'Beta' not in paying     # only the paying school
    assert 'clear' in paying.lower()                       # active-segment chip


def test_schools_csv_export(mt):
    app, _ = mt
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    r = c.get('/platform/schools/export', headers=H)
    assert r.status_code == 200 and 'text/csv' in r.content_type
    body = r.get_data(as_text=True)
    assert 'Subdomain' in body and 'alpha' in body and 'beta' in body
    # filtered export
    r2 = c.get('/platform/schools/export?filter=trial', headers=H)
    assert 'filename="tenants_trial.csv"' in (r2.headers.get('Content-Disposition') or '')


def test_bulk_grant_days(mt):
    app, tenancy = mt
    from utils import billing
    c = _login_owner(app)
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/platform/schools', headers=H).get_data(as_text=True)).group(1)
    c.post('/platform/bulk', headers=H,
           data={'subdomains': ['alpha', 'beta'], 'action': 'grant', 'days': '20',
                 '_csrf_token': tok})
    assert billing.is_active(tenancy.get_tenant('alpha'))
    assert billing.is_active(tenancy.get_tenant('beta'))


def test_health_page(mt):
    app, _ = mt
    c = _login_owner(app)
    r = c.get('/platform/health', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Control plane database' in body and 'Tenant databases' in body
    assert 'Payment gateway' in body and 'Email (SMTP)' in body


def test_platform_analytics(mt):
    app, tenancy = mt
    from utils import platform_analytics
    c = _login_owner(app)
    r = c.get('/platform/analytics', headers={'Host': 'edusyncra.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'New schools' in body and 'Churn events' in body and 'Cumulative schools' in body
    data = platform_analytics.monthly_trends(12, use_cache=False)
    assert len(data['labels']) == 12 and len(data['signups']) == 12
    # 3 schools were registered this run -> they land in the current month + cumulative
    assert data['cumulative'][-1] >= 3


def _make_owner_admin(app, tenancy, username, password):
    """Create a non-super 'admin' user in the owner school's DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import User
    eng = create_engine(tenancy.get_tenant('owner').database_url)
    S = sessionmaker(bind=eng)
    with S() as s:
        if not s.query(User).filter_by(username=username).first():
            u = User(username=username, full_name=username, role='admin',
                     scope='central', must_change_password=False)
            u.set_password(password); s.add(u); s.commit()
    eng.dispose()


def test_platform_roles_caps_logic(mt):
    app, _ = mt
    from utils import platform_roles
    with app.test_request_context():
        assert platform_roles.caps_for('anyone', is_super=True) == set(platform_roles.CAP_KEYS)
        platform_roles.save_team({'bob': ['view_revenue']})
        assert platform_roles.caps_for('bob', is_super=False) == {'view_revenue'}
        assert platform_roles.caps_for('alice', is_super=False) == set(platform_roles.CAP_KEYS)  # unlisted = full
        platform_roles.save_team({})   # reset


def test_team_page_super_admin_only(mt):
    app, _ = mt
    c = _login_owner(app)
    assert c.get('/platform/team', headers={'Host': 'edusyncra.test'}).status_code == 200


def test_restricted_admin_is_capability_gated(mt):
    app, tenancy = mt
    from utils import platform_roles
    _make_owner_admin(app, tenancy, 'limited', 'Zebra!Mango42Q')
    with app.test_request_context():
        platform_roles.save_team({'limited': ['view_revenue']})   # revenue only
    c = app.test_client()
    H = {'Host': 'edusyncra.test'}
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/login', headers=H).get_data(as_text=True)).group(1)
    c.post('/login', headers=H, data={'username': 'limited', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    assert c.get('/platform/subscriptions', headers=H).status_code == 200   # granted
    assert c.get('/platform/pricing', headers=H).status_code == 403         # not granted
    assert c.get('/platform/analytics', headers=H).status_code == 403       # not granted
    with app.test_request_context():
        platform_roles.save_team({})   # reset for other tests
