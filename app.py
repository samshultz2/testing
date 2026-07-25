"""
EduSyncra School Management System
Main Flask application entry point
"""
import os
import secrets
from flask import Flask, session, Response
from config import Config, get_config
from models import db, init_db
from routes import auth_bp, main_bp, academics_bp, attendance_bp, results_bp, reports_bp, settings_bp, subjects_bp, timetable_bp, promotion_bp, users_bp, staff_onb_bp
from routes.generator import generator_bp
from routes.contributions import contributions_bp
from routes.mock_jamb import mock_jamb_bp, mock_jamb_portal_bp
from routes.mock_waec import mock_waec_bp
from routes.finance import finance_bp
from routes.communication import comms_bp
from routes.hr import hr_bp
from routes.admissions import adm_bp
from routes.library import library_bp
from routes.events import events_bp
from routes.cbt import cbt_bp, cbt_portal_bp
from routes.result_portal import scratchcards_bp, result_portal_bp
from routes.parent_portal import parent_bp
from routes.sales import sales_bp
from routes.welfare import welfare_bp


_scheduler_started = False


# Arbitrary, fixed key for the cross-worker PostgreSQL advisory lock that makes
# scheduled dispatch run on exactly ONE worker per tick (with automatic failover
# if that worker dies). Without it, every gunicorn worker would send each due
# campaign — duplicate SMS/fee reminders to parents.
_SCHED_LOCK_KEY = 0x5C8ED01


def _tick_dispatch(app):
    """Run one scheduling tick. In multi-tenant mode this runs once per active
    school (bound to that school's database); otherwise once for the single DB."""
    if app.config.get('MULTI_TENANT'):
        from flask import g
        from utils import tenancy
        from utils.tenant_runtime import _engine_for
        for t in tenancy.list_tenants():
            if t.status != 'active' or not t.database_url:
                continue
            try:
                g.tenant_engine = _engine_for(t.database_url)
                _tick_one(app)
            except Exception:
                app.logger.exception('scheduled-jobs tick failed for tenant %s', t.subdomain)
            finally:
                g.pop('tenant_engine', None)
    else:
        _tick_one(app)


def _tick_one(app):
    """One scheduling tick against the currently-bound database, guarded so only
    one worker dispatches at a time."""
    from models import db
    from sqlalchemy import text
    # Use the session's routed bind (tenant-aware) rather than the default engine.
    is_pg = db.session.get_bind().dialect.name == 'postgresql'
    if is_pg:
        got = db.session.execute(
            text('SELECT pg_try_advisory_lock(:k)'), {'k': _SCHED_LOCK_KEY}).scalar()
        if not got:
            return                                  # another worker owns this tick
    try:
        from utils.comms import dispatch_due_scheduled
        dispatch_due_scheduled()
        # Daily fee reminders: a DB-shared marker so they fire once per day across
        # ALL workers (a per-process flag would fire once per worker).
        import time as _t
        from models.models import SchoolSettings
        today = _t.strftime('%Y-%m-%d')
        if SchoolSettings.get('last_fee_reminder_date') != today:
            from utils.reminders import run_fee_reminders
            run_fee_reminders(app)                  # opt-in; no-op unless enabled
            SchoolSettings.set('last_fee_reminder_date', today, 'string',
                               'Last date the daily fee-reminder job ran')
        # Daily library reminders (overdue + due-soon), opt-in via the automation
        # center; a DB-shared marker fires them once per day across all workers.
        if SchoolSettings.get('last_library_reminder_date') != today:
            try:
                from utils.library_notify import run_library_reminders
                run_library_reminders(app)
            except Exception:
                app.logger.exception('library reminder job failed')
            SchoolSettings.set('last_library_reminder_date', today, 'string',
                               'Last date the daily library-reminder job ran')
        # Daily stock alerts (low-stock + expiry), opt-in via the automation
        # center; a DB-shared marker fires them once per day across all workers.
        if SchoolSettings.get('last_stock_alert_date') != today:
            try:
                from utils.stock_notify import run_stock_alerts
                run_stock_alerts(app)
            except Exception:
                app.logger.exception('stock alert job failed')
            SchoolSettings.set('last_stock_alert_date', today, 'string',
                               'Last date the daily stock-alert job ran')
        # Daily exam-analytics refresh: recompute the SSS3 risk/prediction rows,
        # backfill correlation and warm the hub caches so the first load of the
        # day is never cold. Own DB-shared marker (runs once per day per school).
        try:
            from utils.exam_refresh import run_daily_refresh_if_due
            run_daily_refresh_if_due(app)
        except Exception:
            app.logger.exception('exam analytics refresh job failed')
        # Term-end board-pack delivery: email the institution analytics pack to
        # owners once per published term. Opt-in via the institution view.
        try:
            from utils.results_notify import run_board_pack_delivery_if_due
            run_board_pack_delivery_if_due(app)
        except Exception:
            app.logger.exception('board pack delivery job failed')
    finally:
        if is_pg:
            db.session.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': _SCHED_LOCK_KEY})
            db.session.commit()


