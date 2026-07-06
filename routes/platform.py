"""Platform super-admin dashboard (multi-tenancy).

A cross-school control panel for the SaaS operator: every school, its status and
billing, plus grant-days / suspend / delete actions. It reads the control-plane
registry (not any one school's database).

Access is restricted to a logged-in admin **on the owner school's host** — i.e.
you, on edusyncra.site (the APEX_TENANT). It 404s everywhere else, so a normal
school never sees it.
"""
import datetime as _dt
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, session, abort)

from utils.access_control import is_admin
from utils.tenant_runtime import current_tenant
from utils import tenancy, billing, provisioning

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


def _dt_min():
    return _dt.datetime.min


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
    au = st['access_until']
    return {
        'name': t.name, 'subdomain': t.subdomain, 'status': t.status,
        'plan': st['plan'], 'owner': st['owner'], 'active': st['active'],
        'on_trial': st['on_trial'], 'days_left': st['days_left'],
        'access_until': au.strftime('%d %b %Y') if au else '—',
        'paid_until': t.paid_until.strftime('%d %b %Y') if t.paid_until else '—',
        'admin_email': t.admin_email or '—',
        'created': t.created_at.strftime('%d %b %Y') if t.created_at else '—',
        'created_at': t.created_at,
        # A subscriber whose access lapses within 3 days needs attention.
        'ending_soon': (not st['owner'] and st['active']
                        and st['days_left'] is not None and st['days_left'] <= 3),
        # customer state bucket for filtering/segments
        'bucket': ('owner' if st['owner']
                   else 'suspended' if t.status == 'suspended'
                   else 'trial' if st['on_trial']
                   else 'paying' if (st['active'] and t.status == 'active')
                   else 'unpaid'),
    }


def _rows_and_summary():
    """Shared data for every console page: the school rows plus the roll-up
    numbers (revenue, counts by state)."""
    tenants = tenancy.list_tenants()
    rows = [_row(t) for t in tenants]
    price = (current_app.config.get('TENANT_PRICE_KOBO', 0) or 0) / 100.0
    paying = sum(1 for r in rows if r['bucket'] == 'paying')
    customers = sum(1 for r in rows if not r['owner'])
    summary = {
        'total': len(rows),
        'customers': customers,
        'active': sum(1 for r in rows if r['active'] and r['status'] == 'active'),
        'trial': sum(1 for r in rows if r['bucket'] == 'trial'),
        'paying': paying,
        'blocked': sum(1 for r in rows if r['bucket'] == 'unpaid'),
        'suspended': sum(1 for r in rows if r['status'] == 'suspended'),
        'ending_soon': sum(1 for r in rows if r['ending_soon']),
        'mrr': paying * price,
        'arpa': (paying and (paying * price) / paying) or 0,   # = price when paying>0
    }
    return rows, summary, price


