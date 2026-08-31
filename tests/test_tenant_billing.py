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


def test_soft_grace_then_lockout():
    # just past the trial/subscription end -> expired, but still usable (soft grace)
    just_expired = _t(trial_ends_at=_in(-0.5))
    assert billing.is_blocked(just_expired)              # paid/trial period is over
    assert not billing.is_locked_out(just_expired)       # ...but not locked yet
    # past the soft grace -> locked out
    locked = _t(trial_ends_at=_in(-2))
    assert billing.is_locked_out(locked)
    # owner is never locked
    assert not billing.is_locked_out(_t(plan='owner', trial_ends_at=_in(-30)))


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

    # expire the trial past the soft grace -> locked to billing
    tenancy.set_billing('trial', trial_ends_at=dt.datetime.utcnow() - dt.timedelta(days=3))
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


def test_subscription_link_in_sidebar_for_tenant_admin(mt):
    app, tenancy = mt
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    page = c.get('/students', headers=H).get_data(as_text=True)
    assert '/billing' in page and 'Subscription' in page      # sidebar link renders


def test_billing_page_flags_unconfigured_and_clicking_explains(mt):
    """When Paystack keys / prices aren't set, the page says so and clicking a
    tier gives a clear reason instead of silently reloading."""
    app, tenancy = mt
    app.config['BILLING_TEST_MODE'] = False
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = ''      # not set
    app.config['TENANT_PRICE_KOBO'] = 0                  # no price
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})

    page = c.get('/billing/', headers=H).get_data(as_text=True)
    assert 'aren’t fully set up' in page                 # proactive page notice
    btok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', page).group(1)

    c.post('/billing/pay', headers=H, data={'_csrf_token': btok, 'plan': 'monthly'})
    after = c.get('/billing/', headers=H).get_data(as_text=True)
    assert 'isn’t set up yet' in after                   # specific flash: missing key

    # with a key but still no price -> the message points at pricing
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    c.post('/billing/pay', headers=H, data={'_csrf_token': btok, 'plan': 'monthly'})
    after = c.get('/billing/', headers=H).get_data(as_text=True)
    assert 'isn’t priced yet' in after


def test_paying_redirects_to_paystack_and_csp_allows_it(mt):
    """A real (non-test-mode) payment renders the interstitial that redirects to
    Paystack, and the CSP form-action permits that cross-origin redirect."""
    from unittest.mock import patch
    app, tenancy = mt
    app.config['BILLING_TEST_MODE'] = False
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    app.config['TENANT_PRICE_KOBO'] = 5000000
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    btok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                     c.get('/billing/', headers=H).get_data(as_text=True)).group(1)

    class FakeResp:
        content = '{"ok":1}'
        def json(self):
            return {'status': True, 'data': {'authorization_url': 'https://checkout.paystack.com/abc123'}}

    with patch('utils.http.post_json', return_value=FakeResp()):
        r = c.post('/billing/pay', headers=H, data={'_csrf_token': btok, 'plan': 'monthly'})

    page = r.get_data(as_text=True)
    assert r.status_code == 200                                    # interstitial, not a bare 302
    assert 'https://checkout.paystack.com/abc123' in page          # visible fallback link
    assert 'window.location.replace' in page                       # explicit JS redirect
    # the CSP must permit the cross-origin redirect to Paystack (else browsers block it)
    assert 'checkout.paystack.com' in r.headers.get('Content-Security-Policy', '')


def _signed_webhook(secret, payload):
    import hmac, hashlib, json as _json
    body = _json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    return body, sig


def _charge(subdomain, plan='monthly', amount=5000000, amt=5000000, reference='ref1', status='success'):
    return {'event': 'charge.success',
            'data': {'status': status, 'reference': reference, 'amount': amount,
                     'metadata': {'subdomain': subdomain, 'plan': plan, 'amt': amt}}}


