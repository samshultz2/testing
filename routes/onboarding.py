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
                   flash, current_app, abort, jsonify)

from config import Config
from utils import onboarding
from utils.security import login_limiter

onboarding_bp = Blueprint('onboarding', __name__)


@onboarding_bp.route('/register/check')
def check_subdomain():
    """Live availability check for the registration form. Returns
    {available: bool, reason: str} for the given ?subdomain=."""
    _require_mt()
    from utils.tenancy import VALID_SUBDOMAIN, get_tenant
    sub = (request.args.get('subdomain') or '').strip().lower()
    reserved = current_app.config.get('RESERVED_SUBDOMAINS', set())
    apex = (current_app.config.get('APEX_TENANT') or '').lower()
    if not sub:
        return jsonify(available=False, reason='')
    if len(sub) < 3:
        return jsonify(available=False, reason='At least 3 characters.')
    if not VALID_SUBDOMAIN.match(sub):
        return jsonify(available=False, reason='Only lowercase letters, digits and hyphens.')
    if sub in reserved or sub == apex:
        return jsonify(available=False, reason='That address is reserved.')
    if get_tenant(sub) is not None:
        return jsonify(available=False, reason='Already taken — try another.')
    return jsonify(available=True, reason='Available')


def _require_mt():
    if not current_app.config.get('MULTI_TENANT'):
        abort(404)


def _render_register(**kw):
    """Render the signup form with the current subscription tiers available.

    The plan the visitor clicked on the homepage/pricing page arrives as a
    ?plan=<id> query param (and is echoed back via a hidden field on POST so a
    validation-error re-render keeps it). We surface that exact tier in the
    "Your plan" card instead of always showing the Monthly tier."""
    from utils.plans import tenant_plans
    plans = tenant_plans()
    plan_id = (request.values.get('plan') or '').strip().lower()
    selected = next((p for p in plans if p['id'] == plan_id), None)
    return render_template('onboarding/register.html', plans=plans,
                           selected_plan=selected, **kw)


def _registration_blocked(ip):
    """Per-IP rate limit + daily ban on signups (provisioning is expensive and
    abusable). Returns a message if blocked, else None (and records the attempt)."""
    cfg = current_app.config
    if login_limiter.is_rate_limited(f'reg_ban:{ip}', cfg['REGISTRATION_MAX_PER_DAY'], 24 * 60):
        return 'Too many registrations from your network today. Please try again tomorrow.'
    if login_limiter.is_rate_limited(f'reg_hour:{ip}', cfg['REGISTRATION_MAX_PER_HOUR'], 60):
        return 'Please wait a little before registering another school.'
    # Count the attempt against both windows BEFORE provisioning, so failures and
    # retries still count toward the limit.
    login_limiter.record_attempt(f'reg_hour:{ip}')
    login_limiter.record_attempt(f'reg_ban:{ip}')
    return None


@onboarding_bp.route('/register', methods=['GET', 'POST'])
def register():
    _require_mt()
    if request.method == 'POST':
        ip = request.remote_addr or 'unknown'
        blocked = _registration_blocked(ip)
        if blocked:
            flash(blocked, 'error')
            return _render_register(), 429

        cfg = current_app.config
        name = (request.form.get('name') or '').strip()
        subdomain = (request.form.get('subdomain') or '').strip().lower()
        email = (request.form.get('admin_email') or '').strip()

        # Default: create the school instantly (no email-verification step).
        if cfg.get('REGISTRATION_AUTO_PROVISION', True):
            try:
                tenant, username, password = onboarding.register_and_provision(
                    name, subdomain, email, base_domain=cfg.get('TENANT_BASE_DOMAIN'))
            except ValueError as e:
                flash(str(e), 'error')
                return _render_register(name=name, subdomain=subdomain, admin_email=email)
            except Exception:
                current_app.logger.exception('instant provisioning failed for %s', subdomain)
                flash('We could not set up your school just now. Please try again.', 'error')
                return _render_register(name=name, subdomain=subdomain, admin_email=email)
            from utils import mailer
            base = cfg.get('TENANT_BASE_DOMAIN')
            login_url = f'https://{tenant.subdomain}.{base}/' if base else None
            show_pw = not mailer.is_configured()
            return render_template('onboarding/done.html', tenant=tenant, login_url=login_url,
                                   username=username, password=(password if show_pw else None),
                                   trial_days=cfg.get('TENANT_TRIAL_DAYS'))

        # Opt-in: require an email-verification link before creating the database.
        try:
            tenant, token = onboarding.request_school(name, subdomain, email)
        except ValueError as e:
            flash(str(e), 'error')
            return _render_register(name=name, subdomain=subdomain, admin_email=email)
        verify_url = url_for('onboarding.verify', subdomain=subdomain, token=token, _external=True)
        emailed = onboarding.send_verification_email(tenant, token, verify_url)
        return render_template('onboarding/sent.html', email=email,
                               dev_link=(None if emailed else verify_url))

    return _render_register()


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
