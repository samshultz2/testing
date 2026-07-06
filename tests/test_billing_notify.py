"""Billing lifecycle reminder emails: the right notice fires at the right time,
once per stage, and resets on payment."""
import datetime as dt
import types
import pytest

from utils import billing_notify


def _t(**kw):
    base = dict(name='Acme', subdomain='acme', admin_email='head@acme.test',
                status='active', plan='standard', trial_ends_at=None, paid_until=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _in(days):
    return dt.datetime.utcnow() + dt.timedelta(days=days)


def test_trial_ending_fires_one_day_before():
    t = _t(trial_ends_at=_in(0.4))          # ~10h left -> within 1 day
    assert billing_notify.due_notice(t) == 'trial_ending'
    t2 = _t(trial_ends_at=_in(3))           # 3 days left -> nothing yet
    assert billing_notify.due_notice(t2) is None


def test_subscription_reminders():
    assert billing_notify.due_notice(_t(paid_until=_in(6))) == 'sub_7d'
    assert billing_notify.due_notice(_t(paid_until=_in(0.5))) == 'sub_1d'
    assert billing_notify.due_notice(_t(paid_until=_in(20))) is None


def test_lapsed_and_purge_warning():
    # locked out (past the 1-day soft grace) -> "renew to restore" reminder
    assert billing_notify.due_notice(_t(paid_until=_in(-2))) == 'lapsed'
    # still in the soft grace (portal works) -> no lockout email yet
    assert billing_notify.due_notice(_t(paid_until=_in(-0.2))) is None
    # 1 day before the retention grace ends -> final purge warning
    assert billing_notify.due_notice(_t(paid_until=_in(-7.5))) == 'purge_soon'
    # past grace -> no email (the reaper takes over)
    assert billing_notify.due_notice(_t(paid_until=_in(-30))) is None


def test_owner_is_never_notified():
    assert billing_notify.due_notice(_t(plan='owner', paid_until=_in(-2))) is None


@pytest.fixture()
def cp(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy
    tenancy._reset_engine()
    tenancy.init_control_plane()
    yield tenancy
    tenancy._reset_engine()


def test_claim_payment_dedupes(cp):
    assert cp.claim_payment('ref_123', 'acme') is True
    assert cp.claim_payment('ref_123', 'acme') is False    # already processed -> no double credit
    assert cp.claim_payment('ref_456') is True             # a different reference is new
    assert cp.claim_payment(None) is True                  # no reference (test mode) -> never deduped
    assert cp.claim_payment(None) is True


def test_receipt_email_is_built_and_sent(monkeypatch):
    from utils.plans import get_plan
    box = []
    monkeypatch.setattr('utils.mailer.send_email',
                        lambda to, subj, body, html=None: box.append((to, subj, body)))
    plan = get_plan('annual', dict(TENANT_PRICE_KOBO=5000000, TENANT_PLAN_DAYS=30, TENANT_TERM_DAYS=120))
    t = _t(paid_until=dt.datetime.utcnow() + dt.timedelta(days=365))
    assert billing_notify.send_receipt(t, plan, until=t.paid_until, link='https://acme.test/') is True
    assert box and 'Payment received' in box[0][1] and 'Annual' in box[0][1]


def test_run_notifications_is_idempotent_per_stage(cp, monkeypatch):
    from utils import provisioning, billing
    cp.register_tenant('Trial Co', 'trialco', 'head@trialco.test')
    provisioning.provision('trialco')
    # put it one day from trial end
    cp.set_billing('trialco', trial_ends_at=dt.datetime.utcnow() + dt.timedelta(hours=6))

    sent_box = []
    monkeypatch.setattr('utils.mailer.send_email',
                        lambda to, subj, body, html=None: sent_box.append((to, subj)))

    first = billing_notify.run_notifications()
    assert ('trialco', 'trial_ending') in first
    assert len(sent_box) == 1
    # re-running the same day sends nothing new
    assert billing_notify.run_notifications() == []
    assert len(sent_box) == 1
    # marker recorded
    assert cp.get_notice('trialco') == 'trial_ending'

    # paying clears the notice state so a later cycle can remind again
    billing.record_payment('trialco', days=30)
    assert cp.get_notice('trialco') is None
