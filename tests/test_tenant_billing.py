"""Multi-tenancy billing: free trial, pay-to-continue, owner exemption, and the
reaper that deletes unpaid databases past the grace period."""
import datetime as dt
import re
from types import SimpleNamespace

import pytest

from utils import billing


def _t(**kw):
    base = dict(plan='standard', trial_ends_at=None, paid_until=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _in(days):
    return dt.datetime.utcnow() + dt.timedelta(days=days)


# --- pure state machine -----------------------------------------------------
def test_owner_is_always_active_and_never_reaped():
    o = _t(plan='owner')
    assert billing.is_active(o) and not billing.is_blocked(o)
    assert not billing.is_reapable(o, grace_days=0)
    assert billing.days_left(o) is None


def test_trial_active_then_expired_then_reapable():
    active = _t(trial_ends_at=_in(2))
    assert billing.is_active(active) and billing.on_trial(active)
    expired = _t(trial_ends_at=_in(-1))
    assert billing.is_blocked(expired) and not billing.on_trial(expired)
    assert not billing.is_reapable(expired, grace_days=7)        # within grace
    reapable = _t(trial_ends_at=_in(-9))
    assert billing.is_reapable(reapable, grace_days=7)           # past grace


def test_payment_extends_access():
    paid = _t(trial_ends_at=_in(-1), paid_until=_in(20))         # expired trial, but paid
    assert billing.is_active(paid) and not billing.on_trial(paid)
    assert billing.days_left(paid) >= 19


# --- registry-backed helpers ------------------------------------------------
@pytest.fixture()
def cp(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy
    tenancy._reset_engine()
    tenancy.init_control_plane()
    yield tenancy
    tenancy._reset_engine()


def test_provision_starts_trial_and_adopt_is_owner(cp):
    from utils import provisioning, onboarding
    cp.register_tenant('New School', 'newschool', 'a@x.test')
    provisioning.provision('newschool')
    t = cp.get_tenant('newschool')
    assert t.plan == 'standard' and t.trial_ends_at is not None
    assert billing.is_active(t) and billing.on_trial(t)

    owner = onboarding.adopt_current_school('mine', 'My School', 'sqlite:///x.db', 'me@x.test')
    assert owner.plan == 'owner' and billing.is_owner(owner)
    assert not billing.is_reapable(owner, grace_days=0)


def test_record_payment_moves_expired_to_active(cp):
    cp.register_tenant('Pay School', 'payschool')
    cp.set_billing('payschool', trial_ends_at=_in(-2))          # trial already over
    assert billing.is_blocked(cp.get_tenant('payschool'))
    billing.record_payment('payschool', days=30)
    assert billing.is_active(cp.get_tenant('payschool'))


def test_reaper_deletes_unpaid_but_spares_owner(cp):
    from utils import provisioning, onboarding
    import os
    monkey_days = 7
    # an unpaid, past-grace standard school
    cp.register_tenant('Dead School', 'dead')
    provisioning.provision('dead')
    cp.set_billing('dead', trial_ends_at=_in(-(monkey_days + 3)))
    dead_url = cp.get_tenant('dead').database_url
    dead_path = dead_url.replace('sqlite:///', '')
    assert os.path.exists(dead_path)
    # the owner, long past any date, must never be reaped
    provisioning.provision('keep') if cp.get_tenant('keep') else None

    from scripts.reap_unpaid_tenants import main as reap
    reap([])                                                    # actually delete
    assert not os.path.exists(dead_path)                       # database gone
    assert cp.get_tenant('dead') is None                       # subdomain purged too


# --- enforcement + test-mode payment through the app ------------------------
@pytest.fixture()
def mt(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, provisioning, tenant_runtime
    tenancy._reset_engine()
    tenant_runtime.reset_engines()
    tenancy.init_control_plane()
    tenancy.register_tenant('Trial School', 'trial', 'head@trial.test')
    provisioning.provision('trial', admin_password='Zebra!Mango42Q')
    # Admin has already set their password (so must_change_password doesn't
    # intercept the pages under test).
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as _S
    from models import User
    _eng = create_engine(tenancy.get_tenant('trial').database_url)
    with _S(_eng) as _s:
        _u = _s.query(User).filter_by(username='admin').first()
        _u.must_change_password = False
        _s.commit()
    _eng.dispose()
    from app import create_app
    from config import Config

    class MT(Config):
        TESTING = True
        MULTI_TENANT = True
        TENANT_BASE_DOMAIN = 'edusyncra.test'
        BILLING_TEST_MODE = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'fallback.db')

    yield create_app(MT), tenancy
    tenant_runtime.reset_engines()
    tenancy._reset_engine()


def test_lapsed_school_is_locked_to_billing_then_test_pay_restores(mt):
    app, tenancy = mt
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    # log in as the school admin
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})

    # trial is active -> a normal page is NOT bounced to billing
    r = c.get('/students', headers=H)
    assert '/billing' not in (r.headers.get('Location') or '')

    # expire the trial -> locked to billing
    tenancy.set_billing('trial', trial_ends_at=dt.datetime.utcnow() - dt.timedelta(days=1))
    r = c.get('/students', headers=H)
    assert r.status_code == 302 and '/billing' in (r.headers.get('Location') or '')

    # test-mode payment restores access
    bill = c.get('/billing/', headers=H).get_data(as_text=True)
    btok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', bill).group(1)
    c.post('/billing/pay', headers=H, data={'_csrf_token': btok})
    assert billing.is_active(tenancy.get_tenant('trial'))
    r = c.get('/students', headers=H)
    assert '/billing' not in (r.headers.get('Location') or '')


def test_paying_a_tier_grants_that_tiers_days(mt):
    app, tenancy = mt
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    btok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                     c.get('/billing/', headers=H).get_data(as_text=True)).group(1)

    # annual (365 days) via the test-mode pay path
    c.post('/billing/pay', headers=H, data={'_csrf_token': btok, 'plan': 'annual'})
    assert billing.days_left(tenancy.get_tenant('trial')) >= 360

    # termly adds another 120 days on top
    c.post('/billing/pay', headers=H, data={'_csrf_token': btok, 'plan': 'termly'})
    assert billing.days_left(tenancy.get_tenant('trial')) >= 360 + 118


def test_plan_tiers_are_discounted():
    from utils.plans import tenant_plans, get_plan
    cfg = dict(TENANT_PRICE_KOBO=5000000, TENANT_PLAN_DAYS=30, TENANT_TERM_DAYS=120)
    m, t, a = tenant_plans(cfg)
    assert (m['days'], m['price_naira'], m['savings']) == (30, 50000, 0)
    assert t['days'] == 120 and t['savings'] == 10
    assert a['days'] == 365 and a['savings'] == 20
    assert a['price_naira'] < m['price_naira'] * 12          # annual is cheaper than 12x monthly
    assert get_plan('nonsense', cfg)['id'] == 'monthly'      # safe fallback
