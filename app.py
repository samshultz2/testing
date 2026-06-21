"""
EduSyncra School Management System
Main Flask application entry point
"""
import os
import secrets
from flask import Flask, session
from config import Config, get_config
from models import db, init_db
from routes import auth_bp, main_bp, academics_bp, attendance_bp, results_bp, reports_bp, settings_bp, subjects_bp, timetable_bp, promotion_bp, users_bp
from routes.generator import generator_bp
from routes.contributions import contributions_bp
from routes.mock_jamb import mock_jamb_bp
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


def _start_scheduled_messages_worker(app):
    """Daemon thread that every minute sends any due scheduled SMS campaigns."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    import threading
    import time

    def _loop():
        last_daily = None
        while True:
            time.sleep(60)
            try:
                with app.app_context():
                    from utils.comms import dispatch_due_scheduled
                    dispatch_due_scheduled()
                    today = time.strftime('%Y%m%d')
                    if today != last_daily:
                        from utils.reminders import run_fee_reminders
                        run_fee_reminders(app)   # opt-in; no-op unless enabled
                        last_daily = today
            except Exception:
                pass

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
    app.register_blueprint(mock_waec_bp)
    app.register_blueprint(users_bp)
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
    
    # Initialize database
    with app.app_context():
        init_db(app)

    # Enable CSRF protection for all state-changing requests
    from utils.csrf import init_csrf
    init_csrf(app)

    # Fine-grained module access for non-admin users.
    from utils.access_control import (enforce_module_access, enforce_read_only,
                                       enforce_write_level, enforce_subsection_access,
                                       enforce_idle_timeout, enforce_password_change)
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

        return {
            'get_active_session': get_active_session,
            'get_active_term': get_active_term,
            'today': date.today(),
            'app_name': Config.APP_NAME,
            'csrf_token': csrf_token,
            'user_permissions': get_user_permissions(),
            'can_access_module': can_access_module,
            'can_write_module': can_write_module,
            'can_manage_users': can_manage_users(),
            'page_can_write': page_can_write(),
            'can_generate_timetable': can_generate_timetable(),
            'can_generate_result_cards': can_generate_result_cards(),
            'branch_ctx': branch_context(),
            'current_theme': current_theme(),
            'themes': THEMES,
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
