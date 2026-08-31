"""Public school onboarding (Stage 3): the browser-facing entry to the automatic
pipeline in utils/onboarding.py.

    GET  /register            → signup form
    POST /register            → record pending school + email a verification link
    GET  /verify/<sub>/<tok>  → verify → AUTO-provision (database + subdomain +
                                admin) and show the login details

These live on the apex/marketing host (no tenant). They only work when
MULTI_TENANT is on — a single-school deployment does not expose registration.
"""
import random

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, abort, jsonify)

from config import Config
from utils import onboarding
from utils.security import login_limiter

onboarding_bp = Blueprint('onboarding', __name__)

# Placeholder examples on the signup form are randomised each load so no single
# (fictional) school is ever singled out. Names are generic and clearly made-up.
_EX_PREFIX = ('Riverside', 'Summit', 'Greenfield', 'Brightstar', 'Oakwood',
              'Crescent', 'Hillcrest', 'Silverstone', 'Unity', 'Cornerstone',
              'Northgate', 'Meadowview', 'Pinnacle', 'Evergreen', 'Harmony',
              'Kingsway', 'Lakeside', 'Highland', 'Fairview', 'Westbrook')
_EX_KIND = ('Academy', 'High School', 'College', 'Schools', 'International School')


def _example_school():
    """A random, obviously-fictional school name + matching subdomain for the
    form placeholders — so the page never shows the same example twice."""
    prefix = random.choice(_EX_PREFIX)
    return f'{prefix} {random.choice(_EX_KIND)}', prefix.lower()


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
    """Render the signup form with the full purchasable grid (capability tier ×
    billing cycle). The school picks a tier (Basic/Premium/Enterprise) and a
    cycle at signup.

    A preselection can arrive from the homepage/pricing page as ?tier= and/or
    ?cycle= (or a combined ?plan=<tier>-<cycle>, or a bare cycle for back-compat);
    it is echoed back so a validation-error re-render keeps the choice."""
    from utils.plans import pricing_grid, PURCHASABLE_TIERS, CYCLE_IDS, DEFAULT_TIER
    grid = pricing_grid()
    vals = request.values
    plan_id = (vals.get('plan') or '').strip().lower()
    sel_tier = (vals.get('tier') or '').strip().lower()
    sel_cycle = (vals.get('cycle') or '').strip().lower()
    if '-' in plan_id:                                  # combined tier-cycle
        pt, pc = plan_id.split('-', 1)
        sel_tier = sel_tier or pt
        sel_cycle = sel_cycle or pc
    elif plan_id in CYCLE_IDS:                          # bare cycle (old links)
        sel_cycle = sel_cycle or plan_id
    if sel_tier not in PURCHASABLE_TIERS:
        sel_tier = 'premium' if any(r['tier'] == 'premium' for r in grid) else \
            (grid[0]['tier'] if grid else DEFAULT_TIER)
    if sel_cycle not in CYCLE_IDS:
        sel_cycle = 'annual'
    price_json = {r['tier']: {c: {'naira': p['price_naira'], 'per': p['per'],
                                  'savings': p['savings']}
                              for c, p in r['plans'].items()} for r in grid}
    example_name, example_sub = _example_school()
    return render_template('onboarding/register.html', grid=grid,
                           sel_tier=sel_tier, sel_cycle=sel_cycle, price_json=price_json,
                           example_name=example_name, example_sub=example_sub, **kw)


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
        from utils.plans import PURCHASABLE_TIERS
        tier = (request.form.get('tier') or '').strip().lower()
        tier = tier if tier in PURCHASABLE_TIERS else None

        # Default: create the school instantly (no email-verification step).
        if cfg.get('REGISTRATION_AUTO_PROVISION', True):
            try:
                tenant, username, password = onboarding.register_and_provision(
                    name, subdomain, email, base_domain=cfg.get('TENANT_BASE_DOMAIN'),
                    tier=tier)
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
            tenant, token = onboarding.request_school(name, subdomain, email, tier=tier)
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
