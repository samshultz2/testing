"""Platform super-admin dashboard (multi-tenancy).

A cross-school control panel for the SaaS operator: every school, its status and
billing, plus grant-days / suspend / delete actions. It reads the control-plane
registry (not any one school's database).

Access is restricted to a logged-in admin **on the owner school's host** — i.e.
you, on edusyncra.site (the APEX_TENANT). It 404s everywhere else, so a normal
school never sees it.
"""
import datetime as _dt
from utils.web_exports import csv_response
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, session, abort)

from utils.access_control import is_admin
from utils.tenant_runtime import current_tenant
from utils import tenancy, billing, provisioning

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


def _dt_min():
    return _dt.datetime.min


def _platform_gate():
    """Shared access check: must be an admin logged in on the owner school's
    host. Returns a response to short-circuit with, or None to proceed."""
    if not current_app.config.get('MULTI_TENANT'):
        abort(404)
    t = current_tenant()
    if t is None or not billing.is_owner(t):
        abort(404)                           # only on the owner school's host
    if not session.get('logged_in') or not is_admin():
        return redirect(url_for('auth.login'))
    return None


def platform_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        gated = _platform_gate()
        return gated if gated is not None else f(*args, **kwargs)
    return wrapper


def platform_requires(cap):
    """Like platform_admin_required, but also requires a specific capability
    (super_admin always passes; unrestricted admins pass; see utils.platform_roles)."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            gated = _platform_gate()
            if gated is not None:
                return gated
            from utils import platform_roles
            if not platform_roles.can(cap):
                if request.method not in ('GET', 'HEAD'):
                    flash('You do not have permission for that platform action.', 'error')
                    return _back()
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return deco


@platform_bp.context_processor
def _inject_platform_caps():
    """Expose platform_can() to platform templates so the nav hides what a
    limited admin can't reach."""
    from utils import platform_roles
    open_tickets = 0
    try:
        open_tickets = tenancy.count_open_tickets()
    except Exception:
        pass
    return {'platform_can': platform_roles.can, 'open_tickets': open_tickets}


