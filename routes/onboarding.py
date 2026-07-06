"""Public school onboarding (Stage 3): the browser-facing entry to the automatic
pipeline in utils/onboarding.py.

    GET  /register            → signup form
    POST /register            → record pending school + email a verification link
    GET  /verify/<sub>/<tok>  → verify → AUTO-provision (database + subdomain +
                                admin) and show the login details

These live on the apex/marketing host (no tenant). They only work when
MULTI_TENANT is on — a single-school deployment does not expose registration.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, abort)

from config import Config
from utils import onboarding
from utils.security import login_limiter

onboarding_bp = Blueprint('onboarding', __name__)


def _require_mt():
    if not current_app.config.get('MULTI_TENANT'):
        abort(404)


@onboarding_bp.route('/register', methods=['GET', 'POST'])
def register():
    _require_mt()
    if request.method == 'POST':
        # Throttle signups per IP — provisioning is expensive and abusable.
        rkey = 'school_register:' + (request.remote_addr or 'unknown')
        if login_limiter.is_rate_limited(rkey, max_attempts=5, window_minutes=60):
            flash('Too many registration attempts. Please try again later.', 'error')
            return render_template('onboarding/register.html')
        login_limiter.record_attempt(rkey)

        name = (request.form.get('name') or '').strip()
        subdomain = (request.form.get('subdomain') or '').strip().lower()
        email = (request.form.get('admin_email') or '').strip()
        try:
            tenant, token = onboarding.request_school(name, subdomain, email)
        except ValueError as e:
            flash(str(e), 'error')
            return render_template('onboarding/register.html',
                                   name=name, subdomain=subdomain, admin_email=email)

        verify_url = url_for('onboarding.verify', subdomain=subdomain, token=token,
                             _external=True)
        emailed = onboarding.send_verification_email(tenant, token, verify_url)
        # In dev (no mail configured) show the link so the flow is testable.
        dev_link = None if emailed else verify_url
        return render_template('onboarding/sent.html', email=email, dev_link=dev_link)

    return render_template('onboarding/register.html')


@onboarding_bp.route('/verify/<subdomain>/<token>')
def verify(subdomain, token):
    _require_mt()
    try:
        tenant, username, password = onboarding.verify_and_provision(
            subdomain, token, base_domain=Config.TENANT_BASE_DOMAIN)
    except ValueError as e:
        return render_template('onboarding/done.html', error=str(e)), 400

    base = Config.TENANT_BASE_DOMAIN
    login_url = f'https://{tenant.subdomain}.{base}/' if base else None
    # The password was emailed; only show it inline when mail isn't configured (dev).
    from utils import mailer
    show_pw = not mailer.is_configured()
    return render_template('onboarding/done.html', tenant=tenant, login_url=login_url,
                           username=username, password=(password if show_pw else None))
