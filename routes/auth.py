"""
Enhanced Authentication routes for PosyHub
Supports both legacy password login and user-based login
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import hmac
from datetime import datetime, timedelta
from config import Config
from models import db, User
from utils.security import login_limiter, is_password_strong

auth_bp = Blueprint('auth', __name__)

# Login throttling via the shared DB-backed limiter, so the lockout holds across
# all gunicorn workers (an in-memory counter is bypassable by spreading attempts
# across processes).
def _client_key():
    return 'staff_login:' + (request.remote_addr or 'unknown')


def _account_key(ident):
    # Per-account throttle keyed by the submitted username, so a distributed
    # (IP-rotating) brute force against ONE known account still trips a lockout —
    # the IP key alone can't see it. Mirrors the parent/CBT portal pattern.
    return 'staff_login_acct:' + (ident or '').strip().lower()


def _login_locked(ident=None):
    if login_limiter.is_rate_limited(_client_key(), Config.LOGIN_MAX_ATTEMPTS,
                                     Config.LOGIN_LOCKOUT_MINUTES):
        return True
    if ident and login_limiter.is_rate_limited(
            _account_key(ident), Config.LOGIN_ACCT_MAX_ATTEMPTS, Config.LOGIN_LOCKOUT_MINUTES):
        return True
    return False


def _record_login_failure(ident=None):
    login_limiter.record_attempt(_client_key())
    if ident:
        login_limiter.record_attempt(_account_key(ident))


def _clear_login_failures(ident=None):
    login_limiter.clear_attempts(_client_key())
    if ident:
        login_limiter.clear_attempts(_account_key(ident))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login - supports username/password or legacy password"""
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if _login_locked(username):
            flash(f'Too many failed attempts. Try again in {Config.LOGIN_LOCKOUT_MINUTES} minutes.', 'error')
            return redirect(url_for('auth.login'))

        # DoS guard: never feed an unbounded password to scrypt (a multi-MB
        # value would pin the single worker). Treat as a normal failed attempt.
        from utils.security import MAX_PASSWORD_LEN
        if len(password) > MAX_PASSWORD_LEN:
            _record_login_failure(username or None)
            flash('Invalid credentials. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        # Try user-based login first
        if username:
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                if not user.is_active:
                    # Don't clear the throttle for a deactivated account.
                    flash('Your account has been deactivated. Contact administrator.', 'error')
                    return redirect(url_for('auth.login'))
                _clear_login_failures(username)

                # Successful user login. Drop any pre-login session and mint a
                # fresh CSRF token so a fixed session/token can't be reused.
                session.clear()
                session['logged_in'] = True
                session['user_id'] = user.id
                session['user'] = user.full_name or user.username
                session['role'] = user.role
                from utils.branch_scope import set_session_scope
                from utils.org_scope import set_session_org
                set_session_scope(user)
                set_session_org(user)
                if user.theme:
                    session['theme'] = user.theme
                session['must_change_password'] = bool(user.must_change_password)
                from utils.csrf import rotate_csrf_token
                rotate_csrf_token()
                session.permanent = True
                
                # Update last login
                user.last_login = datetime.now()
                db.session.commit()
                
                flash(f'Welcome back, {user.full_name or user.username}!', 'success')
                return redirect(url_for('main.dashboard'))
            
            elif user:
                _record_login_failure(username)
                # Generic message — don't reveal that the username exists.
                flash('Invalid credentials. Please try again.', 'error')
                return redirect(url_for('auth.login'))

        # Legacy admin password login — only when explicitly enabled AND a
        # password is configured. There is no built-in/default password, so an
        # unconfigured deployment cannot be logged into via this path.
        if (Config.ENABLE_LEGACY_LOGIN and Config.ADMIN_PASSWORD and password
                and hmac.compare_digest(password, Config.ADMIN_PASSWORD)):
            _clear_login_failures()
            session.clear()           # prevent session fixation
            session['logged_in'] = True
            session['user'] = 'Admin'
            session['role'] = 'admin'
            from utils.branch_scope import set_session_scope
            from utils.org_scope import set_session_org
            set_session_scope(None)   # legacy admin is central
            set_session_org(None)
            from utils.csrf import rotate_csrf_token
            rotate_csrf_token()
            session.permanent = True
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('main.dashboard'))

        _record_login_failure(username or None)
        flash('Invalid credentials. Please try again.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Self-service reset: emails a single-use, time-limited reset LINK. The live
    password is left intact until the user actually sets a new one (so triggering
    a reset for someone else can't lock them out)."""
    from utils import mailer
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        # Throttle reset abuse (account probing + email bombing) by client IP.
        rkey = 'forgot_pw:' + (request.remote_addr or 'unknown')
        if login_limiter.is_rate_limited(rkey, max_attempts=8, window_minutes=15):
            flash('Too many reset requests. Please try again later.', 'error')
            return redirect(url_for('auth.login'))
        login_limiter.record_attempt(rkey)
        ident = (request.form.get('identifier') or '').strip()
        if ident:
            user = User.query.filter((User.username == ident) | (User.email == ident)).first()
            if user and user.email and user.is_active and mailer.is_configured():
                raw = user.set_reset_token(ttl_minutes=60)   # password untouched
                db.session.commit()
                link = url_for('auth.reset_password', uid=user.id, token=raw, _external=True)
                mailer.send_email(user.email, 'EduSyncra password reset',
                                  f'Hello {user.full_name or user.username},\n\n'
                                  f'We received a request to reset your password. Use this '
                                  f'link within 1 hour to set a new one:\n\n{link}\n\n'
                                  f'If you did not request this, you can ignore this email — '
                                  f'your current password still works.\n')
        # Generic response (avoid revealing whether an account exists).
        flash('If a matching account exists, a reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<int:uid>/<token>', methods=['GET', 'POST'])
def reset_password(uid, token):
    """Set a new password via a single-use, time-limited token from the email."""
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    user = User.query.get(uid)
    if not user or not user.is_active or not user.check_reset_token(token):
        flash('This reset link is invalid or has expired. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        pw = request.form.get('password') or ''
        confirm = request.form.get('confirm') or ''
        if pw != confirm:
            flash('The two passwords do not match.', 'error')
            return render_template('auth/reset_password.html', uid=uid, token=token)
        ok, msg = is_password_strong(pw)
        if not ok:
            flash(msg, 'error')
            return render_template('auth/reset_password.html', uid=uid, token=token)
        user.set_password(pw)
        user.clear_reset_token()          # single use
        user.must_change_password = False
        db.session.commit()
        flash('Your password has been reset. Please sign in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', uid=uid, token=token)


@auth_bp.route('/logout')
def logout():
    """Handle user logout"""
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Allow logged in user to change their password"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')
    if not user_id:
        flash('Password change not available for legacy login.', 'info')
        return redirect(url_for('main.dashboard'))
    
    user = db.session.get(User, user_id)
    if not user:
        return redirect(url_for('auth.logout'))
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('auth.change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('auth.change_password'))
        
        ok, msg = is_password_strong(new_password)
        if not ok:
            flash(msg, 'error')
            return redirect(url_for('auth.change_password'))
        
        user.set_password(new_password)
        user.must_change_password = False
        db.session.commit()
        session.pop('must_change_password', None)

        flash('Password changed successfully!', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('auth/change_password.html', user=user)


def get_current_user():
    """Get the current logged-in user object"""
    user_id = session.get('user_id')
    if user_id:
        return db.session.get(User, user_id)
    return None


def is_admin():
    """Check if current user is admin"""
    role = session.get('role')
    return role in ('super_admin', 'admin')


def is_teacher():
    """Check if current user is teacher"""
    role = session.get('role')
    return role == 'teacher'


def can_access_class(class_arm_assignment_id):
    """Check if current user can access a specific class"""
    if is_admin():
        return True
    
    user = get_current_user()
    if user and user.is_teacher and user.teacher_profile:
        return user.teacher_profile.can_access_class(class_arm_assignment_id)
    
    return False
