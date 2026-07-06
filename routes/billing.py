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
from utils.plans import tenant_plans, get_plan

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
    from utils import tenancy, billing_notify
    if not tenancy.claim_payment(reference, subdomain):
        return False                          # already processed (other path won)
    billing.record_payment(subdomain, days=plan['days'])
    t = tenancy.get_tenant(subdomain)
    base = current_app.config.get('TENANT_BASE_DOMAIN')
    link = f'https://{subdomain}.{base}/' if base else None
    billing_notify.send_receipt(t, plan, until=getattr(t, 'paid_until', None), link=link)
    return True


@billing_bp.route('/')
@login_required
def index():
    t = _tenant_or_404()
    st = billing.status(t)
    return render_template('billing/index.html', t=t, st=st,
                           is_admin=is_admin(),
                           plans=tenant_plans(),
                           test_mode=current_app.config.get('BILLING_TEST_MODE'))


@billing_bp.route('/pay', methods=['POST'])
@login_required
def start_payment():
    t = _tenant_or_404()
    if not is_admin():
        flash('Only an administrator can manage the subscription.', 'error')
        return redirect(url_for('billing.index'))

    plan = get_plan(request.form.get('plan'))     # defaults to Monthly if unknown

    # Dev/testing: apply a simulated payment so the flow can be tested.
    if current_app.config.get('BILLING_TEST_MODE'):
        _credit_and_receipt(t.subdomain, plan)     # no reference in test mode
        flash(f"Test payment applied — {plan['label']} ({plan['days']} days).", 'success')
        return redirect(url_for('main.dashboard'))

    key = current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    amount = plan['price_kobo']
    if not key or not amount:
        flash('Online billing is not configured yet. Please contact support.', 'error')
        return redirect(url_for('billing.index'))
    if not t.admin_email:
        flash('No billing email is on file for this school.', 'error')
        return redirect(url_for('billing.index'))

    import requests
    try:
        resp = requests.post(f'{_PAYSTACK_API}/transaction/initialize', headers=_headers(),
                             json={'email': t.admin_email, 'amount': amount,
                                   'callback_url': url_for('billing.callback', _external=True),
                                   'metadata': {'subdomain': t.subdomain, 'plan': plan['id']}}, timeout=20)
        data = resp.json()
        if data.get('status') and data['data'].get('authorization_url'):
            return redirect(data['data']['authorization_url'])
    except Exception:
        current_app.logger.exception('Paystack init failed for tenant %s', t.subdomain)
    flash('Could not start the payment. Please try again.', 'error')
    return redirect(url_for('billing.index'))


@billing_bp.route('/callback')
@login_required
def callback():
    """Return URL after Paystack checkout: verify the reference, then extend."""
    t = _tenant_or_404()
    reference = request.args.get('reference') or request.args.get('trxref')
    key = current_app.config.get('PLATFORM_PAYSTACK_SECRET_KEY', '')
    if reference and key:
        import requests
        try:
            resp = requests.get(f'{_PAYSTACK_API}/transaction/verify/{reference}',
                                headers=_headers(), timeout=20)
            data = resp.json()
            d = data.get('data') or {}
            if data.get('status') and d.get('status') == 'success' and \
                    (d.get('metadata') or {}).get('subdomain') == t.subdomain:
                plan = get_plan((d.get('metadata') or {}).get('plan'))
                _credit_and_receipt(t.subdomain, plan, reference=reference)
                flash(f"Payment received — {plan['label']} subscription active. Thank you!", 'success')
                return redirect(url_for('main.dashboard'))
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
            plan = get_plan((d.get('metadata') or {}).get('plan'))
            try:
                _credit_and_receipt(sub, plan, reference=d.get('reference'))
            except ValueError:
                pass
    return jsonify(status='ok')
