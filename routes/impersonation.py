"""Secure support impersonation (tenant side).

A platform operator mints a time-boxed grant from the console; the operator is
redirected to the tenant's own host to exchange the one-time token for a
**read-only** support session, marked by an unmistakable banner. Every start and
stop is written to the control-plane audit trail with the real operator's name,
so a support action is never mis-attributed to the school's own staff.

Safety properties enforced here:
  * read-only — any state-changing request during impersonation is blocked;
  * time-boxed — the session self-terminates at the grant's expiry;
  * revocable — a super-admin can end the grant (kill switch) and the next
    request tears the session down;
  * scoped — a token only works on the school it was minted for.
"""
import time

from flask import (Blueprint, request, session, redirect, url_for, flash,
                   render_template, abort)

from utils import tenancy
from utils.tenant_runtime import current_tenant

impersonation_bp = Blueprint('impersonation', __name__)

# Endpoints a read-only support session may still POST to.
_WRITE_ALLOWED = {'impersonation.stop', 'auth.logout'}


def _teardown(message=None, category='info'):
    """Drop the impersonation session entirely (a full logout)."""
    session.clear()
    if message:
        flash(message, category)


@impersonation_bp.before_app_request
def enforce_impersonation():
    """Guard every request made inside a support session: enforce expiry, honour
    a remote kill switch, and keep the session strictly read-only."""
    if not session.get('impersonator'):
        return
    ep = request.endpoint or ''
    if ep == 'static':
        return
    # Expiry (self-terminating).
    exp = session.get('imp_exp') or 0
    if time.time() > exp:
        tenancy.end_impersonation(token=session.get('imp_token'))
        tenancy.log_platform('impersonate_end', subdomain=session.get('imp_sub'),
                             actor=session.get('impersonator'), detail='expired')
        _teardown('The support session has ended (time limit reached).')
        return redirect(url_for('auth.login'))
    # Remote kill switch: the grant was revoked from the console.
    g = tenancy.get_impersonation(token=session.get('imp_token'))
    if g is None or g.ended_at is not None:
        tenancy.log_platform('impersonate_end', subdomain=session.get('imp_sub'),
                             actor=session.get('impersonator'), detail='revoked')
        _teardown('The support session was ended by an administrator.')
        return redirect(url_for('auth.login'))
    # Read-only: block every state-changing request except stopping the session.
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and ep not in _WRITE_ALLOWED:
        abort(403, description='This is a read-only support session — '
                               'changes are not permitted while impersonating.')


@impersonation_bp.app_context_processor
def inject_impersonation():
    """Expose banner details to every template when a support session is live."""
    if not session.get('impersonator'):
        return {}
    exp = session.get('imp_exp') or 0
    return {'impersonation': {
        'actor': session.get('impersonator'),
        'school': session.get('imp_sub'),
        'minutes_left': max(0, int((exp - time.time()) // 60)),
    }}


@impersonation_bp.route('/impersonate/<token>')
def establish(token):
    """Exchange a one-time grant token (on the tenant's own host) for a read-only
    support session as the school's admin."""
    t = current_tenant()
    if t is None:
        abort(404)
    g = tenancy.validate_impersonation(token, t.subdomain)
    if g is None:
        return render_template('impersonation_denied.html'), 403
    from models import User
    # The school's own administrator — the provisioned account is a super_admin;
    # fall back to any active admin.
    admin = (User.query.filter_by(role='super_admin', is_active=True).order_by(User.id).first()
             or User.query.filter_by(role='admin', is_active=True).order_by(User.id).first())
    if admin is None:
        return render_template('impersonation_denied.html',
                               reason='This school has no active administrator to view as.'), 403
    # Establish the session AS the tenant admin, flagged as impersonation.
    session.clear()
    session['logged_in'] = True
    session['user_id'] = admin.id
    session['user'] = admin.full_name or admin.username
    session['username'] = admin.username
    session['role'] = admin.role
    session['tv'] = getattr(admin, 'token_version', 0)
    session['must_change_password'] = False
    session['impersonator'] = g.actor
    session['imp_sub'] = t.subdomain
    session['imp_token'] = g.token
    session['imp_id'] = g.id
    session['imp_exp'] = g.expires_at.timestamp()
    session.permanent = False
    tenancy.log_platform('impersonate_start', subdomain=t.subdomain,
                         actor=g.actor, detail=(g.reason or 'support session'))
    flash('You are now viewing this school as support (read-only).', 'info')
    return redirect('/')


@impersonation_bp.route('/impersonate/stop', methods=['GET', 'POST'])
def stop():
    """End the current support session (operator-initiated)."""
    if session.get('impersonator'):
        tenancy.end_impersonation(token=session.get('imp_token'))
        tenancy.log_platform('impersonate_end', subdomain=session.get('imp_sub'),
                             actor=session.get('impersonator'), detail='stopped by operator')
    _teardown('Support session ended.')
    return redirect(url_for('auth.login'))
