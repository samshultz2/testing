"""Automatic subscription renewal (Approach B — stored authorization).

When a school pays and opts in, we keep the *reusable* Paystack authorization
returned with the transaction (a token tied to our secret key — never the card
number). The daily job (scripts/billing_cron.py) then charges that saved card a
couple of days before access ends, so the subscription renews without the admin
lifting a finger. If a charge fails, we record the reason and fall back to the
normal reminder/lockout flow, so nothing is ever silently lost.

Two entry points:
  * capture_authorization(subdomain, tx_data) — called from the payment
    callback/webhook to store the card when the admin opted in.
  * charge_due(now) — called by the daily cron to renew everything due.

All of this is context-free (no Flask app needed): it reads Config + env and
talks to Paystack and the control plane directly, like billing_notify does.
"""
from __future__ import annotations

import datetime as _dt

from config import Config

_PAYSTACK_API = 'https://api.paystack.co'


def _now():
    return _dt.datetime.utcnow()


def _truthy(v):
    return str(v).lower() in ('1', 'true', 'yes', 'on')


def capture_authorization(subdomain, tx_data):
    """Store the reusable card authorization from a successful transaction, but
    only if the admin opted into auto-renew (metadata.auto_renew) and the card is
    reusable. Idempotent — safe to call from both the callback and the webhook."""
    if not tx_data:
        return False
    meta = tx_data.get('metadata') or {}
    if not _truthy(meta.get('auto_renew')):
        return False
    auth = tx_data.get('authorization') or {}
    code = auth.get('authorization_code')
    if not code or auth.get('reusable') is False:
        return False                              # card can't be re-charged
    exp = None
    if auth.get('exp_month') and auth.get('exp_year'):
        exp = f"{auth['exp_month']}/{auth['exp_year']}"
    from utils import tenancy
    tenancy.set_autorenew(
        subdomain,
        auto_renew=1,
        renew_plan=(meta.get('plan') or False),
        paystack_auth_code=code,
        card_brand=(auth.get('brand') or auth.get('card_type') or None),
        card_last4=(auth.get('last4') or None),
        card_exp=exp,
        auto_renew_last_error=None,
    )
    return True


def is_due(t, now=None, lead=None):
    """True if this school should be auto-charged now: opted in, has a saved card,
    active status, inside the lead window before access ends, not yet reapable,
    and not already attempted in the last day."""
    from utils import billing
    now = now or _now()
    lead = Config.AUTO_RENEW_LEAD_DAYS if lead is None else lead
    if billing.is_owner(t) or not getattr(t, 'auto_renew', 0):
        return False
    if not getattr(t, 'paystack_auth_code', None) or t.status != 'active':
        return False
    au = billing.access_until(t)
    if au is None:
        return False
    if now < au - _dt.timedelta(days=lead):
        return False                              # too early
    if billing.is_reapable(t):
        return False                              # past retention — let the reaper act
    last = getattr(t, 'auto_renew_last_attempt', None)
    if last and (now - last) < _dt.timedelta(hours=20):
        return False                              # one attempt per day
    return True


def _charge_authorization(secret, email, amount_kobo, auth_code, subdomain, plan_id):
    """POST /transaction/charge_authorization. Returns (ok, data, error)."""
    import requests
    try:
        resp = requests.post(
            f'{_PAYSTACK_API}/transaction/charge_authorization',
            headers={'Authorization': f'Bearer {secret}', 'Content-Type': 'application/json'},
            json={'email': email, 'amount': amount_kobo, 'authorization_code': auth_code,
                  'metadata': {'subdomain': subdomain, 'plan': plan_id, 'auto_renew': '1'}},
            timeout=(8, 25))
        body = resp.json() if resp.content else {}
        data = body.get('data') or {}
        if resp.ok and data.get('status') == 'success':
            return True, data, None
        err = body.get('message') or data.get('gateway_response') or 'charge declined'
        return False, data, err
    except Exception as e:                          # network / timeout / bad JSON
        return False, None, str(e)


def _attempt(t, plan, secret, base, now, charge):
    from utils import tenancy, billing
    sub = t.subdomain
    if not charge:
        return {'subdomain': sub, 'action': 'would-charge', 'plan': plan['id']}
    # Stamp the attempt up front so a crash mid-run can't cause a repeat charge.
    tenancy.set_autorenew(sub, auto_renew_last_attempt=now)
    if not secret or not plan.get('price_kobo') or not t.admin_email:
        tenancy.set_autorenew(sub, auto_renew_last_error='auto-renew not fully configured')
        return {'subdomain': sub, 'action': 'skipped', 'reason': 'not configured'}
    ok, data, err = _charge_authorization(secret, t.admin_email, plan['price_kobo'],
                                          t.paystack_auth_code, sub, plan['id'])
    if ok:
        billing.credit_payment(sub, plan, reference=(data or {}).get('reference'),
                               base_domain=base)
        tenancy.set_autorenew(sub, auto_renew_last_error=None)
        return {'subdomain': sub, 'action': 'charged', 'plan': plan['id']}
    tenancy.set_autorenew(sub, auto_renew_last_error=(err or 'charge failed')[:300])
    return {'subdomain': sub, 'action': 'failed', 'reason': err}


def charge_due(now=None, charge=True):
    """Renew every school whose saved card is due to be charged. Returns a list of
    per-school result dicts. ``charge=False`` reports without charging (dry run)."""
    from utils import tenancy
    from utils.plans import get_plan
    now = now or _now()
    secret = Config.PLATFORM_PAYSTACK_SECRET_KEY
    base = Config.TENANT_BASE_DOMAIN
    results = []
    for t in tenancy.list_tenants():
        if not is_due(t, now):
            continue
        plan = get_plan(getattr(t, 'renew_plan', None) or 'monthly')
        results.append(_attempt(t, plan, secret, base, now, charge))
    return results
