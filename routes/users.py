"""
User Management Routes
Handles user CRUD, role management, and teacher assignments
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from functools import wraps
from models import db, ClassArmAssignment, Term, Subject, User, Teacher, TeacherClassAssignment, TeacherSubjectAssignment
from utils.access_control import MODULES
from utils.audit import log_action

users_bp = Blueprint('users', __name__, url_prefix='/users')


def admin_required(f):
    """User/permission management is restricted to CENTRAL admins.

    A branch admin is full-featured within their branch but cannot manage
    accounts or permissions (which would let them escalate / cross branches).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please login to access this page.', 'error')
            return redirect(url_for('auth.login'))
        from utils.branch_scope import is_central
        role = session.get('role')
        if role not in ('super_admin', 'admin') or not is_central():
            flash('User management is for central administrators only.', 'error')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@users_bp.route('/')
@admin_required
def index():
    """List all users"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('users/index.html', users=users)


@users_bp.route('/matrix', methods=['GET', 'POST'])
@admin_required
def matrix():
    """Grid view of every non-admin user's module access, editable in one place."""
    users = User.query.order_by(User.username).all()
    editable = [u for u in users if u.role != 'admin']

    if request.method == 'POST':
        changed = 0
        for u in editable:
            before = (sorted(u.module_list), bool(u.view_only))
            selected = [m for m in request.form.getlist(f'mod_{u.id}') if m in MODULES]
            u.set_modules(selected)
            u.view_only = request.form.get(f'view_{u.id}') == 'on'
            after = (sorted(u.module_list), bool(u.view_only))
            if after != before:
                changed += 1
                log_action('user.permissions',
                           f'{u.username} (matrix): modules {before[0]}→{after[0]}, '
                           f'view_only {before[1]}→{after[1]}')
        db.session.commit()
        flash(f'Updated access for {changed} user(s).', 'success')
        return redirect(url_for('users.matrix'))

    return render_template('users/matrix.html', users=users, editable=editable,
                           modules=MODULES)


