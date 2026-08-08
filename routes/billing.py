"""Per-school subscription billing (multi-tenancy).

A blocked (lapsed) school is locked to these pages by `enforce_billing` until it
pays. Payment is collected into the PLATFORM Paystack account and extends the
school's `paid_until` in the control-plane registry. The owner school never
reaches here (it is exempt).

Test mode (BILLING_TEST_MODE, dev only) applies a simulated payment so the whole
trial -> pay -> access flow can be exercised without a real charge. It is forced
off in production.
"""
import hmac
import hashlib

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, abort, jsonify)

from utils.access_control import login_required, is_admin
from utils.tenant_runtime import current_tenant
from utils import billing
from utils.plans import tenant_plans, get_plan, pricing_grid, CYCLE_IDS

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

_PAYSTACK_API = 'https://api.paystack.co'


def _tenant_or_404():
    t = current_tenant()
    if t is None:
        abort(404)                 # billing only exists in multi-tenant context
    return t


def _headers():
    key = current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}


def _credit_and_receipt(subdomain, plan, reference=None):
    """Credit a successful payment once (deduped by Paystack reference) and email
    a receipt. Safe to call from both the callback and the webhook for one
    payment — the second call is a no-op. Returns True if it credited now."""
    return billing.credit_payment(subdomain, plan, reference=reference,
                                  base_domain=current_app.config.get('TENANT_BASE_DOMAIN'))


def _grant_from_paystack(subdomain, d):
    """Given a genuinely successful Paystack transaction `d`, credit the plan it
    was for — but only if the amount actually paid covers what we asked for.
    Returns the plan dict when value was granted (or already had been), or None
    when the payment was rejected as underpaid. Deduped by reference internally,
    so it's safe from both the callback and the webhook.

    Security: the expected amount is read from the transaction's own metadata
    (`amt`, stamped by us at initialize) — never from the user — so a live price
    change can't reject a legitimate payment, and a partial/underpaid charge can
    never buy a full plan."""
    meta = d.get('metadata') or {}
    plan = get_plan(meta.get('plan'))
    expected = int(meta.get('amt') or plan.get('price_kobo') or 0)
    paid = int(d.get('amount') or 0)
    if expected and paid < expected:
        current_app.logger.warning(
            'Billing: underpaid — %s ref=%s paid=%s expected=%s; not credited.',
            subdomain, d.get('reference'), paid, expected)
        return None
    from utils import autorenew
    autorenew.capture_authorization(subdomain, d)      # only if opted in
    _credit_and_receipt(subdomain, plan, reference=d.get('reference'))
    return plan


