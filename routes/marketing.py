"""Public marketing homepage — served by the app itself (no external host).

On a *platform host* (a reserved subdomain like ``www``/``signup``, or the apex
when no owner school claims it) the bare ``/`` is not a school dashboard, so we
render the marketing homepage there. Its content is editable live from the
platform dashboard (see routes/platform.py), stored in the control-plane DB —
so marketing/sales can change it any time without a code change or redeploy, and
Cloudflare only ever handles DNS.
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   current_app)

from utils.tenant_runtime import current_tenant

marketing_bp = Blueprint('marketing', __name__)


def _base_domain():
    return current_app.config.get('TENANT_BASE_DOMAIN', '') or 'edusyncra.site'


def render_home():
    """Render the marketing homepage from the (editable) stored content."""
    import datetime as _dt
    from utils.site_content import get_homepage
    from utils.plans import tenant_plans
    return render_template('marketing/home.html',
                           content=get_homepage(),
                           plans=tenant_plans(),
                           base_domain=_base_domain(),
                           now_year=_dt.date.today().year,
                           register_url=url_for('onboarding.register'))


@marketing_bp.route('/home')
def home():
    """Marketing homepage at a fixed path on ANY host — including the owner's
    main domain (e.g. edusyncra.site/home). Lets the homepage be shown on the
    main domain today; a dedicated marketing domain can point at it later."""
    return render_home()


# Plain-language summaries of how the platform handles data and subscriptions.
# These are honest overviews (not a substitute for the operator's authoritative
# legal documents) so the marketing footer's Privacy / Terms / Cookie links
# resolve to real, useful pages rather than 404s.
_LEGAL = {
    'privacy': ('Privacy Policy', [
        ('What we store', 'Each school’s records live in an isolated, encrypted '
         'database on its own subdomain. We store only what the school enters to '
         'run its operations, plus the admin account details needed to sign in.'),
        ('How your data is used', 'Data is used solely to provide the service to '
         'your school. We never sell it, and one school’s data is never shared '
         'with another.'),
        ('Backups & retention', 'Databases are backed up daily and encrypted at '
         'rest. When a school closes its account, its data can be exported and is '
         'then removed on request.'),
        ('Your rights', 'School administrators can access, correct and export '
         'their data at any time from within the portal.'),
    ]),
    'terms': ('Terms of Service', [
        ('The service', 'EduSyncra provides a hosted school-management portal on a '
         'subscription basis, including a free trial for new schools.'),
        ('Subscriptions & trial', 'Every new school gets a free trial with no card '
         'required. To continue after the trial, you subscribe to a plan. Plans '
         'renew for the period chosen and can be cancelled at any time.'),
        ('Acceptable use', 'You agree to use the platform lawfully and to keep your '
         'administrator credentials secure. You are responsible for the accuracy '
         'of the data your school enters.'),
        ('Availability', 'We aim for high availability and take regular backups, '
         'but the service is provided “as is”. Planned maintenance is communicated '
         'in advance where possible.'),
    ]),
    'cookies': ('Cookie Policy', [
        ('Essential cookies', 'We use a small number of strictly-necessary cookies '
         'to keep you signed in and to secure forms (for example, CSRF protection).'),
        ('No advertising trackers', 'The portal does not use third-party '
         'advertising or cross-site tracking cookies.'),
        ('Managing cookies', 'You can clear or block cookies in your browser, but '
         'the essential ones are required to sign in and use the portal.'),
    ]),
}


@marketing_bp.route('/legal/<slug>')
def legal(slug):
    """A plain-language legal summary page (privacy / terms / cookies)."""
    from utils.site_content import get_homepage
    entry = _LEGAL.get(slug)
    if not entry:
        return redirect(url_for('marketing.home'))
    import datetime as _dt
    title, sections = entry
    return render_template('marketing/legal.html', title=title, sections=sections,
                           content=get_homepage(), base_domain=_base_domain(),
                           now_year=_dt.date.today().year,
                           register_url=url_for('onboarding.register'))


def serve_marketing_home():
    """before_request hook: on a platform host, the bare homepage is the public
    marketing page rather than the login-gated dashboard. No-op everywhere else
    (single-school mode, real schools, and every non-root path)."""
    if not current_app.config.get('MULTI_TENANT'):
        return None
    if request.method not in ('GET', 'HEAD') or request.endpoint == 'static':
        return None
    if request.path != '/':
        return None
    if current_tenant() is not None:
        return None                      # owner apex or a real school -> their own home
    return render_home()