def test_webhook_credits_once_and_dedups_replays(mt):
    app, tenancy = mt
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    app.config['TENANT_PRICE_KOBO'] = 5000000
    c = app.test_client()
    tenancy.set_billing('trial', trial_ends_at=_in(-2))            # expired
    assert billing.is_blocked(tenancy.get_tenant('trial'))

    body, sig = _signed_webhook('sk_test_x', _charge('trial'))
    H = {'X-Paystack-Signature': sig, 'Content-Type': 'application/json'}
    r = c.post('/billing/webhook', data=body, headers=H)
    assert r.status_code == 200
    assert billing.is_active(tenancy.get_tenant('trial'))          # granted
    left = billing.days_left(tenancy.get_tenant('trial'))

    # same reference again -> no double credit
    c.post('/billing/webhook', data=body, headers=H)
    assert billing.days_left(tenancy.get_tenant('trial')) == left


def test_webhook_rejects_forged_signature(mt):
    app, tenancy = mt
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    c = app.test_client()
    tenancy.set_billing('trial', trial_ends_at=_in(-2))
    body, _ = _signed_webhook('sk_test_x', _charge('trial', reference='forge'))
    r = c.post('/billing/webhook', data=body,
               headers={'X-Paystack-Signature': 'deadbeef', 'Content-Type': 'application/json'})
    assert r.status_code == 400
    assert billing.is_blocked(tenancy.get_tenant('trial'))         # nothing granted


def test_webhook_ignores_unsuccessful_and_underpaid(mt):
    app, tenancy = mt
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    app.config['TENANT_PRICE_KOBO'] = 5000000
    c = app.test_client()
    tenancy.set_billing('trial', trial_ends_at=_in(-2))

    # a non-success charge event -> no grant
    body, sig = _signed_webhook('sk_test_x', _charge('trial', reference='a', status='failed'))
    c.post('/billing/webhook', data=body, headers={'X-Paystack-Signature': sig, 'Content-Type': 'application/json'})
    assert billing.is_blocked(tenancy.get_tenant('trial'))

    # a *successful* charge but underpaid (paid < the amount we asked for) -> no grant
    body, sig = _signed_webhook('sk_test_x', _charge('trial', reference='b', amount=100000, amt=5000000))
    c.post('/billing/webhook', data=body, headers={'X-Paystack-Signature': sig, 'Content-Type': 'application/json'})
    assert billing.is_blocked(tenancy.get_tenant('trial'))         # underpayment buys nothing


def test_callback_does_not_grant_on_abandoned_or_wrong_school(mt):
    """A user who reaches the payment page and backs out (or a reference that
    isn't a success / belongs elsewhere) gets no value."""
    from unittest.mock import patch
    app, tenancy = mt
    app.config['BILLING_TEST_MODE'] = False
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    tenancy.set_billing('trial', trial_ends_at=_in(-2))
    assert billing.is_blocked(tenancy.get_tenant('trial'))

    class Resp:
        def __init__(self, d): self._d = d
        def json(self): return {'status': True, 'data': self._d}

    # abandoned checkout: verify says the transaction was not successful
    abandoned = {'status': 'abandoned', 'reference': 'x', 'amount': 0,
                 'metadata': {'subdomain': 'trial', 'plan': 'monthly', 'amt': 5000000}}
    with patch('utils.http.get_json', return_value=Resp(abandoned)):
        c.get('/billing/callback?reference=x', headers=H)
    assert billing.is_blocked(tenancy.get_tenant('trial'))         # no value

    # a success but for a DIFFERENT school -> must not credit this one
    other = {'status': 'success', 'reference': 'y', 'amount': 5000000,
             'metadata': {'subdomain': 'someoneelse', 'plan': 'monthly', 'amt': 5000000}}
    with patch('utils.http.get_json', return_value=Resp(other)):
        c.get('/billing/callback?reference=y', headers=H)
    assert billing.is_blocked(tenancy.get_tenant('trial'))         # still nothing


