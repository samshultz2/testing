"""
Enhanced Authentication routes for PosyHub
Supports both legacy password login and user-based login
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
from collections import defaultdict
from config import Config
from models import db, User

auth_bp = Blueprint('auth', __name__)

# Simple in-memory login throttling (per client address).
_login_failures = defaultdict(list)


def _client_key():
    return request.remote_addr or 'unknown'


def _login_locked():
    cutoff = datetime.now() - timedelta(minutes=Config.LOGIN_LOCKOUT_MINUTES)
    recent = [t for t in _login_failures[_client_key()] if t > cutoff]
    _login_failures[_client_key()] = recent
    return len(recent) >= Config.LOGIN_MAX_ATTEMPTS


def _record_login_failure():
    _login_failures[_client_key()].append(datetime.now())


def _clear_login_failures():
    _login_failures.pop(_client_key(), None)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login - supports username/password or legacy password"""
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if _login_locked():
            flash(f'Too many failed attempts. Try again in {Config.LOGIN_LOCKOUT_MINUTES} minutes.', 'error')
            return redirect(url_for('auth.login'))

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Try user-based login first
        if username:
            user = User.query.filter_by(username=username).first()

            if user and user.check_password(password):
                _clear_login_failures()
                if not user.is_active:
                    flash('Your account has been deactivated. Contact administrator.', 'error')
                    return redirect(url_for('auth.login'))
                
                # Successful user login
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
                session.permanent = True
                
                # Update last login
                user.last_login = datetime.now()
                db.session.commit()
                
                flash(f'Welcome back, {user.full_name or user.username}!', 'success')
                return redirect(url_for('main.dashboard'))
            
            elif user:
                _record_login_failure()
                flash('Invalid password.', 'error')
                return redirect(url_for('auth.login'))

        # Legacy admin password login (only when explicitly enabled)
        if Config.ENABLE_LEGACY_LOGIN and password and password == Config.ADMIN_PASSWORD:
            _clear_login_failures()
            session['logged_in'] = True
            session['user'] = 'Admin'
            session['role'] = 'admin'
            from utils.branch_scope import set_session_scope
            from utils.org_scope import set_session_org
            set_session_scope(None)   # legacy admin is central
            set_session_org(None)
            session.permanent = True
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('main.dashboard'))

        _record_login_failure()
        flash('Invalid credentials. Please try again.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Self-service reset: emails a one-time password the user must change."""
    from utils import mailer
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        ident = (request.form.get('identifier') or '').strip()
        if ident:
            user = User.query.filter((User.username == ident) | (User.email == ident)).first()
            if user and user.email and user.is_active and mailer.is_configured():
                import secrets
                temp = secrets.token_urlsafe(6)
                user.set_password(temp)
                user.must_change_password = True
                db.session.commit()
                school = 'PosyHub'
                mailer.send_email(user.email, f'{school} password reset',
                                  f'Hello {user.full_name or user.username},\n\n'
                                  f'Your temporary password is: {temp}\n\n'
                                  f'Please sign in and set a new password.\n')
        # Generic response (avoid revealing whether an account exists).
        flash('If a matching account exists, a reset email has been sent.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html')


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
    
    user = User.query.get(user_id)
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
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'error')
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
        return User.query.get(user_id)
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
