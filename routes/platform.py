"""Platform super-admin dashboard (multi-tenancy).

A cross-school control panel for the SaaS operator: every school, its status and
billing, plus grant-days / suspend / delete actions. It reads the control-plane
registry (not any one school's database).

Access is restricted to a logged-in admin **on the owner school's host** — i.e.
you, on edusyncra.site (the APEX_TENANT). It 404s everywhere else, so a normal
school never sees it.
"""
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, session, abort)

from utils.access_control import is_admin
from utils.tenant_runtime import current_tenant
from utils import tenancy, billing, provisioning

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


def platform_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_app.config.get('MULTI_TENANT'):
            abort(404)
        t = current_tenant()
        if t is None or not billing.is_owner(t):
            abort(404)                       # only on the owner school's host
        if not session.get('logged_in') or not is_admin():
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return wrapper


def _row(t):
    st = billing.status(t)
    return {
        'name': t.name, 'subdomain': t.subdomain, 'status': t.status,
        'plan': st['plan'], 'owner': st['owner'], 'active': st['active'],
        'on_trial': st['on_trial'], 'days_left': st['days_left'],
        'access_until': st['access_until'].strftime('%d %b %Y') if st['access_until'] else '—',
        'admin_email': t.admin_email or '—',
        'created': t.created_at.strftime('%d %b %Y') if t.created_at else '—',
    }


@platform_bp.route('/')
@platform_admin_required
def dashboard():
    rows = [_row(t) for t in tenancy.list_tenants()]
    summary = {
        'total': len(rows),
        'active': sum(1 for r in rows if r['active'] and r['status'] == 'active'),
        'trial': sum(1 for r in rows if r['on_trial']),
        'blocked': sum(1 for r in rows if not r['active'] and r['status'] == 'active'),
        'suspended': sum(1 for r in rows if r['status'] == 'suspended'),
    }
    return render_template('platform/dashboard.html', rows=rows, summary=summary,
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/<subdomain>/grant', methods=['POST'])
@platform_admin_required
def grant(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    if billing.is_owner(t):
        flash('The owner school is already free forever.', 'info')
        return redirect(url_for('platform.dashboard'))
    days = request.form.get('days', type=int) or current_app.config.get('TENANT_PLAN_DAYS')
    billing.record_payment(subdomain, days=days)
    flash(f'Granted {days} day(s) to {t.name}.', 'success')
    return redirect(url_for('platform.dashboard'))


@platform_bp.route('/<subdomain>/suspend', methods=['POST'])
@platform_admin_required
def suspend(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None or billing.is_owner(t):
        abort(404)
    if t.status == 'suspended':
        tenancy.set_status(subdomain, 'active')
        flash(f'{t.name} reactivated.', 'success')
    else:
        tenancy.set_status(subdomain, 'suspended', error='suspended by platform admin')
        flash(f'{t.name} suspended — its portal is now unreachable.', 'success')
    return redirect(url_for('platform.dashboard'))


@platform_bp.route('/bulk', methods=['POST'])
@platform_admin_required
def bulk():
    """Apply one action to several schools at once (suspend / reactivate /
    delete). The owner school is always skipped."""
    subs = request.form.getlist('subdomains')
    action = request.form.get('action')
    if not subs:
        flash('Select at least one school first.', 'error')
        return redirect(url_for('platform.dashboard'))
    if action == 'delete' and request.form.get('confirm_delete') != 'yes':
        flash('Tick "confirm delete" to delete the selected schools.', 'error')
        return redirect(url_for('platform.dashboard'))

    done = 0
    for sub in subs:
        t = tenancy.get_tenant(sub)
        if t is None or billing.is_owner(t):
            continue                                   # never touch the owner
        if action == 'suspend':
            tenancy.set_status(sub, 'suspended', error='suspended by platform admin')
            done += 1
        elif action == 'reactivate':
            tenancy.set_status(sub, 'active')
            done += 1
        elif action == 'delete':
            provisioning.drop_tenant(sub, forget=True)
            done += 1
    flash(f'{(action or "").title()} applied to {done} school(s).', 'success')
    return redirect(url_for('platform.dashboard'))


@platform_bp.route('/<subdomain>/delete', methods=['POST'])
@platform_admin_required
def delete(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None or billing.is_owner(t):
        abort(404)                           # never delete the owner
    if (request.form.get('confirm') or '').strip().lower() != t.subdomain:
        flash('Type the subdomain to confirm deletion.', 'error')
        return redirect(url_for('platform.dashboard'))
    provisioning.drop_tenant(subdomain, forget=True)   # drop DB + remove registry row
    flash(f'{t.name} and its database were deleted.', 'success')
    return redirect(url_for('platform.dashboard'))