@billing_bp.route('/')
@login_required
def index():
    t = _tenant_or_404()
    st = billing.status(t)
    grid = pricing_grid()
    test_mode = current_app.config.get('BILLING_TEST_MODE')
    # Pre-select the school's current tier (what they already trial/pay for), then
    # the most popular, then the first available.
    cur_tier = (getattr(t, 'tier', None) or '').strip().lower()
    sel_tier = next((r['tier'] for r in grid if r['tier'] == cur_tier),
                    next((r['tier'] for r in grid if r['popular']),
                         grid[0]['tier'] if grid else 'basic'))
    sel_cycle = (getattr(t, 'renew_plan', '') or '').split('-')[-1]
    sel_cycle = sel_cycle if sel_cycle in CYCLE_IDS else 'annual'
    price_json = {r['tier']: {c: {'naira': p['price_naira'], 'per': p['per'],
                                  'savings': p['savings'], 'days': p['days']}
                              for c, p in r['plans'].items()} for r in grid}
    # Can a payment actually be started? (Paystack key present AND a plan priced.)
    any_priced = any(p['price_kobo'] for r in grid for p in r['plans'].values())
    payable = test_mode or (bool(current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY'))
                            and any_priced)
    return render_template('billing/index.html', t=t, st=st,
                           is_admin=is_admin(),
                           grid=grid, price_json=price_json,
                           sel_tier=sel_tier, sel_cycle=sel_cycle, payable=payable,
                           lead_days=current_app.config.get('AUTO_RENEW_LEAD_DAYS'),
                           test_mode=test_mode)


@billing_bp.route('/pay', methods=['POST'])
@login_required
def start_payment():
    t = _tenant_or_404()
    if not is_admin():
        flash('Only an administrator can manage the subscription.', 'error')
        return redirect(url_for('billing.index'))

    # A plan is a (tier, cycle) pair. Accept the combined "plan" id or the two
    # fields separately; get_plan() resolves and safely defaults an unknown id.
    plan_id = request.form.get('plan')
    if not plan_id:
        tier = (request.form.get('tier') or '').strip().lower()
        cycle = (request.form.get('cycle') or '').strip().lower()
        plan_id = f'{tier}-{cycle}' if tier and cycle else (tier or cycle)
    plan = get_plan(plan_id)
    auto_renew = request.form.get('auto_renew') == 'on'

    # Dev/testing: apply a simulated payment so the flow can be tested.
    if current_app.config.get('BILLING_TEST_MODE'):
        _credit_and_receipt(t.subdomain, plan)     # no reference in test mode
        if auto_renew:                             # simulate a saved card
            from utils import tenancy
            tenancy.set_autorenew(t.subdomain, auto_renew=1, renew_plan=plan['id'],
                                  paystack_auth_code='AUTH_test', card_brand='visa',
                                  card_last4='4081', card_exp='12/2030',
                                  auto_renew_last_error=None)
        flash(f"Test payment applied — {plan['label']} ({plan['days']} days)."
              + (' Auto-renew on.' if auto_renew else ''), 'success')
        return redirect(url_for('main.dashboard'))

    key = current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    amount = plan['price_kobo']
    if not key:
        current_app.logger.error('Billing: PLATFORM_PAYSTACK_SECRET_KEY is not set.')
        flash('Online billing isn’t set up yet. Please contact support.', 'error')
        return redirect(url_for('billing.index'))
    if not amount:
        current_app.logger.error('Billing: plan %s has no price (set it at /platform → Pricing).', plan['id'])
        flash('This plan isn’t priced yet. Please contact support.', 'error')
        return redirect(url_for('billing.index'))
    if not t.admin_email:
        flash('No billing email is on file for this school.', 'error')
        return redirect(url_for('billing.index'))

    from utils import http
    try:
        resp = http.post_json(f'{_PAYSTACK_API}/transaction/initialize', headers=_headers(),
                              json={'email': t.admin_email, 'amount': amount,
                                    'callback_url': url_for('billing.callback', _external=True),
                                    'metadata': {'subdomain': t.subdomain, 'plan': plan['id'],
                                                 'amt': amount,
                                                 'auto_renew': '1' if auto_renew else '0'}},
                              timeout=20)          # stdlib socket timeout — never hangs forever
        data = resp.json() if resp.content else {}
        if data.get('status') and (data.get('data') or {}).get('authorization_url'):
            # Interstitial page that JS-redirects to Paystack (with a visible
            # fallback link). More robust than a bare 302 across proxies/CSP —
            # a JS navigation isn't a form submission, so form-action can't block it.
            return render_template('billing/redirect.html',
                                   url=data['data']['authorization_url'])
        # Paystack answered but rejected it — surface *why* (bad key, bad amount…).
        msg = data.get('message') or f'Paystack returned HTTP {resp.status_code}'
        current_app.logger.error('Paystack init rejected for %s: %s', t.subdomain, msg)
        flash(f'Could not start the payment: {msg}', 'error')
    except Exception:
        current_app.logger.exception('Paystack init failed for tenant %s', t.subdomain)
        flash('Could not reach Paystack. Check your connection and try again.', 'error')
    return redirect(url_for('billing.index'))


@billing_bp.route('/autorenew', methods=['POST'])
@login_required
def autorenew_toggle():
    """Turn automatic renewal on or off for this school. Turning it on needs a
    saved card (from a previous opt-in payment); the stored card is kept when it's
    turned off, so it can be switched back on without paying again."""
    t = _tenant_or_404()
    if not is_admin():
        flash('Only an administrator can manage the subscription.', 'error')
        return redirect(url_for('billing.index'))
    from utils import tenancy
    want_on = request.form.get('enabled') == 'on'
    if want_on and not getattr(t, 'paystack_auth_code', None):
        flash('No saved card yet. Choose a plan and tick "keep my card for '
              'automatic renewal" at checkout.', 'warning')
        return redirect(url_for('billing.index'))
    fields = {'auto_renew': 1 if want_on else 0}
    plan_id = request.form.get('renew_plan')
    if plan_id:
        fields['renew_plan'] = get_plan(plan_id)['id']       # validated tier id
    tenancy.set_autorenew(t.subdomain, **fields)
    flash('Automatic renewal turned on.' if want_on else 'Automatic renewal turned off.',
          'success')
    return redirect(url_for('billing.index'))


@billing_bp.route('/callback')
@login_required
def callback():
    """Return URL after Paystack checkout: verify the reference, then extend."""
    t = _tenant_or_404()
    reference = request.args.get('reference') or request.args.get('trxref')
    key = current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    if reference and key:
        from utils import http
        try:
            resp = http.get_json(f'{_PAYSTACK_API}/transaction/verify/{reference}',
                                 headers=_headers(), timeout=20)
            data = resp.json()
            d = data.get('data') or {}
            if data.get('status') and d.get('status') == 'success' and \
                    (d.get('metadata') or {}).get('subdomain') == t.subdomain:
                plan = _grant_from_paystack(t.subdomain, d)
                if plan:
                    flash(f"Payment received — {plan['label']} subscription active. Thank you!", 'success')
                    return redirect(url_for('main.dashboard'))
                flash('That payment could not be applied. If you were charged, please contact support.', 'error')
                return redirect(url_for('billing.index'))
        except Exception:
            current_app.logger.exception('Paystack verify failed for tenant %s', t.subdomain)
    flash('We could not confirm that payment yet. If you were charged it will apply shortly.', 'warning')
    return redirect(url_for('billing.index'))


@billing_bp.route('/webhook', methods=['POST'])
def webhook():
    """Paystack server-to-server confirmation (authoritative). Signature-verified
    with the platform secret; extends the school named in the payment metadata."""
    key = current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    if not key:
        return ('', 200)
    body = request.get_data()
    signature = request.headers.get('X-Paystack-Signature', '')
    expected = hmac.new(key.encode(), body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return ('', 400)
    event = request.get_json(silent=True) or {}
    if event.get('event') == 'charge.success':
        d = event.get('data') or {}
        sub = (d.get('metadata') or {}).get('subdomain')
        if sub and (d.get('status') == 'success'):
            try:
                _grant_from_paystack(sub, d)       # verifies amount, dedups, credits
            except ValueError:
                pass
    return jsonify(status='ok')