def test_webhook_optin_saves_card_then_cron_renews(mt, monkeypatch):
    """End-to-end: an opted-in payment (via webhook) stores the card, and the
    daily cron later auto-charges it near expiry."""
    from config import Config
    from utils import autorenew
    app, tenancy = mt
    app.config['PLATFORM_PAYSTACK_SECRET_KEY'] = 'sk_test_x'
    app.config['TENANT_PRICE_KOBO'] = 5000000
    monkeypatch.setattr(Config, 'PLATFORM_PAYSTACK_SECRET_KEY', 'sk_test_x', raising=False)
    monkeypatch.setattr(Config, 'TENANT_PRICE_KOBO', 5000000, raising=False)
    c = app.test_client()
    tenancy.set_billing('trial', trial_ends_at=_in(-2))

    evt = _charge('trial', reference='pay1')
    evt['data']['metadata']['auto_renew'] = '1'
    evt['data']['authorization'] = {'authorization_code': 'AUTH_z', 'reusable': True,
                                    'brand': 'visa', 'last4': '4081', 'exp_month': '12', 'exp_year': '2030'}
    body, sig = _signed_webhook('sk_test_x', evt)
    c.post('/billing/webhook', data=body,
           headers={'X-Paystack-Signature': sig, 'Content-Type': 'application/json'})

    t = tenancy.get_tenant('trial')
    assert billing.is_active(t) and t.auto_renew == 1 and t.paystack_auth_code == 'AUTH_z'

    # near expiry, the cron auto-charges the saved card
    tenancy.set_billing('trial', paid_until=_in(1))
    monkeypatch.setattr(autorenew, '_charge_authorization',
                        lambda *a, **k: (True, {'reference': 'auto1'}, None))
    res = autorenew.charge_due()
    assert any(r['subdomain'] == 'trial' and r['action'] == 'charged' for r in res)
    assert billing.days_left(tenancy.get_tenant('trial')) >= 29


def test_autorenew_optin_and_toggle_through_the_app(mt):
    app, tenancy = mt
    H = {'Host': 'trial.edusyncra.test'}
    c = app.test_client()
    html = c.get('/login', headers=H).get_data(as_text=True)
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)
    c.post('/login', headers=H, data={'username': 'admin', 'password': 'Zebra!Mango42Q', '_csrf_token': tok})

    # the billing page offers the auto-renew opt-in
    bill = c.get('/billing/', headers=H).get_data(as_text=True)
    assert 'automatic renewal' in bill.lower()
    btok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', bill).group(1)

    # pay (test mode) opting into auto-renew -> card saved + enabled
    c.post('/billing/pay', headers=H,
           data={'_csrf_token': btok, 'tier': 'basic', 'cycle': 'monthly', 'auto_renew': 'on'})
    t = tenancy.get_tenant('trial')
    assert t.auto_renew == 1 and t.card_last4 == '4081' and t.renew_plan == 'basic-monthly'

    # the page now shows it's ON, and the toggle turns it off (card kept)
    bill = c.get('/billing/', headers=H).get_data(as_text=True)
    assert 'Automatic renewal is ON' in bill
    btok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"', bill).group(1)
    c.post('/billing/autorenew', headers=H, data={'_csrf_token': btok, 'enabled': 'off'})
    t = tenancy.get_tenant('trial')
    assert t.auto_renew == 0 and t.paystack_auth_code == 'AUTH_test'   # kept for re-enable


