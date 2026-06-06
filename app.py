"""
PosyHub Student Management System
Main Flask application entry point
"""
import os
import secrets
from flask import Flask, session
from config import Config
from models import db, init_db
from routes import auth_bp, main_bp, academics_bp, attendance_bp, results_bp, reports_bp, settings_bp, subjects_bp, timetable_bp, promotion_bp, users_bp
from routes.generator import generator_bp
from routes.contributions import contributions_bp
from routes.mock_jamb import mock_jamb_bp
from routes.finance import finance_bp


def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Ensure instance folder exists
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, 'instance'), exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)
    
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
    app.register_blueprint(users_bp)
    app.register_blueprint(finance_bp)
    
    # Initialize database
    with app.app_context():
        init_db(app)

    # Enable CSRF protection for all state-changing requests
    from utils.csrf import init_csrf
    init_csrf(app)

    # Friendly error pages
    from utils.errors import register_error_handlers
    register_error_handlers(app)

    # Keep a rolling daily backup of the database
    from utils.backup import auto_backup
    auto_backup(app)

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
        
        return {
            'get_active_session': get_active_session,
            'get_active_term': get_active_term,
            'today': date.today(),
            'app_name': Config.APP_NAME,
            'csrf_token': csrf_token,
            'user_permissions': get_user_permissions()
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

    @app.template_filter('format_phone')
    def format_phone_filter(value):
        if value and len(value) == 11:
            return f"{value[:4]} {value[4:7]} {value[7:]}"
        return value or ''
    
    return app


# Create application instance (skipped under the test harness, which builds its
# own app against a temporary database).
if os.environ.get('POSYHUB_TESTING') != '1':
    app = create_app()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
