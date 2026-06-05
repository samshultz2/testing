"""
Enhanced Authentication routes for PosyHub
Supports both legacy password login and user-based login
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from config import Config
from models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login - supports username/password or legacy password"""
    if session.get('logged_in'):
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Try user-based login first
        if username:
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
                if not user.is_active:
                    flash('Your account has been deactivated. Contact administrator.', 'error')
                    return redirect(url_for('auth.login'))
                
                # Successful user login
                session['logged_in'] = True
                session['user_id'] = user.id
                session['user'] = user.full_name or user.username
                session['role'] = user.role
                session.permanent = True
                
                # Update last login
                user.last_login = datetime.now()
                db.session.commit()
                
                flash(f'Welcome back, {user.full_name or user.username}!', 'success')
                return redirect(url_for('main.dashboard'))
            
            elif user:
                flash('Invalid password.', 'error')
                return redirect(url_for('auth.login'))
        
        # Legacy admin password login (for backwards compatibility)
        if password == Config.ADMIN_PASSWORD:
            session['logged_in'] = True
            session['user'] = 'Admin'
            session['role'] = 'admin'
            session.permanent = True
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('main.dashboard'))
        
        flash('Invalid credentials. Please try again.', 'error')
    
    return render_template('auth/login.html')


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
        db.session.commit()
        
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