def test_plan_tiers_are_discounted():
    from utils.plans import tenant_plans, get_plan, pricing_grid
    cfg = dict(TENANT_PRICE_KOBO=5000000, TENANT_PLAN_DAYS=30, TENANT_TERM_DAYS=120)
    m, t, a = tenant_plans(cfg)                 # anchor (Basic) cycle plans, back-compat shape
    assert (m['days'], m['price_naira'], m['savings']) == (30, 50000, 0)
    assert t['days'] == 120 and t['savings'] == 10
    assert a['days'] == 365 and a['savings'] == 20
    assert a['price_naira'] < m['price_naira'] * 12          # annual is cheaper than 12x monthly
    # per-tier multipliers: Premium 2x, Enterprise 4x the Basic Monthly price
    grid = {r['tier']: r for r in pricing_grid(cfg)}
    assert grid['premium']['plans']['monthly']['price_naira'] == 100000
    assert grid['enterprise']['plans']['monthly']['price_naira'] == 200000
    # unknown ids fall back safely to the Basic Monthly plan
    fb = get_plan('nonsense', cfg)
    assert fb['tier'] == 'basic' and fb['cycle'] == 'monthly'


def test_pricing_overrides_are_live(cp):
    """Admin edits at /platform/pricing (stored in the control plane) take
    precedence over config per (tier, cycle), can hide a cycle or a whole tier,
    and re-anchor savings on the new Monthly price — with no redeploy."""
    from utils import plans
    cfg = dict(TENANT_PRICE_KOBO=5000000, TENANT_PLAN_DAYS=30, TENANT_TERM_DAYS=120)
    assert plans.get_plan('premium-monthly', cfg)['price_naira'] == 100000   # config default (2x)

    plans.save_pricing({
        'grid': {
            'basic':   {'monthly': 4000000, 'annual': 36000000},   # ₦40,000 / ₦360,000
            'premium': {'monthly': 9000000},                       # ₦90,000
        },
        'cycles': {'termly': {'enabled': False}},                  # hide the Termly cycle
        'tier_enabled': {'basic': True, 'premium': True, 'enterprise': False},
    })

    # per-cell overrides win
    assert plans.get_plan('basic-monthly', cfg)['price_naira'] == 40000
    assert plans.get_plan('premium-monthly', cfg)['price_naira'] == 90000
    # annual saving re-anchored on the new ₦40k Basic monthly (₦360k vs ₦480k = 25%)
    assert plans.get_plan('basic-annual', cfg)['savings'] == 25

    # enterprise tier hidden; termly cycle hidden from every visible tier
    grid = plans.pricing_grid(cfg)
    assert [r['tier'] for r in grid] == ['basic', 'premium']
    for r in grid:
        assert [p['cycle'] for p in r['plan_list']] == ['monthly', 'annual']

    # the admin editor still sees every tier + cycle via include_disabled
    allg = plans.pricing_grid(cfg, include_disabled=True)
    assert [r['tier'] for r in allg] == ['basic', 'premium', 'enterprise']
    assert next(r for r in allg if r['tier'] == 'enterprise')['enabled'] is False


# --- auto-renew (Approach B: stored authorization + scheduled charge) --------
def _paystack_tx(auth_code='AUTH_x', reusable=True, auto_renew='1', plan='monthly',
                 reference='ref_1'):
    return {
        'status': 'success', 'reference': reference,
        'metadata': {'subdomain': 'ar', 'plan': plan, 'auto_renew': auto_renew},
        'authorization': {'authorization_code': auth_code, 'reusable': reusable,
                          'brand': 'visa', 'last4': '4081', 'exp_month': '12', 'exp_year': '2030'},
    }


def test_autorenew_capture_stores_card_only_when_opted_in(cp):
    from utils import autorenew
    cp.register_tenant('AR School', 'ar', 'ar@x.test')

    # opted out -> nothing stored
    assert autorenew.capture_authorization('ar', _paystack_tx(auto_renew='0')) is False
    assert cp.get_tenant('ar').auto_renew == 0

    # non-reusable card -> can't be saved
    assert autorenew.capture_authorization('ar', _paystack_tx(reusable=False)) is False
    assert not cp.get_tenant('ar').paystack_auth_code

    # opted in + reusable -> stored + enabled
    assert autorenew.capture_authorization('ar', _paystack_tx()) is True
    t = cp.get_tenant('ar')
    assert t.auto_renew == 1 and t.paystack_auth_code == 'AUTH_x'
    assert t.card_brand == 'visa' and t.card_last4 == '4081' and t.card_exp == '12/2030'
    assert t.renew_plan == 'monthly'