@platform_bp.route('/')
@platform_admin_required
def dashboard():
    """Overview: headline numbers, what needs attention, and recent signups."""
    rows, summary, price = _rows_and_summary()
    attention = [r for r in rows if r['bucket'] == 'unpaid' or r['ending_soon']]
    attention.sort(key=lambda r: (r['bucket'] != 'unpaid', r['days_left'] if r['days_left'] is not None else 999))
    recent = sorted([r for r in rows if not r['owner']],
                    key=lambda r: r['created_at'] or _dt_min(), reverse=True)[:6]
    return render_template('platform/overview.html', active='overview',
                           summary=summary, price=price,
                           attention=attention[:8], recent=recent,
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/schools')
@platform_admin_required
def schools():
    """Full school management: search, per-school actions, bulk actions."""
    rows, summary, price = _rows_and_summary()
    rows.sort(key=lambda r: (r['owner'] is False, r['name'].lower()))
    return render_template('platform/schools.html', active='schools',
                           rows=rows, summary=summary,
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/subscriptions')
@platform_admin_required
def subscriptions():
    """Billing & subscriptions: revenue, who's paying / on trial / lapsed."""
    rows, summary, price = _rows_and_summary()
    customers = [r for r in rows if not r['owner']]
    customers.sort(key=lambda r: ({'unpaid': 0, 'trial': 1, 'paying': 2, 'suspended': 3}.get(r['bucket'], 9),
                                  r['days_left'] if r['days_left'] is not None else 999))
    return render_template('platform/subscriptions.html', active='subscriptions',
                           rows=customers, summary=summary, price=price,
                           period=current_app.config.get('TENANT_PLAN_DAYS'),
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/homepage', methods=['GET', 'POST'])
@platform_admin_required
def homepage():
    """Edit the public marketing homepage content (stored in the control plane).
    Lets the marketing/sales team change copy, pricing and FAQ live — no deploy."""
    from utils import site_content
    if request.method == 'POST':
        content = site_content.get_homepage()
        for k in ('brand', 'hero_title', 'hero_subtitle', 'hero_cta',
                  'trial_note', 'price_period', 'footer'):
            content[k] = (request.form.get(k) or '').strip()
        price = request.form.get('price_naira', type=int)
        content['price_naira'] = price if price else None
        content['features'] = site_content.parse_pairs(
            request.form.get('features'), ('title', 'body'))
        content['steps'] = site_content.parse_pairs(
            request.form.get('steps'), ('title', 'body'))
        content['faqs'] = site_content.parse_pairs(
            request.form.get('faqs'), ('q', 'a'))
        content['testimonials'] = site_content.parse_pairs(
            request.form.get('testimonials'), ('name', 'quote'))
        site_content.save_homepage(content)
        flash('Homepage updated — changes are live.', 'success')
        return redirect(url_for('platform.homepage'))

    content = site_content.get_homepage()
    base = current_app.config.get('TENANT_BASE_DOMAIN', '')
    marketing_url = f'https://www.{base}/' if base else '/'
    return render_template(
        'platform/homepage.html', active='homepage', content=content, marketing_url=marketing_url,
        features_text=site_content.format_pairs(content.get('features'), ('title', 'body')),
        steps_text=site_content.format_pairs(content.get('steps'), ('title', 'body')),
        faqs_text=site_content.format_pairs(content.get('faqs'), ('q', 'a')),
        testimonials_text=site_content.format_pairs(content.get('testimonials'), ('name', 'quote')))


def _back(default='platform.schools'):
    """Return to the page the action was triggered from (Schools or
    Subscriptions), falling back to the schools list."""
    ref = request.referrer or ''
    for ep in ('platform.subscriptions', 'platform.schools', 'platform.dashboard'):
        if url_for(ep) in ref:
            return redirect(ref)
    return redirect(url_for(default))


@platform_bp.route('/<subdomain>/grant', methods=['POST'])
@platform_admin_required
def grant(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    if billing.is_owner(t):
        flash('The owner school is already free forever.', 'info')
        return _back()
    days = request.form.get('days', type=int) or current_app.config.get('TENANT_PLAN_DAYS')
    billing.record_payment(subdomain, days=days)
    flash(f'Granted {days} day(s) to {t.name}.', 'success')
    return _back()


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
    return _back()


@platform_bp.route('/bulk', methods=['POST'])
@platform_admin_required
def bulk():
    """Apply one action to several schools at once (suspend / reactivate /
    delete). The owner school is always skipped."""
    subs = request.form.getlist('subdomains')
    action = request.form.get('action')
    if not subs:
        flash('Select at least one school first.', 'error')
        return _back()
    if action == 'delete' and request.form.get('confirm_delete') != 'yes':
        flash('Tick "confirm delete" to delete the selected schools.', 'error')
        return _back()

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
    return _back()


@platform_bp.route('/<subdomain>/delete', methods=['POST'])
@platform_admin_required
def delete(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None or billing.is_owner(t):
        abort(404)                           # never delete the owner
    if (request.form.get('confirm') or '').strip().lower() != t.subdomain:
        flash('Type the subdomain to confirm deletion.', 'error')
        return _back()
    provisioning.drop_tenant(subdomain, forget=True)   # drop DB + remove registry row
    flash(f'{t.name} and its database were deleted.', 'success')
    return _back()