def _start_scheduled_messages_worker(app):
    """Daemon thread that every minute dispatches due scheduled SMS / fee reminders.

    Safe under multi-worker gunicorn: a PostgreSQL advisory lock ensures only one
    worker actually dispatches per tick. (On non-Postgres dev/test there is a single
    process, so no lock is needed.)"""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    import threading
    import time

    def _loop():
        while True:
            time.sleep(60)
            try:
                with app.app_context():
                    _tick_dispatch(app)
            except Exception:
                app.logger.exception('scheduled-jobs tick failed')

    threading.Thread(target=_loop, daemon=True).start()


def create_app(config_class=None):
    """Application factory pattern.

    When no config class is passed, the environment selects it via APP_ENV /
    FLASK_ENV (development | production | testing). Tests pass an explicit
    TestConfig, so their behaviour is unchanged.
    """
    if config_class is None:
        config_class = get_config()
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Enforce/surface security configuration at startup (previously defined on
    # the config but never invoked). Skip under tests to keep output clean.
    if not app.config.get('TESTING'):
        import sys
        # Fail closed in production: refuse to boot if a critical secret is
        # missing (SECRET_KEY, FIELD_ENCRYPTION_KEY).
        if app.config.get('ENFORCE_SECURITY'):
            errors = config_class.security_errors()
            if errors:
                raise RuntimeError(
                    'Refusing to start — fix these security settings:\n  - '
                    + '\n  - '.join(errors))
        for _w in config_class.security_warnings():
            print('SECURITY: ' + _w, file=sys.stderr)

    # Optional Sentry error monitoring (opt-in via SENTRY_DSN; no-op otherwise).
    try:
        from utils.monitoring import init_sentry
        init_sentry(app)
    except Exception:
        pass

    # Ensure instance folder exists
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)

    # Alembic migrations (flask db ...). create_all (below) still builds fresh
    # dev/test databases; Alembic is for controlled schema changes to existing
    # databases. See docs/MIGRATIONS.md.
    try:
        from flask_migrate import Migrate
        Migrate(app, db, directory='db_migrations')
    except ImportError:
        pass
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(academics_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(subjects_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(promotion_bp)
    app.register_blueprint(generator_bp)
    app.register_blueprint(contributions_bp)
    app.register_blueprint(mock_jamb_bp)
    app.register_blueprint(mock_jamb_portal_bp)
    app.register_blueprint(mock_waec_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(staff_onb_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(comms_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(adm_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(cbt_bp)
    app.register_blueprint(cbt_portal_bp)
    app.register_blueprint(scratchcards_bp)
    app.register_blueprint(result_portal_bp)
    app.register_blueprint(parent_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(welfare_bp)

    # Public multi-tenant onboarding (only reachable when MULTI_TENANT is on).
    from routes.onboarding import onboarding_bp
    app.register_blueprint(onboarding_bp)
    from routes.billing import billing_bp
    app.register_blueprint(billing_bp)
    from routes.platform import platform_bp
    app.register_blueprint(platform_bp)
    from routes.marketing import marketing_bp
    app.register_blueprint(marketing_bp)
    from routes.website_public import website_bp
    app.register_blueprint(website_bp)
    from routes.website_admin import website_admin_bp
    app.register_blueprint(website_admin_bp)

    # Initialize database. In multi-tenant mode the app has no single database of
    # its own — each school's database is created by provisioning — so we init
    # only the control plane here and NEVER create_all/seed against a tenant DB
    # at boot.
    with app.app_context():
        if app.config.get('MULTI_TENANT'):
            from utils.tenancy import init_control_plane
            init_control_plane()
        else:
            init_db(app)

    # Finance ledger: mirror every money event (fees, sales, expenses) into the
    # central FinanceTransaction ledger — the single source of truth.
    from utils.finance_ledger import register_ledger_hooks, ensure_tables
    register_ledger_hooks()
    # Ensure the finance tables exist even under SKIP_CREATE_ALL (Alembic-managed
    # production) — they were added after the schema baseline.
    try:
        with app.app_context():
            ensure_tables()
    except Exception:
        app.logger.exception('Could not ensure finance tables on the main database')

    # Enable CSRF protection for all state-changing requests
    from utils.csrf import init_csrf
    init_csrf(app)

    # Coarse per-IP request ceiling — the first thing every request hits, so a
    # flood is shed before it can reach the DB or any heavier work. In-memory and
    # process-wide (fine for the single worker); the per-endpoint DB limiters stay
    # the precise controls. Skipped under tests and for static assets.
    from flask import request as _request, abort as _abort
    from utils.security import global_rate_exceeded

    def _enforce_global_rate_limit():
        cap = app.config.get('GLOBAL_RATE_PER_MIN', 0)
        if not cap or app.config.get('TESTING'):
            return
        if _request.endpoint == 'static':
            return
        ip = _request.remote_addr or 'anon'
        if global_rate_exceeded(f'req:{ip}', cap, 60):
            _abort(429, description='Too many requests. Please slow down and try again shortly.')

    # Multi-tenancy: resolve host -> school -> database engine BEFORE anything
    # else, so every downstream gate and query sees the right tenant. No-op when
    # MULTI_TENANT is off (single-school mode — current behaviour unchanged).
    from utils.tenant_runtime import route_tenant, enforce_billing
    from routes.marketing import serve_marketing_home
    app.before_request(route_tenant)
    # On a platform host (www/signup/apex-without-owner) the homepage is the
    # public marketing page, served here before any login gate. No-op otherwise.
    app.before_request(serve_marketing_home)
    app.before_request(enforce_billing)   # lock out lapsed (unpaid) schools

    app.before_request(_enforce_global_rate_limit)

    # Fine-grained module access for non-admin users.
    from utils.access_control import (enforce_module_access, enforce_read_only,
                                       enforce_write_level, enforce_subsection_access,
                                       enforce_idle_timeout, enforce_password_change,
                                       enforce_session_version)
    app.before_request(enforce_session_version)   # revoked/deactivated -> logout
    app.before_request(enforce_idle_timeout)
    app.before_request(enforce_password_change)
    app.before_request(enforce_module_access)
    app.before_request(enforce_read_only)
    app.before_request(enforce_write_level)
    app.before_request(enforce_subsection_access)

    # Friendly error pages
    from utils.errors import register_error_handlers
    register_error_handlers(app)

    # Keep a rolling daily backup of the database
    from utils.backup import auto_backup
    auto_backup(app)

    # Background worker: dispatch due scheduled parent-communication campaigns.
    # Runs in-process by default (fine for a single worker). When scaling to
    # multiple gunicorn workers, set RUN_INPROCESS_JOBS=0 and run the jobs in a
    # separate process (scripts/run_jobs.py) so they fire exactly once.
    _run_jobs = os.environ.get('RUN_INPROCESS_JOBS', '1').strip().lower() \
        not in ('0', 'false', 'no', 'off')
    if os.environ.get('POSYHUB_TESTING') != '1' and _run_jobs:
        _start_scheduled_messages_worker(app)

    # Serve the service worker from the root so its scope covers the whole app
    from flask import send_from_directory
    import os as _os

    @app.route('/sw.js')
    def _service_worker():
        resp = send_from_directory(_os.path.join(app.root_path, 'static', 'js'), 'sw.js')
        resp.headers['Content-Type'] = 'application/javascript'
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache'
        return resp

    @app.route('/robots.txt')
    def _robots():
        # Internal app — keep everything (incl. the public login / parent / result
        # portals) out of search indexes.
        return Response('User-agent: *\nDisallow: /\n', mimetype='text/plain')
    
    # Template context processors
    @app.context_processor
    def utility_processor():
        from models import AcademicSession, Term
        from datetime import date
        from utils.themes import THEMES, normalize_theme

        def current_theme():
            """The active UI theme: the logged-in user's saved choice, else default."""
            try:
                from utils.access_control import get_current_user
                t = session.get('theme')
                if not t:
                    u = get_current_user()
                    t = u.theme if u else None
                return normalize_theme(t)
            except Exception:
                return 'light'

        def get_active_session():
            return AcademicSession.query.filter_by(is_active=True).first()
        
        def get_active_term():
            return Term.query.filter_by(is_active=True).first()
        
        def csrf_token():
            """Generate CSRF token and store in session"""
            if '_csrf_token' not in session:
                session['_csrf_token'] = secrets.token_hex(32)
            return session['_csrf_token']

        def _csp_nonce_value():
            from utils.security import get_csp_nonce
            return get_csp_nonce()

        def bundle_url(filename):
            """Versioned URL for a static asset — appends ?v=<file mtime> so a
            rebuilt JS/CSS bundle busts browser, service-worker and CDN caches on
            the next deploy instead of serving a stale copy."""
            import os
            from flask import url_for as _url_for
            url = _url_for('static', filename=filename)
            try:
                path = os.path.join(app.static_folder, filename)
                return f'{url}?v={int(os.path.getmtime(path))}'
            except OSError:
                return url

        def _password_rules():
            """The server's password policy, for the live checklist on the
            password pages (single source of truth: utils.security)."""
            from utils.security import password_rules
            return password_rules()

        def _billing_nav():
            """Whether to show the school-side Subscription link (multi-tenant,
            non-owner school), plus days left for a subtle badge."""
            try:
                if not app.config.get('MULTI_TENANT'):
                    return {'show': False}
                from utils.tenant_runtime import current_tenant
                from utils import billing
                t = current_tenant()
                if t is None or billing.is_owner(t):
                    return {'show': False}
                return {'show': True, 'days_left': billing.days_left(t)}
            except Exception:
                return {'show': False}
        
        # User access context
        def get_user_permissions():
            """Get current user permissions for templates"""
            try:
                from utils.access_control import is_admin, is_teacher, can_mark_attendance, can_enter_results
                return {
                    'is_admin': is_admin(),
                    'is_teacher': is_teacher(),
                    'can_mark_attendance': can_mark_attendance(),
                    'can_enter_results': can_enter_results(),
                }
            except:
                return {
                    'is_admin': session.get('role') in ('super_admin', 'admin'),
                    'is_teacher': session.get('role') == 'teacher',
                    'can_mark_attendance': True,
                    'can_enter_results': True,
                }
        
        def can_access_module(key):
            try:
                from utils.access_control import can_access_module as _cam
                return _cam(key)
            except Exception:
                return True

        def can_write_module(key):
            try:
                from utils.access_control import can_write_module as _cwm
                return _cwm(key)
            except Exception:
                return True

        def can_manage_users():
            try:
                from utils.access_control import can_manage_users as _cmu
                return _cmu()
            except Exception:
                return False

        def page_can_write():
            try:
                from utils.access_control import page_can_write as _pcw
                return _pcw()
            except Exception:
                return True

        def can_generate_timetable():
            try:
                from utils.access_control import can_generate_timetable as _f
                return _f()
            except Exception:
                return False

        def can_generate_result_cards():
            try:
                from utils.access_control import can_generate_result_cards as _f
                return _f()
            except Exception:
                return False

        def can_access_graduates():
            try:
                from utils.access_control import can_access_graduates as _f
                return _f()
            except Exception:
                return False

        def branch_context():
            """Header branch switcher state."""
            try:
                from models import Branch
                from utils.branch_scope import is_central, viewing_branch_id
                if not session.get('logged_in'):
                    return {'is_central': False, 'branches': [], 'current': None}
                central = is_central()
                bid = viewing_branch_id()
                current = db.session.get(Branch, bid) if (bid and bid != -1) else None
                return {
                    'is_central': central,
                    'branches': Branch.query.filter_by(is_active=True)
                                .order_by(Branch.name).all() if central else [],
                    'current': current,
                }
            except Exception:
                return {'is_central': False, 'branches': [], 'current': None}

        def school_brand():
            """When signed in, the school's own identity replaces the app brand in
            the shell: its name + uploaded logo (falling back to the app brand),
            plus the signed-in person's name, role/position and branch."""
            base = {'logged_in': False, 'name': Config.APP_NAME, 'logo_url': '',
                    'user': '', 'role_label': '', 'branch': ''}
            try:
                from utils.school import logo_url
                from models import User, Branch, SchoolSettings
                if not session.get('logged_in'):
                    # Pre-login (e.g. the login page): show THIS school's name +
                    # logo, resolved from its subdomain. On the platform's own
                    # marketing/signup host (no school bound) keep the app brand.
                    if app.config.get('MULTI_TENANT'):
                        from utils.tenant_runtime import current_tenant
                        if current_tenant() is None:
                            return base
                    base['name'] = (SchoolSettings.get('school_name', '') or '').strip() or Config.APP_NAME
                    base['logo_url'] = logo_url()
                    return base
                from utils.branch_scope import is_central, viewing_branch_id
                from utils.branch_scope import is_central, viewing_branch_id
                name = (SchoolSettings.get('school_name', '') or '').strip() or Config.APP_NAME
                role = session.get('role', '') or ''
                role_label = {'super_admin': 'Super Admin', 'admin': 'Administrator',
                              'teacher': 'Teacher', 'staff': 'Staff',
                              'readonly': 'View Only'}.get(role, role.replace('_', ' ').title())
                uid = session.get('user_id')
                if uid:
                    u = db.session.get(User, uid)
                    if u:
                        role_label = u.get_display_role() or role_label
                if is_central():
                    branch = 'All branches'
                else:
                    bid = viewing_branch_id()
                    b = db.session.get(Branch, bid) if (bid and bid not in (None, -1)) else None
                    branch = b.name if b else ''
                return {'logged_in': True, 'name': name, 'logo_url': logo_url(),
                        'user': session.get('user', 'Admin'), 'role_label': role_label,
                        'branch': branch}
            except Exception:
                base['logged_in'] = bool(session.get('logged_in'))
                base['user'] = session.get('user', '')
                return base

        def time_travel():
            """For the admin session-view banner: the past session being viewed
            (or None), the live session, and the list to switch between."""
            try:
                from utils.access_control import is_admin
                if not is_admin():
                    return {'viewing': None, 'live': None, 'sessions': []}
                from utils.helpers import view_session_override
                live = AcademicSession.query.filter_by(is_active=True).first()
                return {'viewing': view_session_override(), 'live': live,
                        'sessions': AcademicSession.query.order_by(
                            AcademicSession.name.desc()).all()}
            except Exception:
                return {'viewing': None, 'live': None, 'sessions': []}

        def subscription_banner():
            """Trial / subscription state for the shell banner + a 'where to pay'
            link. Empty for the owner school and in single-school mode."""
            try:
                if not app.config.get('MULTI_TENANT') or not session.get('logged_in'):
                    return {}
                from utils.tenant_runtime import current_tenant
                from utils import billing
                t = current_tenant()
                if t is None or billing.is_owner(t):
                    return {}
                st = billing.status(t)
                return {'on_trial': st['on_trial'], 'active': st['active'],
                        'days_left': st['days_left'], 'url': url_for('billing.index')}
            except Exception:
                return {}

        return {
            'get_active_session': get_active_session,
            'get_active_term': get_active_term,
            'time_travel': time_travel,
            'subscription': subscription_banner(),
            'today': date.today(),
            'app_name': Config.APP_NAME,
            'csrf_token': csrf_token,
            'bundle_url': bundle_url,
            'csp_nonce': _csp_nonce_value(),
            'user_permissions': get_user_permissions(),
            'can_access_module': can_access_module,
            'can_write_module': can_write_module,
            'can_manage_users': can_manage_users(),
            'page_can_write': page_can_write(),
            'can_generate_timetable': can_generate_timetable(),
            'can_generate_result_cards': can_generate_result_cards(),
            'can_access_graduates': can_access_graduates(),
            'branch_ctx': branch_context(),
            'school_brand': school_brand(),
            'current_theme': current_theme(),
            'themes': THEMES,
            'password_rules': _password_rules(),
            'billing_nav': _billing_nav(),
        }
    
    # Custom Jinja filters
    @app.template_filter('format_date')
    def format_date_filter(value, format='%d %b %Y'):
        if value:
            return value.strftime(format)
        return ''
    
    @app.template_filter('fromjson')
    def fromjson_filter(value):
        import json
        try:
            return json.loads(value) if value else []
        except (ValueError, TypeError):
            return []

    @app.template_filter('question_html')
    def question_html_filter(value):
        """Render a Mock JAMB question/passage/option for the browser: HTML-safe,
        with ``[table: …]`` markers turned into real tables and ``\\( … \\)`` maths
        left for MathJax."""
        from utils.mathtext import question_html
        return question_html(value)

    @app.template_filter('num')
    def num_filter(value, dp=2):
        """Whole numbers without a trailing .0 (34 not 34.0); genuine decimals to
        ``dp`` places (34.3 -> 34.30). Blank/non-numeric values pass through."""
        from utils.numfmt import fmt_num
        return fmt_num(value, dp=dp, blank='')

    @app.template_filter('naira')
    def naira_filter(value):
        """Format a number as Naira, e.g. 25000 -> ₦25,000.00."""
        try:
            return '₦{:,.2f}'.format(float(value or 0))
        except (ValueError, TypeError):
            return '₦0.00'

    @app.template_filter('naira_short')
    def naira_short_filter(value):
        """Compact Naira for tight spaces (KPIs): 1250000 -> ₦1.25M, 9500 -> ₦9.5k."""
        try:
            n = float(value or 0)
        except (ValueError, TypeError):
            return '₦0'
        sign = '-' if n < 0 else ''
        n = abs(n)
        if n >= 1_000_000:
            return f'{sign}₦{n/1_000_000:.2f}M'
        if n >= 1_000:
            return f'{sign}₦{n/1_000:.1f}k'
        return f'{sign}₦{n:,.0f}'

    @app.template_filter('wa_intl')
    def wa_intl_filter(value):
        """Phone number in international digits for wa.me links (080… -> 23480…)."""
        from utils.comms import normalise_phone
        return normalise_phone(value)

    @app.template_filter('format_phone')
    def format_phone_filter(value):
        if value and len(value) == 11:
            return f"{value[:4]} {value[4:7]} {value[7:]}"
        return value or ''

    # Production hardening: proxy support, security headers, logging,
    # /healthz. Safe in every environment.
    from utils.production import harden
    harden(app, config_class)

    return app


# Create application instance (skipped under the test harness, which builds its
# own app against a temporary database).
if os.environ.get('POSYHUB_TESTING') != '1':
    app = create_app()


if __name__ == '__main__':
    # Local run (no Cloudflare): `python app.py`. Uses Flask's built-in server.
    # For the public demo (app + Cloudflare tunnel) run `python app_production.py`.
    port = int(os.environ.get('PORT', '5000'))
    app.run(debug=app.config.get('DEBUG', False), host='0.0.0.0', port=port)