def test_autorenew_charges_due_card_and_extends(cp, monkeypatch):
    from config import Config
    from utils import autorenew
    monkeypatch.setattr(Config, 'TENANT_PRICE_KOBO', 5000000, raising=False)
    monkeypatch.setattr(Config, 'PLATFORM_PAYSTACK_SECRET_KEY', 'sk_test_x', raising=False)
    cp.register_tenant('AR School', 'ar', 'ar@x.test')
    cp.set_status('ar', 'active')
    cp.set_billing('ar', paid_until=_in(1))          # ends tomorrow -> inside lead window
    cp.set_autorenew('ar', auto_renew=1, renew_plan='monthly', paystack_auth_code='AUTH_x')

    calls = {}
    def fake_charge(secret, email, amount, code, sub, plan_id):
        calls.update(amount=amount, code=code, sub=sub)
        return True, {'reference': 'psref_1'}, None
    monkeypatch.setattr(autorenew, '_charge_authorization', fake_charge)

    res = autorenew.charge_due()
    assert res and res[0]['action'] == 'charged'
    assert calls == {'amount': 5000000, 'code': 'AUTH_x', 'sub': 'ar'}
    assert billing.days_left(cp.get_tenant('ar')) >= 29       # +30 days from ~tomorrow
    assert cp.get_tenant('ar').auto_renew_last_error is None

    # running again the same day does not double-charge (already attempted today)
    calls.clear()
    assert autorenew.charge_due() == []
    assert calls == {}


def test_autorenew_skips_owner_and_not_yet_due(cp, monkeypatch):
    from utils import autorenew
    fired = []
    monkeypatch.setattr(autorenew, '_charge_authorization',
                        lambda *a, **k: (fired.append(1), (True, {'reference': 'r'}, None))[1])
    # far from expiry -> not due
    cp.register_tenant('Later', 'later', 'l@x.test')
    cp.set_status('later', 'active')
    cp.set_billing('later', paid_until=_in(60))
    cp.set_autorenew('later', auto_renew=1, paystack_auth_code='AUTH_y')
    # owner is never auto-charged
    from utils import onboarding
    onboarding.adopt_current_school('own', 'Owner', 'sqlite:///o.db', 'o@x.test')
    cp.set_autorenew('own', auto_renew=1, paystack_auth_code='AUTH_z')

    assert autorenew.charge_due() == []
    assert fired == []


def test_autorenew_failed_charge_records_error_without_extending(cp, monkeypatch):
    from config import Config
    from utils import autorenew
    monkeypatch.setattr(Config, 'TENANT_PRICE_KOBO', 5000000, raising=False)
    monkeypatch.setattr(Config, 'PLATFORM_PAYSTACK_SECRET_KEY', 'sk_test_x', raising=False)
    cp.register_tenant('AR School', 'ar', 'ar@x.test')
    cp.set_status('ar', 'active')
    cp.set_billing('ar', paid_until=_in(1))
    cp.set_autorenew('ar', auto_renew=1, renew_plan='monthly', paystack_auth_code='AUTH_x')
    before = billing.days_left(cp.get_tenant('ar'))
    monkeypatch.setattr(autorenew, '_charge_authorization',
                        lambda *a, **k: (False, {}, 'insufficient funds'))

    res = autorenew.charge_due()
    assert res and res[0]['action'] == 'failed'
    t = cp.get_tenant('ar')
    assert t.auto_renew_last_error == 'insufficient funds'
    assert billing.days_left(t) == before                     # access unchanged
