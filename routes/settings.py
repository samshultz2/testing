"""
Settings, Backup, and Configuration routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response, send_file
from datetime import datetime
import os
import shutil
import json
from models import (
    db, SchoolSettings, GradeScale, AssessmentType, TimetableSlot,
    Student, AcademicSession, Term, User
)
from utils.helpers import login_required
from utils.access_control import admin_required, central_admin_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


# ============================================================================
# SCHOOL SETTINGS
# ============================================================================

@settings_bp.route('/')
@login_required
def index():
    """Settings main page"""
    settings = SchoolSettings.query.all()
    settings_dict = {s.key: s.value for s in settings}

    return render_template('settings/index.html', settings=settings_dict)


# ---------------------------------------------------------------------------
# Branches (multi-branch support)
# ---------------------------------------------------------------------------

@settings_bp.route('/branches')
@central_admin_required
def branches():
    from models import Branch
    rows = Branch.query.order_by(Branch.is_default.desc(), Branch.name).all()
    return render_template('settings/branches.html', branches=rows)


@settings_bp.route('/branches/add', methods=['POST'])
@central_admin_required
def add_branch():
    from models import db, Branch
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Branch name is required.', 'error')
        return redirect(url_for('settings.branches'))
    if Branch.query.filter_by(name=name).first():
        flash('A branch with that name already exists.', 'error')
        return redirect(url_for('settings.branches'))
    first = Branch.query.count() == 0
    db.session.add(Branch(
        name=name,
        code=(request.form.get('code') or '').strip() or None,
        address=(request.form.get('address') or '').strip() or None,
        phone=(request.form.get('phone') or '').strip() or None,
        is_default=first))   # the very first branch is the default
    db.session.commit()
    from utils.audit import log_action
    log_action('branch.create', target_type='branch', target_label=name)
    flash(f'Branch "{name}" added.', 'success')
    return redirect(url_for('settings.branches'))


@settings_bp.route('/branches/<int:branch_id>/edit', methods=['POST'])
@central_admin_required
def edit_branch(branch_id):
    from models import db, Branch
    b = db.get_or_404(Branch, branch_id)
    b.name = (request.form.get('name') or b.name).strip()
    b.code = (request.form.get('code') or '').strip() or None
    b.address = (request.form.get('address') or '').strip() or None
    b.phone = (request.form.get('phone') or '').strip() or None
    b.is_active = request.form.get('is_active') == 'on'
    if request.form.get('make_default') == 'on' and not b.is_default:
        Branch.query.update({Branch.is_default: False})
        b.is_default = True
        b.is_active = True
    db.session.commit()
    from utils.audit import log_action
    log_action('branch.update', target=b)
    flash('Branch updated.', 'success')
    return redirect(url_for('settings.branches'))


@settings_bp.route('/school', methods=['GET', 'POST'])
@login_required
def school_settings():
    """School information settings"""
    if request.method == 'POST':
        try:
            # Update school settings
            SchoolSettings.set('school_name', request.form.get('school_name', ''), 'string', 'Name of the school')
            SchoolSettings.set('school_address', request.form.get('school_address', ''), 'string', 'School address')
            SchoolSettings.set('school_phone', request.form.get('school_phone', ''), 'string', 'School phone number')
            SchoolSettings.set('school_email', request.form.get('school_email', ''), 'string', 'School email')
            SchoolSettings.set('school_motto', request.form.get('school_motto', ''), 'string', 'School motto')
            SchoolSettings.set('next_term_fees', request.form.get('next_term_fees', ''), 'string', 'Next term fees (shown on report cards)')
            SchoolSettings.set('next_term_begins', request.form.get('next_term_begins', ''), 'string', 'Next term resumption date (shown on report cards)')
            tz = (request.form.get('timezone') or '').strip()
            if tz:
                SchoolSettings.set('timezone', tz, 'string', 'Site-wide timezone')
                from utils.timeutil import clear_cache
                clear_cache()

            flash('School settings updated!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        
        return redirect(url_for('settings.school_settings'))
    
    settings = {s.key: s.value for s in SchoolSettings.query.all()}
    from utils.timeutil import all_timezones, get_timezone
    return render_template('settings/school.html', settings=settings,
        timezones=all_timezones(), current_tz=get_timezone())


@settings_bp.route('/academic', methods=['GET', 'POST'])
@login_required
def academic_settings():
    """Academic and timetable settings"""
    if request.method == 'POST':
        try:
            SchoolSettings.set('school_day_start', request.form.get('school_day_start', '08:20'), 'string')
            SchoolSettings.set('school_day_end', request.form.get('school_day_end', '14:10'), 'string')
            SchoolSettings.set('period_duration', request.form.get('period_duration', '40'), 'int')
            SchoolSettings.set('break_duration', request.form.get('break_duration', '30'), 'int')
            SchoolSettings.set('periods_per_day', request.form.get('periods_per_day', '8'), 'int')
            SchoolSettings.set('promotion_threshold', request.form.get('promotion_threshold', '50'), 'float')
            SchoolSettings.set('pass_mark', request.form.get('pass_mark', '50'), 'int')
            
            flash('Academic settings updated!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
        
        return redirect(url_for('settings.academic_settings'))
    
    settings = {s.key: s.value for s in SchoolSettings.query.all()}
    return render_template('settings/academic.html', settings=settings)


# ============================================================================
# GRADE SCALE
# ============================================================================

@settings_bp.route('/grades')
@login_required
def grades_list():
    """List grade scale"""
    grades = GradeScale.query.order_by(GradeScale.order).all()
    return render_template('settings/grades.html', grades=grades)


@settings_bp.route('/grades/save', methods=['POST'])
@login_required
def save_grades():
    """Save grade scale"""
    try:
        # Get form data
        grades = request.form.getlist('grade[]')
        min_scores = request.form.getlist('min_score[]')
        max_scores = request.form.getlist('max_score[]')
        remarks = request.form.getlist('remark[]')
        
        # Delete existing grades
        GradeScale.query.delete()
        
        # Add new grades
        for i, grade in enumerate(grades):
            if grade.strip():
                db.session.add(GradeScale(
                    grade=grade.strip(),
                    min_score=int(min_scores[i]) if min_scores[i] else 0,
                    max_score=int(max_scores[i]) if max_scores[i] else 100,
                    remark=remarks[i].strip() if i < len(remarks) else '',
                    order=i + 1
                ))
        
        db.session.commit()
        flash('Grade scale saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('settings.grades_list'))


# ============================================================================
# BEHAVIOURAL TRAITS
# ============================================================================

def _slugify(text):
    import re
    s = re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')
    return s or 'trait'


@settings_bp.route('/traits')
@login_required
def traits_list():
    from models import BehaviouralTrait
    traits = BehaviouralTrait.query.order_by(BehaviouralTrait.order, BehaviouralTrait.id).all()
    return render_template('settings/traits.html', traits=traits)


@settings_bp.route('/traits/save', methods=['POST'])
@login_required
def save_traits():
    from models import BehaviouralTrait
    keys = request.form.getlist('key[]')
    labels = request.form.getlist('label[]')
    active_set = set(request.form.getlist('active[]'))   # values are row indices
    seen = set()
    try:
        for i, label in enumerate(labels):
            label = label.strip()
            if not label:
                continue
            key = (keys[i].strip() if i < len(keys) and keys[i].strip() else _slugify(label))
            # avoid colliding with a different existing trait's key
            base, n = key, 1
            while key in seen:
                n += 1; key = f'{base}_{n}'
            is_active = str(i) in active_set
            trait = BehaviouralTrait.query.filter_by(key=key).first()
            if trait:
                trait.label, trait.order, trait.is_active = label, i, is_active
            else:
                db.session.add(BehaviouralTrait(key=key, label=label, order=i, is_active=is_active))
            seen.add(key)
        # Traits dropped from the form are deactivated (keys kept so ratings survive).
        for t in BehaviouralTrait.query.all():
            if t.key not in seen:
                t.is_active = False
        db.session.commit()
        flash('Behavioural traits saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('settings.traits_list'))


# ============================================================================
# ASSESSMENT TYPES
# ============================================================================

@settings_bp.route('/assessments')
@login_required
def assessments_list():
    """List assessment types"""
    assessments = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    total_max = sum(a.max_score for a in assessments)
    return render_template('settings/assessments.html', assessments=assessments, total_max=total_max)


@settings_bp.route('/assessments/save', methods=['POST'])
@login_required
def save_assessments():
    """Save assessment types"""
    try:
        names = request.form.getlist('name[]')
        short_names = request.form.getlist('short_name[]')
        max_scores = request.form.getlist('max_score[]')
        
        # Deactivate all existing
        AssessmentType.query.update({AssessmentType.is_active: False})
        
        # Add/update assessment types
        for i, name in enumerate(names):
            if name.strip():
                # Check if exists
                existing = AssessmentType.query.filter_by(name=name.strip()).first()
                if existing:
                    existing.short_name = short_names[i].strip() if i < len(short_names) else ''
                    existing.max_score = int(max_scores[i]) if i < len(max_scores) and max_scores[i] else 10
                    existing.order = i + 1
                    existing.is_active = True
                else:
                    db.session.add(AssessmentType(
                        name=name.strip(),
                        short_name=short_names[i].strip() if i < len(short_names) else '',
                        max_score=int(max_scores[i]) if i < len(max_scores) and max_scores[i] else 10,
                        order=i + 1,
                        is_active=True
                    ))
        
        db.session.commit()
        flash('Assessment types saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('settings.assessments_list'))


# ============================================================================
# TIMETABLE SLOTS
# ============================================================================

@settings_bp.route('/timetable-slots')
@login_required
def timetable_slots():
    """Manage timetable slots/periods"""
    slots = TimetableSlot.query.filter_by(is_active=True).order_by(TimetableSlot.order).all()
    settings = {s.key: s.value for s in SchoolSettings.query.all()}
    return render_template('settings/timetable_slots.html', slots=slots, settings=settings)


@settings_bp.route('/timetable-slots/generate', methods=['POST'])
@login_required
def generate_timetable_slots():
    """Auto-generate timetable slots based on settings"""
    try:
        from datetime import timedelta, datetime as dt
        
        # Get settings
        start_time_str = SchoolSettings.get('school_day_start', '08:20')
        period_duration = SchoolSettings.get('period_duration', 40)
        break_duration = SchoolSettings.get('break_duration', 30)
        periods_per_day = SchoolSettings.get('periods_per_day', 8)
        
        # Parse start time
        start_hour, start_min = map(int, start_time_str.split(':'))
        current_time = dt(2000, 1, 1, start_hour, start_min)
        
        # Delete existing slots
        TimetableSlot.query.delete()
        
        slot_number = 1
        order = 1
        
        for i in range(periods_per_day):
            # Add period
            end_time = current_time + timedelta(minutes=period_duration)
            db.session.add(TimetableSlot(
                slot_number=slot_number,
                name=f'Period {slot_number}',
                start_time=current_time.time(),
                end_time=end_time.time(),
                is_break=False,
                duration_minutes=period_duration,
                order=order
            ))
            current_time = end_time
            slot_number += 1
            order += 1
            
            # Add break after period 4 and period 6 (configurable)
            if i == 3 or i == 5:  # After 4th and 6th periods
                break_end = current_time + timedelta(minutes=break_duration)
                break_name = 'Short Break' if i == 3 else 'Long Break'
                db.session.add(TimetableSlot(
                    slot_number=0,  # 0 for breaks
                    name=break_name,
                    start_time=current_time.time(),
                    end_time=break_end.time(),
                    is_break=True,
                    duration_minutes=break_duration,
                    order=order
                ))
                current_time = break_end
                order += 1
        
        db.session.commit()
        flash(f'{periods_per_day} periods and 2 breaks generated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('settings.timetable_slots'))


@settings_bp.route('/timetable-slots/save', methods=['POST'])
@login_required
def save_timetable_slots():
    """Save timetable slots"""
    try:
        from datetime import time
        
        slot_ids = request.form.getlist('slot_id[]')
        names = request.form.getlist('name[]')
        start_times = request.form.getlist('start_time[]')
        end_times = request.form.getlist('end_time[]')
        is_breaks = request.form.getlist('is_break[]')
        
        for i, slot_id in enumerate(slot_ids):
            if slot_id:
                slot = db.session.get(TimetableSlot, int(slot_id))
                if slot:
                    slot.name = names[i] if i < len(names) else slot.name
                    
                    if i < len(start_times) and start_times[i]:
                        h, m = map(int, start_times[i].split(':'))
                        slot.start_time = time(h, m)
                    
                    if i < len(end_times) and end_times[i]:
                        h, m = map(int, end_times[i].split(':'))
                        slot.end_time = time(h, m)
                    
                    slot.is_break = str(i) in is_breaks
                    slot.order = i + 1
        
        db.session.commit()
        flash('Timetable slots updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('settings.timetable_slots'))


# ============================================================================
# DATABASE BACKUP & RESTORE
# ============================================================================

@settings_bp.route('/backup')
@login_required
def backup_page():
    """Backup and restore page"""
    # Get database info
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'school.db')
    db_size = 0
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path)
    
    # Get record counts
    counts = {
        'students': Student.query.count(),
        'sessions': AcademicSession.query.count(),
        'terms': Term.query.count(),
        'users': User.query.count()
    }
    
    from flask import current_app
    from utils.backup import list_backups
    return render_template('settings/backup.html', db_size=db_size, counts=counts,
                           backups=list_backups(current_app))


@settings_bp.route('/backup/create', methods=['POST'])
@admin_required
def create_backup():
    from flask import current_app
    from utils.backup import make_backup
    path = make_backup(current_app)
    if path:
        flash('Backup created.', 'success')
    else:
        flash('Could not create backup.', 'error')
    return redirect(url_for('settings.backup_page'))


@settings_bp.route('/backup/file/<path:name>')
@admin_required
def download_backup_file(name):
    import os as _os
    from flask import current_app
    safe = _os.path.basename(name)
    if not (safe.startswith('school_') and safe.endswith(('.db', '.sql'))):
        flash('Invalid backup file.', 'error')
        return redirect(url_for('settings.backup_page'))
    path = _os.path.join(current_app.config['BASE_DIR'], 'instance', 'backups', safe)
    if not _os.path.exists(path):
        flash('Backup not found.', 'error')
        return redirect(url_for('settings.backup_page'))
    mimetype = 'application/sql' if safe.endswith('.sql') else 'application/x-sqlite3'
    return send_file(path, as_attachment=True, download_name=safe, mimetype=mimetype)


@settings_bp.route('/backup/download')
@login_required
def download_backup():
    """Download database backup"""
    try:
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'school.db')
        
        if not os.path.exists(db_path):
            flash('Database file not found!', 'error')
            return redirect(url_for('settings.backup_page'))
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'school_backup_{timestamp}.db'
        
        return send_file(
            db_path,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/x-sqlite3'
        )
    except Exception as e:
        flash(f'Error creating backup: {str(e)}', 'error')
        return redirect(url_for('settings.backup_page'))


@settings_bp.route('/backup/export-json')
@login_required
def export_json():
    """Export all data to JSON"""
    try:
        from models import (
            Student, ParentContact, AcademicSession, SchoolSettings, GradeScale, AssessmentType
        )
        
        data = {
            'export_date': datetime.now().isoformat(),
            'school_settings': [{
                'key': s.key, 'value': s.value, 'value_type': s.value_type
            } for s in SchoolSettings.query.all()],
            'grade_scales': [{
                'grade': g.grade, 'min_score': g.min_score, 'max_score': g.max_score,
                'remark': g.remark, 'order': g.order
            } for g in GradeScale.query.all()],
            'assessment_types': [{
                'name': a.name, 'short_name': a.short_name, 'max_score': a.max_score, 'order': a.order
            } for a in AssessmentType.query.filter_by(is_active=True).all()],
            'students': [{
                'student_id': s.student_id, 'first_name': s.first_name, 'middle_name': s.middle_name,
                'surname': s.surname, 'gender': s.gender,
                'date_of_birth': s.date_of_birth.isoformat() if s.date_of_birth else None,
                'religion': s.religion, 'home_address': s.home_address, 'hobbies': s.hobbies,
                'is_active': s.is_active
            } for s in Student.query.all()],
            'parent_contacts': [{
                'student_id': p.student.student_id, 'phone_number': p.phone_number,
                'relationship': p.relationship, 'name': p.name, 'is_primary': p.is_primary
            } for p in ParentContact.query.all()],
            'academic_sessions': [{
                'name': s.name,
                'start_date': s.start_date.isoformat() if s.start_date else None,
                'end_date': s.end_date.isoformat() if s.end_date else None,
                'is_active': s.is_active
            } for s in AcademicSession.query.all()],
        }
        
        # Create JSON response
        json_str = json.dumps(data, indent=2)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        return Response(
            json_str,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=school_export_{timestamp}.json'}
        )
    except Exception as e:
        flash(f'Error exporting data: {str(e)}', 'error')
        return redirect(url_for('settings.backup_page'))


@settings_bp.route('/backup/restore', methods=['POST'])
@login_required
def restore_backup():
    """Restore database from an uploaded backup (SQLite .db or Postgres .sql)."""
    import tempfile
    from flask import current_app
    from utils.backup import restore_database

    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('settings.backup_page'))

    file = request.files['file']
    if not file.filename:
        flash('No file selected.', 'error')
        return redirect(url_for('settings.backup_page'))

    if not file.filename.lower().endswith(('.db', '.sql')):
        flash('Please upload a .db (SQLite) or .sql (PostgreSQL) backup file.', 'error')
        return redirect(url_for('settings.backup_page'))

    # Stage the upload to a temp file, then let the backend-aware helper apply it.
    suffix = '.sql' if file.filename.lower().endswith('.sql') else '.db'
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        file.save(tmp_path)
        ok, message = restore_database(current_app, tmp_path, file.filename)
        flash(message, 'success' if ok else 'error')
    except Exception as e:
        flash(f'Error restoring backup: {str(e)}', 'error')
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return redirect(url_for('settings.backup_page'))


# ============================================================================
# USER MANAGEMENT
# ============================================================================

@settings_bp.route('/users')
@login_required
def users_list():
    """List all users"""
    users = User.query.order_by(User.role, User.username).all()
    return render_template('settings/users.html', users=users)


@settings_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    """Add new user"""
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip().lower()
            email = request.form.get('email', '').strip().lower()
            full_name = request.form.get('full_name', '').strip()
            password = request.form.get('password', '')
            role = request.form.get('role', 'teacher')
            
            if not username or not password:
                flash('Username and password are required.', 'error')
                return redirect(url_for('settings.add_user'))
            
            # Check for duplicates
            if User.query.filter_by(username=username).first():
                flash('Username already exists.', 'error')
                return redirect(url_for('settings.add_user'))
            
            user = User(
                username=username,
                email=email or None,
                full_name=full_name or None,
                role=role
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash(f'User {username} created!', 'success')
            return redirect(url_for('settings.users_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('settings/add_user.html')


@settings_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """Edit user"""
    user = db.get_or_404(User, user_id)
    
    if request.method == 'POST':
        try:
            user.email = request.form.get('email', '').strip().lower() or None
            user.full_name = request.form.get('full_name', '').strip() or None
            user.role = request.form.get('role', 'teacher')
            user.is_active = request.form.get('is_active') == 'on'
            
            # Update password if provided
            new_password = request.form.get('password', '').strip()
            if new_password:
                user.set_password(new_password)
            
            db.session.commit()
            flash('User updated!', 'success')
            return redirect(url_for('settings.users_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('settings/edit_user.html', user=user)


@settings_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete user"""
    user = db.get_or_404(User, user_id)
    
    # Prevent deleting last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin', is_active=True).count()
        if admin_count <= 1:
            flash('Cannot delete the last admin user!', 'error')
            return redirect(url_for('settings.users_list'))
    
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('settings.users_list'))
