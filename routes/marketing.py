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
    from utils.site_content import get_homepage
    return render_template('marketing/home.html',
                           content=get_homepage(),
                           base_domain=_base_domain(),
                           register_url=url_for('onboarding.register'))


@marketing_bp.route('/home')
def home():
    """Marketing homepage at a fixed path on ANY host — including the owner's
    main domain (e.g. edusyncra.site/home). Lets the homepage be shown on the
    main domain today; a dedicated marketing domain can point at it later."""
    return render_home()


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