def _audit(action, *, subdomain=None, detail=None):
    """Record a platform-admin action to the control-plane audit trail."""
    tenancy.log_platform(action, subdomain=subdomain, detail=detail,
                         actor=session.get('username') or 'admin')


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
        'auto_renew': bool(getattr(t, 'auto_renew', 0)),
        'created': t.created_at.strftime('%d %b %Y') if t.created_at else '—',
        'created_at': t.created_at,
        # A subscriber whose access lapses within 3 days needs attention.
        'ending_soon': (not st['owner'] and st['active']
                        and st['days_left'] is not None and st['days_left'] <= 3),
        # customer state bucket for filtering/segments
        'bucket': ('owner' if st['owner']
                   else 'archived' if t.status == 'archived'
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
    now = _dt.datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    def _created_since(since):
        return sum(1 for r in rows if not r['owner'] and r['created_at'] and r['created_at'] >= since)
    mrr = paying * price
    summary = {
        'total': len(rows),
        'customers': customers,
        'active': sum(1 for r in rows if r['active'] and r['status'] == 'active'),
        'trial': sum(1 for r in rows if r['bucket'] == 'trial'),
        'paying': paying,
        'blocked': sum(1 for r in rows if r['bucket'] == 'unpaid'),
        'suspended': sum(1 for r in rows if r['status'] == 'suspended'),
        'ending_soon': sum(1 for r in rows if r['ending_soon']),
        'mrr': mrr,
        'arr': mrr * 12,
        'arpa': price if paying else 0,               # avg revenue per paying account
        'new_month': _created_since(month_start),
        'today': _created_since(today_start),
    }
    return rows, summary, price


@platform_bp.route('/')
@platform_admin_required
def dashboard():
    """Executive command center: the full KPI set, growth trend, distribution,
    what needs attention, and recent signups."""
    rows, summary, price = _rows_and_summary()
    attention = [r for r in rows if r['bucket'] == 'unpaid' or r['ending_soon']]
    attention.sort(key=lambda r: (r['bucket'] != 'unpaid', r['days_left'] if r['days_left'] is not None else 999))
    recent = sorted([r for r in rows if not r['owner']],
                    key=lambda r: r['created_at'] or _dt_min(), reverse=True)[:6]
    from utils.platform_stats import platform_totals
    from utils import platform_metrics
    totals = platform_totals(tenancy.list_tenants())
    m = platform_metrics.executive_summary()
    trend = m['trend']
    growth_line, growth_end, _ = platform_metrics.sparkline_points(trend.get('cumulative'))
    signup_bars = trend.get('signups') or []
    signup_max = max(signup_bars) if signup_bars else 0
    return render_template('platform/overview.html', active='overview',
                           summary=summary, price=price, totals=totals, m=m,
                           trend=trend, growth_line=growth_line, growth_end=growth_end,
                           signup_bars=signup_bars, signup_max=signup_max,
                           attention=attention[:8], recent=recent,
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/search')
@platform_admin_required
def search():
    """Global command-palette search: schools by name / subdomain / admin email,
    plus static console destinations. Returns JSON for the ⌘K overlay."""
    from flask import jsonify
    q = (request.args.get('q') or '').strip().lower()
    results = []
    # Console destinations (always available; filtered by the query).
    nav = [
        ('Overview', 'fa-gauge-high', url_for('platform.dashboard')),
        ('Schools', 'fa-school', url_for('platform.schools')),
        ('Subscriptions', 'fa-credit-card', url_for('platform.subscriptions')),
        ('Pricing', 'fa-tags', url_for('platform.pricing')),
        ('Analytics', 'fa-chart-line', url_for('platform.analytics')),
        ('Audit log', 'fa-clock-rotate-left', url_for('platform.audit')),
        ('Health', 'fa-heart-pulse', url_for('platform.health')),
        ('Edit homepage', 'fa-pen-ruler', url_for('platform.homepage')),
    ]
    for label, icon, href in nav:
        if not q or q in label.lower():
            results.append({'type': 'page', 'label': label, 'sub': 'Console',
                            'icon': icon, 'href': href})
    # Schools (cap the payload; rank exact/startswith first).
    if q:
        hits = []
        for t in tenancy.list_tenants():
            hay = f'{t.name or ""} {t.subdomain or ""} {t.admin_email or ""}'.lower()
            if q in hay:
                rank = (0 if (t.subdomain or '').lower().startswith(q)
                        or (t.name or '').lower().startswith(q) else 1)
                hits.append((rank, t))
        hits.sort(key=lambda x: (x[0], (x[1].name or '').lower()))
        for _rank, t in hits[:12]:
            results.append({'type': 'school', 'label': t.name or t.subdomain,
                            'sub': f'{t.subdomain} · {t.status}', 'icon': 'fa-school',
                            'href': url_for('platform.tenant_profile', subdomain=t.subdomain)})
    return jsonify({'results': results[:20]})


@platform_bp.route('/schools')
@platform_admin_required
def schools():
    """Full school management: search, per-school actions, bulk actions.
    A ``?filter=`` segment (from the dashboard KPIs) pre-filters the list."""
    rows, summary, price = _rows_and_summary()
    seg = (request.args.get('filter') or '').strip()
    _SEGMENTS = {
        'paying': lambda r: r['bucket'] == 'paying',
        'trial': lambda r: r['bucket'] == 'trial',
        'unpaid': lambda r: r['bucket'] == 'unpaid',
        'suspended': lambda r: r['status'] == 'suspended',
        'archived': lambda r: r['status'] == 'archived',
        'ending_soon': lambda r: r['ending_soon'],
        'customers': lambda r: not r['owner'],
    }
    if seg in _SEGMENTS:
        rows = [r for r in rows if _SEGMENTS[seg](r)]
    rows.sort(key=lambda r: (r['owner'] is False, r['name'].lower()))
    return render_template('platform/schools.html', active='schools',
                           rows=rows, summary=summary, segment=seg if seg in _SEGMENTS else '',
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/schools/export')
@platform_requires('export_reports')
def schools_export():
    """Download the tenant directory as CSV (honours the ?filter= segment)."""
    import csv
    import io
    from flask import Response
    rows, _summary, _price = _rows_and_summary()
    seg = (request.args.get('filter') or '').strip()
    _SEGMENTS = {
        'paying': lambda r: r['bucket'] == 'paying', 'trial': lambda r: r['bucket'] == 'trial',
        'unpaid': lambda r: r['bucket'] == 'unpaid', 'suspended': lambda r: r['status'] == 'suspended',
        'archived': lambda r: r['status'] == 'archived',
        'ending_soon': lambda r: r['ending_soon'], 'customers': lambda r: not r['owner'],
    }
    if seg in _SEGMENTS:
        rows = [r for r in rows if _SEGMENTS[seg](r)]
    rows.sort(key=lambda r: (r['owner'] is False, r['name'].lower()))
    # Tags come from the registry rows, not _row(); index them once.
    tags = {t.subdomain: (t.tags or '') for t in tenancy.list_tenants()}
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Name', 'Subdomain', 'Admin email', 'Status', 'Plan', 'Segment',
                'Days left', 'Access until', 'Paid until', 'Registered', 'Tags'])
    for r in rows:
        w.writerow([r['name'], r['subdomain'], r['admin_email'], r['status'], r['plan'],
                    r['bucket'], r['days_left'] if r['days_left'] is not None else '',
                    r['access_until'], r['paid_until'], r['created'], tags.get(r['subdomain'], '')])
    _audit('export', detail=f'tenant directory ({len(rows)} rows{", " + seg if seg else ""})')
    fname = f'tenants{"_" + seg if seg else ""}.csv'
    return csv_response(out.getvalue(), f'{fname}')


@platform_bp.route('/subscriptions')
@platform_requires('view_revenue')
def subscriptions():
    """Billing & subscriptions: revenue, who's paying / on trial / lapsed."""
    rows, summary, price = _rows_and_summary()
    customers = [r for r in rows if not r['owner']]
    customers.sort(key=lambda r: ({'unpaid': 0, 'trial': 1, 'paying': 2, 'suspended': 3}.get(r['bucket'], 9),
                                  r['days_left'] if r['days_left'] is not None else 999))
    from utils import platform_billing
    overview = platform_billing.billing_overview()
    payments = tenancy.list_payments(limit=40)
    return render_template('platform/subscriptions.html', active='subscriptions',
                           rows=customers, summary=summary, price=price, ov=overview,
                           payments=payments,
                           period=current_app.config.get('TENANT_PLAN_DAYS'),
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


@platform_bp.route('/subscriptions/payments.csv')
@platform_requires('export_reports')
def payments_export():
    """Download the full payments ledger (every credited payment) as CSV."""
    import csv
    import io
    rows = tenancy.list_payments(limit=100000)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Date', 'School', 'Subdomain', 'Reference'])
    for p in rows:
        w.writerow([p['at'].strftime('%Y-%m-%d %H:%M') if p['at'] else '',
                    p['name'], p['subdomain'], p['reference']])
    _audit('export', detail=f'payments ledger ({len(rows)} rows)')
    return csv_response(out.getvalue(), 'payments.csv')


@platform_bp.route('/homepage', methods=['GET', 'POST'])
@platform_requires('manage_settings')
def homepage():
    """Edit the public marketing homepage content (stored in the control plane).
    Lets the marketing/sales team change copy, pricing and FAQ live — no deploy."""
    from utils import site_content
    if request.method == 'POST':
        content = site_content.get_homepage()
        for k in ('brand', 'hero_title', 'hero_subtitle', 'hero_cta',
                  'trial_note', 'price_period', 'footer'):
            content[k] = (request.form.get(k) or '').strip()
        content['features'] = site_content.parse_pairs(
            request.form.get('features'), ('title', 'body'))
        content['steps'] = site_content.parse_pairs(
            request.form.get('steps'), ('title', 'body'))
        content['faqs'] = site_content.parse_pairs(
            request.form.get('faqs'), ('q', 'a'))
        content['testimonials'] = site_content.parse_pairs(
            request.form.get('testimonials'), ('name', 'quote'))
        # Contact block — shown on the homepage (contact cards + footer icons).
        import re as _re
        _wa = _re.sub(r'\D', '', request.form.get('contact_whatsapp') or '')  # wa.me wants digits only
        content['contact'] = {
            'email': (request.form.get('contact_email') or '').strip(),
            'phone': (request.form.get('contact_phone') or '').strip(),
            'whatsapp': _wa,
        }
        # Legal-document fields (company name, effective date, DPO, sub-processors).
        for k in ('legal_entity', 'legal_effective', 'dpo_email'):
            content[k] = (request.form.get(k) or '').strip()
        content['subprocessors'] = site_content.parse_pairs(
            request.form.get('subprocessors'), ('name', 'purpose'))
        site_content.save_homepage(content)
        _audit('homepage', detail='homepage content updated')
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
        testimonials_text=site_content.format_pairs(content.get('testimonials'), ('name', 'quote')),
        subprocessors_text=site_content.format_pairs(content.get('subprocessors'), ('name', 'purpose')))


@platform_bp.route('/pricing', methods=['GET', 'POST'])
@platform_requires('manage_plans')
def pricing():
    """Edit the subscription tiers (price, duration, label, badge, on/off).
    Stored in the control plane, so changes are live everywhere — homepage,
    register and each school's billing page — with no redeploy. Changing a price
    only affects future payments; existing subscribers keep what they paid for."""
    from utils import plans
    if request.method == 'POST':
        tiers = {}
        for pid in plans.TIER_IDS:
            price = request.form.get(f'{pid}_price', type=int)      # naira
            days = request.form.get(f'{pid}_days', type=int)
            if price is not None and price < 0:
                flash('Prices cannot be negative.', 'error')
                return redirect(url_for('platform.pricing'))
            if days is not None and days < 1:
                flash('Duration must be at least 1 day.', 'error')
                return redirect(url_for('platform.pricing'))
            tiers[pid] = {
                'enabled': request.form.get(f'{pid}_enabled') == 'on',
                'label': (request.form.get(f'{pid}_label') or '').strip() or None,
                'price_kobo': price * 100 if price is not None else None,
                'days': days or None,
                'badge': (request.form.get(f'{pid}_badge') or '').strip() or None,
            }
        # The Monthly tier is the anchor for every other tier's savings and the
        # homepage headline price — it can never be switched off.
        if not tiers['monthly']['enabled']:
            tiers['monthly']['enabled'] = True
            flash('The Monthly tier stays on — it anchors pricing everywhere. '
                  'Other changes were saved.', 'info')
        plans.save_pricing({
            'tiers': tiers,
            'updated_at': _dt.datetime.utcnow().isoformat() + 'Z',
            'updated_by': session.get('username') or 'admin',
        })
        _audit('pricing', detail='subscription tiers updated')
        flash('Pricing updated — changes are live.', 'success')
        return redirect(url_for('platform.pricing'))

    stored = plans.get_pricing()
    return render_template(
        'platform/pricing.html', active='pricing',
        tiers=plans.tenant_plans(include_disabled=True),
        updated_at=stored.get('updated_at'), updated_by=stored.get('updated_by'))


@platform_bp.route('/features', methods=['GET', 'POST'])
@platform_requires('manage_plans')
def features():
    """Edit the entitlement matrix: which features and numeric limits each tier
    (Free/Basic/Premium/Enterprise) grants. Stored in the control plane, live."""
    from utils import entitlements as ent
    if request.method == 'POST':
        tiers = {}
        for tid in ent.TIER_IDS:
            feats = {fk: (request.form.get(f'{tid}__f__{fk}') == 'on')
                     for fk, _ in ent.FEATURES}
            lims = {}
            for lk, _label, _unit in ent.LIMITS:
                v = request.form.get(f'{tid}__l__{lk}', type=int)
                lims[lk] = v if v is not None else 0
            tiers[tid] = {'features': feats, 'limits': lims}
        ent.save_tiers(tiers)
        _audit('features', detail='entitlement matrix updated')
        flash('Plan features & limits updated — live everywhere.', 'success')
        return redirect(url_for('platform.features'))
    return render_template('platform/features.html', active='features',
                           tiers=ent.get_tiers(), tier_ids=ent.TIER_IDS,
                           tier_labels=ent.TIER_LABELS,
                           feature_defs=ent.FEATURES, limit_defs=ent.LIMITS)


@platform_bp.route('/tenant/<subdomain>/tier', methods=['POST'])
@platform_requires('manage_tenants')
def set_tier(subdomain):
    """Change a tenant's entitlement tier and per-tenant feature overrides."""
    from utils import entitlements as ent
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    tier = (request.form.get('tier') or '').strip().lower()
    if tier not in ent.TIER_IDS:
        tier = ent.DEFAULT_TIER
    # Per-tenant feature overrides: only store the ones that differ from the tier.
    tiers = ent.get_tiers()
    base_feats = (tiers.get(tier) or tiers[ent.DEFAULT_TIER])['features']
    ov_feats = {}
    for fk, _ in ent.FEATURES:
        checked = request.form.get(f'ov__{fk}') == 'on'
        if checked != base_feats.get(fk, False):
            ov_feats[fk] = checked
    overrides = {'features': ov_feats} if ov_feats else {}
    tenancy.set_entitlement(subdomain, tier=tier, overrides=overrides)
    _audit('tier', subdomain=subdomain,
           detail=f'tier={tier}' + (f', overrides={list(ov_feats)}' if ov_feats else ''))
    flash(f'Plan set to {ent.TIER_LABELS.get(tier, tier)}.', 'success')
    return redirect(url_for('platform.tenant_profile', subdomain=subdomain))


@platform_bp.route('/tenant/<subdomain>/impersonate', methods=['POST'])
@platform_requires('manage_tenants')
def impersonate(subdomain):
    """Mint a time-boxed, read-only support session for a school and hand the
    operator a one-time link on the school's own host."""
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    if billing.is_owner(t):
        flash('You are already the owner — no need to impersonate.', 'info')
        return _back()
    if t.status != 'active':
        flash('Only an active school can be viewed — its portal is offline.', 'error')
        return _back()
    reason = (request.form.get('reason') or '').strip()
    if not reason:
        flash('A reason is required to start a support session.', 'error')
        return redirect(url_for('platform.tenant_profile', subdomain=subdomain))
    ttl = request.form.get('minutes', type=int) or 30
    ttl = max(5, min(ttl, 120))
    g = tenancy.create_impersonation(session.get('username') or 'admin', subdomain, reason,
                                     ttl_minutes=ttl)
    _audit('impersonate_grant', subdomain=subdomain, detail=f'{ttl}m · {reason[:120]}')
    base = current_app.config.get('TENANT_BASE_DOMAIN', '')
    link = f'https://{t.subdomain}.{base}/impersonate/{g.token}' if base \
        else url_for('impersonation.establish', token=g.token)
    return redirect(link)


@platform_bp.route('/impersonation')
@platform_admin_required
def impersonation_log():
    """Active and recent support sessions, with a kill switch for live ones."""
    rows = tenancy.list_impersonations(limit=100)
    return render_template('platform/impersonation.html', active='impersonation', rows=rows)


@platform_bp.route('/impersonation/<int:grant_id>/end', methods=['POST'])
@platform_requires('manage_tenants')
def impersonation_end(grant_id):
    """Kill switch: end a live support session immediately."""
    g = tenancy.get_impersonation(grant_id=grant_id)
    if g is None:
        abort(404)
    tenancy.end_impersonation(grant_id=grant_id)
    _audit('impersonate_kill', subdomain=g.subdomain, detail=f'ended grant #{grant_id}')
    flash('Support session ended.', 'success')
    return redirect(url_for('platform.impersonation_log'))


@platform_bp.app_context_processor
def _inject_broadcasts():
    """Expose live platform broadcasts to tenant portal templates (base.html).
    Only for a logged-in user on a real tenant host; no-op elsewhere."""
    try:
        if not session.get('logged_in'):
            return {}
        t = current_tenant()
        if t is None:
            return {}
        bc = list(tenancy.broadcasts_for(t))
        from utils import platform_settings
        st = platform_settings.get_settings()
        if st.get('maintenance_mode'):
            import types
            bc.insert(0, types.SimpleNamespace(
                level='critical',
                message=st.get('maintenance_message') or 'Scheduled maintenance is in progress — some features may be briefly unavailable.'))
        return {'platform_broadcasts': bc} if bc else {}
    except Exception:
        return {}


@platform_bp.route('/broadcasts', methods=['GET', 'POST'])
@platform_requires('manage_settings')
def broadcasts():
    """Compose and manage platform-wide announcements to tenant admins."""
    if request.method == 'POST':
        msg = (request.form.get('message') or '').strip()
        if not msg:
            flash('Enter a message to broadcast.', 'error')
            return redirect(url_for('platform.broadcasts'))
        days = request.form.get('days', type=int)
        ends_at = (_dt.datetime.utcnow() + _dt.timedelta(days=days)) if days and days > 0 else None
        b = tenancy.create_broadcast(
            msg, level=(request.form.get('level') or 'info'),
            segment=(request.form.get('segment') or 'all'),
            created_by=session.get('username') or 'admin', ends_at=ends_at)
        _audit('broadcast', detail=f'{b.segment} · {b.level} · {msg[:80]}')
        flash('Broadcast published — live for matching schools.', 'success')
        return redirect(url_for('platform.broadcasts'))
    rows = tenancy.list_broadcasts()
    return render_template('platform/broadcasts.html', active='broadcasts', rows=rows,
                           segments=tenancy._BROADCAST_SEGMENTS)


@platform_bp.route('/broadcasts/<int:bid>/end', methods=['POST'])
@platform_requires('manage_settings')
def broadcast_end(bid):
    tenancy.end_broadcast(bid)
    _audit('broadcast_end', detail=f'ended #{bid}')
    flash('Broadcast ended.', 'success')
    return redirect(url_for('platform.broadcasts'))


@platform_bp.route('/settings', methods=['GET', 'POST'])
@platform_requires('manage_settings')
def settings_page():
    """Global platform settings: support contact + maintenance mode."""
    from utils import platform_settings
    if request.method == 'POST':
        saved = platform_settings.save_settings({
            'support_email': request.form.get('support_email'),
            'support_phone': request.form.get('support_phone'),
            'maintenance_mode': request.form.get('maintenance_mode') == 'on',
            'maintenance_message': request.form.get('maintenance_message'),
        })
        _audit('settings', detail='maintenance=%s' % saved['maintenance_mode'])
        flash('Platform settings saved.', 'success')
        return redirect(url_for('platform.settings_page'))
    from utils import platform_health
    checks = platform_health.health_checks(current_app)
    return render_template('platform/settings.html', active='settings',
                           s=platform_settings.get_settings(), checks=checks)


@platform_bp.route('/tickets')
@platform_admin_required
def tickets():
    """The support queue across all schools."""
    status = (request.args.get('status') or 'open').strip()
    status = status if status in ('open', 'closed') else None
    rows = tenancy.list_tickets(status=status)
    return render_template('platform/tickets.html', active='tickets', rows=rows,
                           status=(status or 'all'), open_count=tenancy.count_open_tickets())


@platform_bp.route('/tickets/<int:ticket_id>', methods=['GET', 'POST'])
@platform_admin_required
def ticket_detail(ticket_id):
    ticket, messages = tenancy.get_ticket(ticket_id)
    if ticket is None:
        abort(404)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'close':
            tenancy.set_ticket_status(ticket_id, 'closed')
            _audit('ticket_close', subdomain=ticket.subdomain, detail=f'#{ticket_id}')
            flash('Ticket closed.', 'success')
        else:
            body = (request.form.get('body') or '').strip()
            if body:
                tenancy.add_ticket_message(ticket_id, body,
                                           author=session.get('username') or 'admin', is_staff=True)
                _audit('ticket_reply', subdomain=ticket.subdomain, detail=f'#{ticket_id}')
                flash('Reply sent.', 'success')
        return redirect(url_for('platform.ticket_detail', ticket_id=ticket_id))
    return render_template('platform/ticket.html', active='tickets',
                           ticket=ticket, messages=messages)


@platform_bp.route('/tenant/<subdomain>')
@platform_admin_required
def tenant_profile(subdomain):
    """One school's full profile: general info, subscription/billing, live usage,
    recent payments, internal notes/tags, and one-click actions."""
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    st = billing.status(t)
    from utils.platform_stats import tenant_usage
    usage = tenant_usage(t.database_url) if t.status == 'active' else {}
    payments = tenancy.recent_payments(subdomain)
    tag_list = [x.strip() for x in (t.tags or '').split(',') if x.strip()]
    timeline = tenancy.tenant_timeline(subdomain)
    from utils import entitlements as ent
    from utils import platform_customer_success as cs
    resolved = ent.resolve(t)
    usage_limits = ent.usage_vs_limits(t, usage)
    health = cs.health_score(t)
    onboarding = cs.onboarding_progress(usage) if t.status == 'active' else None
    return render_template('platform/tenant.html', active='schools', t=t, st=st,
                           row=_row(t), usage=usage, payments=payments, tags=tag_list,
                           timeline=timeline, portal_url=_portal_url(t),
                           health=health, onboarding=onboarding,
                           ent=resolved, usage_limits=usage_limits,
                           feature_defs=ent.FEATURES, tier_ids=ent.TIER_IDS,
                           tier_labels=ent.TIER_LABELS,
                           plan_days=current_app.config.get('TENANT_PLAN_DAYS'))


def _portal_url(t):
    base = current_app.config.get('TENANT_BASE_DOMAIN', '')
    return f'https://{t.subdomain}.{base}/' if base else '#'


@platform_bp.route('/tenant/<subdomain>/notes', methods=['POST'])
@platform_requires('manage_tenants')
def save_notes(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    tenancy.set_meta(subdomain, notes=request.form.get('notes', ''),
                     tags=request.form.get('tags', ''),
                     account_manager=request.form.get('account_manager', ''),
                     priority=request.form.get('priority', ''),
                     risk=request.form.get('risk', ''))
    _audit('notes', subdomain=subdomain, detail='notes/tags/CRM updated')
    flash('Tenant details saved.', 'success')
    return redirect(url_for('platform.tenant_profile', subdomain=subdomain))


@platform_bp.route('/<subdomain>/archive', methods=['POST'])
@platform_requires('manage_tenants')
def archive(subdomain):
    """Soft-delete: take a school offline without dropping its database, so it
    can be restored. Archived tenants are unreachable (tenant_runtime only serves
    'active') but keep all data, unlike delete which drops the database."""
    t = tenancy.get_tenant(subdomain)
    if t is None or billing.is_owner(t):
        abort(404)
    if t.status == 'archived':
        tenancy.set_status(subdomain, 'active')
        _audit('restore', subdomain=subdomain, detail=t.name)
        flash(f'{t.name} restored — its portal is reachable again.', 'success')
    else:
        tenancy.set_status(subdomain, 'archived', error='archived by platform admin')
        _audit('archive', subdomain=subdomain, detail=t.name)
        flash(f'{t.name} archived — data kept, portal offline. Restore anytime.', 'success')
    return _back()


@platform_bp.route('/team', methods=['GET', 'POST'])
@platform_admin_required
def team():
    """Assign granular platform capabilities to admin users (super-admin only).
    An admin not listed here keeps full access, so existing setups are unchanged."""
    if session.get('role') != 'super_admin':
        abort(403)
    from utils import platform_roles
    from models import User
    admins = (User.query.filter(User.role.in_(('admin',)), User.is_active == True)
              .order_by(User.username).all())
    if request.method == 'POST':
        team_map = {}
        for u in admins:
            preset = (request.form.get(f'preset_{u.username}') or 'full').strip()
            if preset == 'full':
                continue                       # unrestricted → leave off the map
            if preset in platform_roles.ROLE_PRESETS:
                team_map[u.username] = platform_roles.preset_caps(preset)
            elif preset == 'custom':
                team_map[u.username] = [c for c, _ in platform_roles.CAPS
                                        if request.form.get(f'cap_{u.username}_{c}') == 'on']
        platform_roles.save_team(team_map)
        _audit('team', detail=f'{len(team_map)} restricted admin(s)')
        flash('Platform roles saved.', 'success')
        return redirect(url_for('platform.team'))
    current = platform_roles.get_team()
    return render_template('platform/team.html', active='team',
                           presets=platform_roles.ROLE_PRESETS,
                           role_of=platform_roles.role_of,
                           admins=admins, caps=platform_roles.CAPS, current=current)


@platform_bp.route('/analytics')
@platform_requires('view_analytics')
def analytics():
    """Growth & subscription trends over the last 12 months (from control-plane
    history: signups, payments/renewals, churn events, cumulative schools)."""
    from utils import platform_analytics
    data = platform_analytics.monthly_trends(12)
    return render_template('platform/analytics.html', active='analytics', d=data)


@platform_bp.route('/health')
@platform_admin_required
def health():
    """Operational health: control-plane + tenant DB reachability, scheduler,
    and gateway/email configuration (no external calls)."""
    from utils import platform_health
    rows = platform_health.health_checks(current_app)
    return render_template('platform/health.html', active='health',
                           checks=rows, overall=platform_health.overall(rows))


@platform_bp.route('/audit')
@platform_admin_required
def audit():
    """Searchable log of every platform-admin action against the control plane."""
    action = (request.args.get('action') or '').strip() or None
    sub = (request.args.get('subdomain') or '').strip() or None
    q = (request.args.get('q') or '').strip() or None
    rows = tenancy.list_platform_audit(action=action, subdomain=sub, q=q)
    chain = tenancy.verify_audit_chain()
    return render_template('platform/audit.html', active='audit',
                           rows=rows, actions=tenancy.audit_actions(), chain=chain,
                           f={'action': action or '', 'subdomain': sub or '', 'q': q or ''})


def _back(default='platform.schools'):
    """Return to the page the action was triggered from (a tenant profile,
    Schools or Subscriptions), falling back to the schools list."""
    ref = request.referrer or ''
    if '/platform/tenant/' in ref:
        return redirect(ref)
    for ep in ('platform.subscriptions', 'platform.schools', 'platform.dashboard'):
        if url_for(ep) in ref:
            return redirect(ref)
    return redirect(url_for(default))


@platform_bp.route('/<subdomain>/grant', methods=['POST'])
@platform_requires('manage_billing')
def grant(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None:
        abort(404)
    if billing.is_owner(t):
        flash('The owner school is already free forever.', 'info')
        return _back()
    days = request.form.get('days', type=int) or current_app.config.get('TENANT_PLAN_DAYS')
    billing.record_payment(subdomain, days=days)
    _audit('grant', subdomain=subdomain, detail=f'{days} day(s)')
    flash(f'Granted {days} day(s) to {t.name}.', 'success')
    return _back()


@platform_bp.route('/<subdomain>/suspend', methods=['POST'])
@platform_requires('manage_tenants')
def suspend(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None or billing.is_owner(t):
        abort(404)
    if t.status == 'suspended':
        tenancy.set_status(subdomain, 'active')
        _audit('reactivate', subdomain=subdomain, detail=t.name)
        flash(f'{t.name} reactivated.', 'success')
    else:
        tenancy.set_status(subdomain, 'suspended', error='suspended by platform admin')
        _audit('suspend', subdomain=subdomain, detail=t.name)
        flash(f'{t.name} suspended — its portal is now unreachable.', 'success')
    return _back()


@platform_bp.route('/bulk', methods=['POST'])
@platform_requires('manage_tenants')
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
        elif action == 'grant':
            days = request.form.get('days', type=int) or current_app.config.get('TENANT_PLAN_DAYS')
            billing.record_payment(sub, days=days)
            done += 1
        elif action == 'delete':
            provisioning.drop_tenant(sub, forget=True)
            done += 1
    _audit(f'bulk_{action}', detail=f'{done} school(s)')
    flash(f'{(action or "").title()} applied to {done} school(s).', 'success')
    return _back()


@platform_bp.route('/<subdomain>/delete', methods=['POST'])
@platform_requires('manage_tenants')
def delete(subdomain):
    t = tenancy.get_tenant(subdomain)
    if t is None or billing.is_owner(t):
        abort(404)                           # never delete the owner
    if (request.form.get('confirm') or '').strip().lower() != t.subdomain:
        flash('Type the subdomain to confirm deletion.', 'error')
        return _back()
    provisioning.drop_tenant(subdomain, forget=True)   # drop DB + remove registry row
    _audit('delete', subdomain=subdomain, detail=t.name)
    flash(f'{t.name} and its database were deleted.', 'success')
    return redirect(url_for('platform.schools'))       # the profile no longer exists