@users_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Add new user"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip() or None
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip() or None
        role = request.form.get('role', 'teacher')
        
        # Validation
        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('users.add_user'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('users.add_user'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('users.add_user'))
        
        # Check if username exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('users.add_user'))
        
        # Check if email exists
        if email and User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('users.add_user'))
        
        try:
            # Create user
            user = User(
                username=username,
                email=email,
                full_name=full_name,
                phone=phone,
                role=role,
                created_by_id=session.get('user_id')
            )
            user.set_password(password)
            # Fine-grained module access (admins always have full access).
            if role != 'admin':
                selected = [m for m in request.form.getlist('modules') if m in MODULES]
                user.set_modules(selected)
            user.view_only = request.form.get('view_only') == 'on'
            # Branch scope: central users see all branches; branch users one.
            user.scope = 'central' if request.form.get('scope') == 'central' else 'branch'
            user.branch_id = (None if user.scope == 'central'
                              else request.form.get('branch_id', type=int))
            user.section = request.form.get('section') or None
            user.stream = request.form.get('stream') or None
            db.session.add(user)
            db.session.flush()  # Get user ID

            # Create teacher profile if role is teacher
            if role == 'teacher':
                teacher = Teacher(
                    user_id=user.id,
                    employee_id=Teacher.generate_employee_id(),
                    branch_id=user.branch_id,
                    can_mark_attendance=request.form.get('can_mark_attendance') == 'on',
                    can_enter_results=request.form.get('can_enter_results') == 'on',
                    can_edit_results=request.form.get('can_edit_results') == 'on',
                    can_view_student_details=request.form.get('can_view_student_details') == 'on',
                    can_print_reports=request.form.get('can_print_reports') == 'on',
                )
                db.session.add(teacher)
            
            db.session.commit()
            log_action('user.create',
                       f'{username} (role={role}, modules={user.module_list or "role default"}, '
                       f'view_only={user.view_only})')
            flash(f'User "{username}" created successfully!', 'success')
            return redirect(url_for('users.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'error')
            return redirect(url_for('users.add_user'))
    
    from models import Branch
    from utils.role_presets import presets_for_form
    return render_template('users/add.html', modules=MODULES,
                           branches=Branch.query.order_by(Branch.name).all(),
                           presets=presets_for_form())


@users_bp.route('/<int:user_id>')
@admin_required
def view_user(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    return render_template('users/view.html', user=user, modules=MODULES)


@users_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Snapshot access-related fields so we can audit any change.
        before = (user.role, sorted(user.module_list), bool(user.view_only),
                  user.scope, user.branch_id)

        user.email = request.form.get('email', '').strip() or None
        user.full_name = request.form.get('full_name', '').strip()
        user.phone = request.form.get('phone', '').strip() or None
        user.role = request.form.get('role', user.role)
        user.is_active = request.form.get('is_active') == 'on'

        # Fine-grained module access (admins always have full access).
        if user.role == 'admin':
            user.set_modules(None)
        else:
            selected = [m for m in request.form.getlist('modules') if m in MODULES]
            user.set_modules(selected)
        user.view_only = request.form.get('view_only') == 'on'
        # Branch scope.
        user.scope = 'central' if request.form.get('scope') == 'central' else 'branch'
        user.branch_id = (None if user.scope == 'central'
                          else request.form.get('branch_id', type=int))
        user.section = request.form.get('section') or None
        user.stream = request.form.get('stream') or None
        
        # Update password if provided
        new_password = request.form.get('new_password', '')
        if new_password:
            if len(new_password) < 6:
                flash('Password must be at least 6 characters.', 'error')
                return redirect(url_for('users.edit_user', user_id=user_id))
            user.set_password(new_password)
        
        # Update teacher permissions if teacher
        if user.role == 'teacher':
            if not user.teacher_profile:
                teacher = Teacher(
                    user_id=user.id,
                    employee_id=Teacher.generate_employee_id()
                )
                db.session.add(teacher)
                db.session.flush()
            
            teacher = user.teacher_profile
            teacher.can_mark_attendance = request.form.get('can_mark_attendance') == 'on'
            teacher.can_enter_results = request.form.get('can_enter_results') == 'on'
            teacher.can_edit_results = request.form.get('can_edit_results') == 'on'
            teacher.can_view_student_details = request.form.get('can_view_student_details') == 'on'
            teacher.can_print_reports = request.form.get('can_print_reports') == 'on'
            teacher.branch_id = user.branch_id

        try:
            db.session.commit()
            after = (user.role, sorted(user.module_list), bool(user.view_only),
                     user.scope, user.branch_id)
            if after != before:
                log_action('user.permissions',
                           f'{user.username}: role {before[0]}→{after[0]}, '
                           f'modules {before[1]}→{after[1]}, '
                           f'view_only {before[2]}→{after[2]}, '
                           f'scope {before[3]}→{after[3]}, branch {before[4]}→{after[4]}')
            flash('User updated successfully!', 'success')
            return redirect(url_for('users.view_user', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'error')
    
    from models import Branch
    from utils.role_presets import presets_for_form
    return render_template('users/edit.html', user=user, modules=MODULES,
                           branches=Branch.query.order_by(Branch.name).all(),
                           presets=presets_for_form())


@users_bp.route('/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete user"""
    user = User.query.get_or_404(user_id)
    
    # Prevent deleting self
    if user.id == session.get('user_id'):
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('users.index'))
    
    # Prevent deleting super_admin if not super_admin
    current_user = User.query.get(session.get('user_id'))
    if user.is_super_admin and not current_user.is_super_admin:
        flash('Only super admins can delete other super admins.', 'error')
        return redirect(url_for('users.index'))
    
    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        flash(f'User "{username}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('users.index'))


@users_bp.route('/<int:user_id>/assign-class', methods=['GET', 'POST'])
@admin_required
def assign_class(user_id):
    """Assign teacher to a class as form teacher"""
    user = User.query.get_or_404(user_id)
    
    if not user.is_teacher or not user.teacher_profile:
        flash('User must be a teacher to assign classes.', 'error')
        return redirect(url_for('users.view_user', user_id=user_id))
    
    teacher = user.teacher_profile
    active_term = Term.query.filter_by(is_active=True).first()
    
    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id', type=int)
        is_form_teacher = request.form.get('is_form_teacher') == 'on'
        
        if not assignment_id:
            flash('Please select a class.', 'error')
            return redirect(url_for('users.assign_class', user_id=user_id))
        
        # Check if already assigned
        existing = TeacherClassAssignment.query.filter_by(
            teacher_id=teacher.id,
            class_arm_assignment_id=assignment_id
        ).first()
        
        if existing:
            existing.is_form_teacher = is_form_teacher
            existing.is_active = True
        else:
            assignment = TeacherClassAssignment(
                teacher_id=teacher.id,
                class_arm_assignment_id=assignment_id,
                is_form_teacher=is_form_teacher
            )
            db.session.add(assignment)
        
        try:
            db.session.commit()
            flash('Class assigned successfully!', 'success')
            return redirect(url_for('users.view_user', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    assignments = []
    if active_term:
        assignments = ClassArmAssignment.query.filter_by(term_id=active_term.id).all()
    
    return render_template('users/assign_class.html', 
                         user=user, 
                         teacher=teacher, 
                         assignments=assignments,
                         active_term=active_term)


@users_bp.route('/<int:user_id>/assign-subject', methods=['GET', 'POST'])
@admin_required
def assign_subject(user_id):
    """Assign teacher to teach a subject in a class"""
    user = User.query.get_or_404(user_id)
    
    if not user.is_teacher or not user.teacher_profile:
        flash('User must be a teacher to assign subjects.', 'error')
        return redirect(url_for('users.view_user', user_id=user_id))
    
    teacher = user.teacher_profile
    active_term = Term.query.filter_by(is_active=True).first()
    
    if request.method == 'POST':
        assignment_id = request.form.get('assignment_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        
        if not assignment_id or not subject_id:
            flash('Please select both class and subject.', 'error')
            return redirect(url_for('users.assign_subject', user_id=user_id))
        
        # Check if already assigned
        existing = TeacherSubjectAssignment.query.filter_by(
            teacher_id=teacher.id,
            class_arm_assignment_id=assignment_id,
            subject_id=subject_id
        ).first()
        
        if existing:
            existing.is_active = True
        else:
            assignment = TeacherSubjectAssignment(
                teacher_id=teacher.id,
                class_arm_assignment_id=assignment_id,
                subject_id=subject_id
            )
            db.session.add(assignment)
        
        try:
            db.session.commit()
            flash('Subject assigned successfully!', 'success')
            return redirect(url_for('users.view_user', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    assignments = []
    if active_term:
        assignments = ClassArmAssignment.query.filter_by(term_id=active_term.id).all()
    
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    
    return render_template('users/assign_subject.html',
                         user=user,
                         teacher=teacher,
                         assignments=assignments,
                         subjects=subjects,
                         active_term=active_term)


@users_bp.route('/assignment/<int:assignment_id>/remove', methods=['POST'])
@admin_required
def remove_assignment(assignment_id):
    """Remove a class or subject assignment"""
    assignment_type = request.form.get('type', 'class')
    user_id = request.form.get('user_id', type=int)
    
    if assignment_type == 'class':
        assignment = TeacherClassAssignment.query.get_or_404(assignment_id)
    else:
        assignment = TeacherSubjectAssignment.query.get_or_404(assignment_id)
    
    try:
        db.session.delete(assignment)
        db.session.commit()
        flash('Assignment removed successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('users.view_user', user_id=user_id))


@users_bp.route('/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_status(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    if user.id == session.get('user_id'):
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('users.index'))
    
    user.is_active = not user.is_active
    
    try:
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {status} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('users.index'))
