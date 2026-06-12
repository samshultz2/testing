"""
Academic management routes - Sessions, Terms, Classes, Arms
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.helpers import get_active_term
from datetime import timedelta, date
from models import (
    db, AcademicSession, Term, SchoolClass, ClassArm, 
    ClassArmAssignment, StudentEnrollment, Week, Holiday, Student
)
from utils.helpers import login_required, parse_date, get_weeks_in_range

academics_bp = Blueprint('academics', __name__, url_prefix='/academics')


# ============================================================================
# ACADEMIC SESSIONS
# ============================================================================

@academics_bp.route('/sessions')
@login_required
def sessions_list():
    """List all academic sessions"""
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    return render_template('academics/sessions.html', sessions=sessions)


@academics_bp.route('/sessions/add', methods=['GET', 'POST'])
@login_required
def add_session():
    """Add new academic session"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            is_active = request.form.get('is_active') == 'on'
            
            # Validate
            if not name:
                flash('Session name is required.', 'error')
                return redirect(url_for('academics.add_session'))
            
            # Check for duplicate
            existing = AcademicSession.query.filter_by(name=name).first()
            if existing:
                flash('A session with this name already exists.', 'error')
                return redirect(url_for('academics.add_session'))
            
            # If setting as active, deactivate others
            if is_active:
                AcademicSession.query.update({AcademicSession.is_active: False})
            
            session = AcademicSession(
                name=name,
                start_date=start_date,
                end_date=end_date,
                is_active=is_active
            )
            db.session.add(session)
            db.session.commit()
            
            flash('Academic session created successfully!', 'success')
            return redirect(url_for('academics.sessions_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating session: {str(e)}', 'error')
    
    return render_template('academics/add_session.html')


@academics_bp.route('/sessions/<int:session_id>/activate', methods=['POST'])
@login_required
def activate_session(session_id):
    """Set a session as active"""
    try:
        # Deactivate all sessions
        AcademicSession.query.update({AcademicSession.is_active: False})
        
        # Activate selected session
        session = db.get_or_404(AcademicSession, session_id)
        session.is_active = True
        db.session.commit()
        
        flash(f'{session.name} is now the active session.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.sessions_list'))


@academics_bp.route('/sessions/<int:session_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_session(session_id):
    """Edit an academic session"""
    session = db.get_or_404(AcademicSession, session_id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            
            if not name:
                flash('Session name is required.', 'error')
                return redirect(url_for('academics.edit_session', session_id=session_id))
            
            # Check for duplicate name (excluding current session)
            existing = AcademicSession.query.filter(
                AcademicSession.name == name,
                AcademicSession.id != session_id
            ).first()
            if existing:
                flash('A session with this name already exists.', 'error')
                return redirect(url_for('academics.edit_session', session_id=session_id))
            
            session.name = name
            session.start_date = start_date
            session.end_date = end_date
            db.session.commit()
            
            flash('Session updated successfully!', 'success')
            return redirect(url_for('academics.sessions_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating session: {str(e)}', 'error')
    
    return render_template('academics/edit_session.html', academic_session=session)


# ============================================================================
# TERMS
# ============================================================================

@academics_bp.route('/terms')
@login_required
def terms_list():
    """List all terms"""
    terms = Term.query.join(AcademicSession).order_by(
        AcademicSession.name.desc(),
        Term.term_number
    ).all()
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    return render_template('academics/terms.html', terms=terms, sessions=sessions)


@academics_bp.route('/terms/add', methods=['GET', 'POST'])
@login_required
def add_term():
    """Add new term"""
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    if request.method == 'POST':
        try:
            session_id = request.form.get('session_id', type=int)
            term_number = request.form.get('term_number', type=int)
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            is_active = request.form.get('is_active') == 'on'
            
            # Validate
            if not session_id or not term_number:
                flash('Session and term number are required.', 'error')
                return redirect(url_for('academics.add_term'))
            
            # Check for duplicate
            existing = Term.query.filter_by(
                session_id=session_id,
                term_number=term_number
            ).first()
            if existing:
                flash('This term already exists for this session.', 'error')
                return redirect(url_for('academics.add_term'))
            
            # Get term name
            term_names = {1: 'First Term', 2: 'Second Term', 3: 'Third Term'}
            term_name = term_names.get(term_number, f'Term {term_number}')
            
            # If setting as active, deactivate others
            if is_active:
                Term.query.update({Term.is_active: False})
            
            term = Term(
                session_id=session_id,
                term_number=term_number,
                name=term_name,
                start_date=start_date,
                end_date=end_date,
                is_active=is_active
            )
            db.session.add(term)
            db.session.flush()
            
            # Auto-generate weeks if dates provided
            if start_date and end_date:
                weeks = get_weeks_in_range(start_date, end_date)
                for week_num, mon, fri in weeks:
                    week = Week(
                        term_id=term.id,
                        week_number=week_num,
                        start_date=mon,
                        end_date=fri
                    )
                    db.session.add(week)
            
            db.session.commit()
            flash('Term created successfully!', 'success')
            return redirect(url_for('academics.terms_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating term: {str(e)}', 'error')
    
    return render_template('academics/add_term.html', sessions=sessions)


@academics_bp.route('/terms/<int:term_id>/activate', methods=['POST'])
@login_required
def activate_term(term_id):
    """Set a term as active"""
    try:
        Term.query.update({Term.is_active: False})
        
        term = db.get_or_404(Term, term_id)
        term.is_active = True
        
        # Also activate the parent session
        AcademicSession.query.update({AcademicSession.is_active: False})
        term.session.is_active = True
        
        db.session.commit()
        flash(f'{term.full_name} is now the active term.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.terms_list'))


@academics_bp.route('/terms/<int:term_id>')
@login_required
def view_term(term_id):
    """View term details including weeks and holidays"""
    term = db.get_or_404(Term, term_id)
    weeks = term.weeks.order_by(Week.week_number).all()
    holidays = term.holidays.order_by(Holiday.date).all()
    class_assignments = term.class_arm_assignments.all()
    
    return render_template('academics/view_term.html',
        term=term,
        weeks=weeks,
        holidays=holidays,
        class_assignments=class_assignments
    )


@academics_bp.route('/terms/<int:term_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_term(term_id):
    """Edit a term's dates"""
    term = db.get_or_404(Term, term_id)
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    if request.method == 'POST':
        try:
            start_date = parse_date(request.form.get('start_date'))
            end_date = parse_date(request.form.get('end_date'))
            regenerate_weeks = request.form.get('regenerate_weeks') == 'on'
            
            term.start_date = start_date
            term.end_date = end_date
            
            # Optionally regenerate weeks
            if regenerate_weeks and start_date and end_date:
                # Delete existing weeks
                Week.query.filter_by(term_id=term.id).delete()
                
                # Generate new weeks
                weeks = get_weeks_in_range(start_date, end_date)
                for week_num, mon, fri in weeks:
                    week = Week(
                        term_id=term.id,
                        week_number=week_num,
                        start_date=mon,
                        end_date=fri
                    )
                    db.session.add(week)
            
            db.session.commit()
            flash('Term updated successfully!', 'success')
            return redirect(url_for('academics.view_term', term_id=term_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating term: {str(e)}', 'error')
    
    return render_template('academics/edit_term.html', term=term, sessions=sessions)


# ============================================================================
# WEEKS
# ============================================================================

@academics_bp.route('/terms/<int:term_id>/weeks/add', methods=['POST'])
@login_required
def add_next_week(term_id):
    """Add the next week to a term"""
    term = db.get_or_404(Term, term_id)
    
    try:
        # Get the last week for this term
        last_week = Week.query.filter_by(term_id=term_id).order_by(Week.week_number.desc()).first()
        
        if last_week:
            # Calculate next week based on last week
            new_week_number = last_week.week_number + 1
            new_start_date = last_week.start_date + timedelta(days=7)
            new_end_date = last_week.end_date + timedelta(days=7)
        else:
            # First week - use term start date or today
            new_week_number = 1
            if term.start_date:
                # Find the Monday of or after the start date
                start = term.start_date
                while start.weekday() != 0:  # 0 = Monday
                    start += timedelta(days=1)
                new_start_date = start
            else:
                # Use next Monday from today
                today = date.today()
                days_until_monday = (7 - today.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 7
                new_start_date = today + timedelta(days=days_until_monday)
            
            new_end_date = new_start_date + timedelta(days=4)  # Friday
        
        # Check max weeks (15)
        if new_week_number > 15:
            flash('Maximum of 15 weeks reached for this term.', 'warning')
            return redirect(url_for('academics.view_term', term_id=term_id))
        
        week = Week(
            term_id=term.id,
            week_number=new_week_number,
            start_date=new_start_date,
            end_date=new_end_date
        )
        db.session.add(week)
        db.session.commit()
        
        flash(f'Week {new_week_number} added ({new_start_date.strftime("%d %b")} - {new_end_date.strftime("%d %b %Y")})!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.view_term', term_id=term_id))


@academics_bp.route('/weeks/<int:week_id>/delete', methods=['POST'])
@login_required
def delete_week(week_id):
    """Delete a week (only the last week can be deleted)"""
    week = db.get_or_404(Week, week_id)
    term_id = week.term_id
    
    try:
        # Verify this is the last week
        last_week = Week.query.filter_by(term_id=term_id).order_by(Week.week_number.desc()).first()
        
        if week.id != last_week.id:
            flash('Only the last week can be deleted.', 'error')
            return redirect(url_for('academics.view_term', term_id=term_id))
        
        # Delete associated attendance records first
        from models import Attendance
        Attendance.query.filter_by(week_id=week_id).delete()
        
        db.session.delete(week)
        db.session.commit()
        
        flash(f'Week {week.week_number} deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.view_term', term_id=term_id))


@academics_bp.route('/terms/<int:term_id>/weeks/generate', methods=['POST'])
@login_required
def generate_weeks(term_id):
    """Generate weeks for a term"""
    term = db.get_or_404(Term, term_id)
    
    if not term.start_date or not term.end_date:
        flash('Please set term start and end dates first.', 'error')
        return redirect(url_for('academics.view_term', term_id=term_id))
    
    try:
        # Delete existing weeks
        Week.query.filter_by(term_id=term_id).delete()
        
        # Generate new weeks
        weeks = get_weeks_in_range(term.start_date, term.end_date)
        for week_num, mon, fri in weeks:
            week = Week(
                term_id=term.id,
                week_number=week_num,
                start_date=mon,
                end_date=fri
            )
            db.session.add(week)
        
        db.session.commit()
        flash(f'{len(weeks)} weeks generated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.view_term', term_id=term_id))


# ============================================================================
# HOLIDAYS
# ============================================================================

@academics_bp.route('/terms/<int:term_id>/holidays/add', methods=['POST'])
@login_required
def add_holiday(term_id):
    """Add a holiday (single day or a date range, e.g. a one-week mid-term break)."""
    try:
        from datetime import timedelta
        start = parse_date(request.form.get('date'))
        end = parse_date(request.form.get('end_date')) or start
        reason = request.form.get('reason', '').strip()
        holiday_type = request.form.get('holiday_type', 'Public Holiday')

        if not start or not reason:
            flash('Date and reason are required.', 'error')
            return redirect(url_for('academics.view_term', term_id=term_id))
        if end < start:
            start, end = end, start
        if (end - start).days > 60:
            flash('That range is longer than 60 days — please check the dates.', 'error')
            return redirect(url_for('academics.view_term', term_id=term_id))

        taken = {h.date for h in Holiday.query.filter_by(term_id=term_id).all()}
        added = skipped = 0
        d = start
        while d <= end:
            if d.weekday() >= 5:          # weekends are already non-school days
                pass
            elif d in taken:
                skipped += 1
            else:
                db.session.add(Holiday(term_id=term_id, date=d, reason=reason,
                                       holiday_type=holiday_type))
                added += 1
            d += timedelta(days=1)
        db.session.commit()

        if added and end != start:
            msg = (f'{reason}: {added} day(s) marked '
                   f'({start.strftime("%d %b")} – {end.strftime("%d %b %Y")}).')
        elif added:
            msg = 'Holiday added successfully!'
        else:
            msg = 'No new days to add — those dates are already holidays or weekends.'
        if skipped:
            msg += f' {skipped} already-marked day(s) skipped.'
        flash(msg, 'success' if added else 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('academics.view_term', term_id=term_id))


@academics_bp.route('/holidays/<int:holiday_id>/delete', methods=['POST'])
@login_required
def delete_holiday(holiday_id):
    """Delete a holiday"""
    holiday = db.get_or_404(Holiday, holiday_id)
    term_id = holiday.term_id
    
    try:
        db.session.delete(holiday)
        db.session.commit()
        flash('Holiday deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.view_term', term_id=term_id))


# ============================================================================
# CLASSES
# ============================================================================

@academics_bp.route('/classes')
@login_required
def classes_list():
    """List all classes"""
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    return render_template('academics/classes.html', classes=classes)


@academics_bp.route('/classes/add', methods=['POST'])
@login_required
def add_class():
    """Add a new class"""
    try:
        name = request.form.get('name', '').strip().upper()
        level = request.form.get('level', type=int)
        description = request.form.get('description', '').strip()
        
        if not name or not level:
            flash('Class name and level are required.', 'error')
            return redirect(url_for('academics.classes_list'))
        
        existing = SchoolClass.query.filter_by(name=name).first()
        if existing:
            flash('A class with this name already exists.', 'error')
            return redirect(url_for('academics.classes_list'))
        
        school_class = SchoolClass(
            name=name,
            level=level,
            description=description
        )
        db.session.add(school_class)
        db.session.commit()
        
        flash('Class added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.classes_list'))


# ============================================================================
# CLASS ARMS
# ============================================================================

@academics_bp.route('/arms')
@login_required
def arms_list():
    """List all class arms"""
    arms = ClassArm.query.order_by(ClassArm.name).all()
    return render_template('academics/arms.html', arms=arms)


@academics_bp.route('/arms/add', methods=['POST'])
@login_required
def add_arm():
    """Add a new class arm"""
    try:
        name = request.form.get('name', '').strip().title()
        description = request.form.get('description', '').strip()
        
        if not name:
            flash('Arm name is required.', 'error')
            return redirect(url_for('academics.arms_list'))
        
        existing = ClassArm.query.filter_by(name=name).first()
        if existing:
            flash('An arm with this name already exists.', 'error')
            return redirect(url_for('academics.arms_list'))
        
        arm = ClassArm(name=name, description=description)
        db.session.add(arm)
        db.session.commit()
        
        flash('Arm added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.arms_list'))


# ============================================================================
# CLASS ARM ASSIGNMENTS
# ============================================================================

@academics_bp.route('/assignments')
@login_required
def assignments_list():
    """List class arm assignments for a term"""
    term_id = request.args.get('term_id', type=int)
    
    terms = Term.query.join(AcademicSession).order_by(
        AcademicSession.name.desc(),
        Term.term_number
    ).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    assignments = []
    selected_term = None
    if term_id:
        selected_term = db.session.get(Term, term_id)
        assignments = ClassArmAssignment.query.filter_by(term_id=term_id).join(
            SchoolClass
        ).order_by(SchoolClass.level).all()
    
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True).order_by(ClassArm.name).all()
    
    return render_template('academics/assignments.html',
        assignments=assignments,
        terms=terms,
        selected_term=selected_term,
        classes=classes,
        arms=arms
    )


@academics_bp.route('/assignments/add', methods=['POST'])
@login_required
def add_assignment():
    """Create a class arm assignment"""
    try:
        term_id = request.form.get('term_id', type=int)
        class_id = request.form.get('class_id', type=int)
        arm_id = request.form.get('arm_id', type=int)
        form_teacher = request.form.get('form_teacher', '').strip()
        form_teacher_phone = request.form.get('form_teacher_phone', '').strip()
        
        if not all([term_id, class_id, arm_id]):
            flash('Term, class, and arm are required.', 'error')
            return redirect(url_for('academics.assignments_list', term_id=term_id))
        
        # Check for duplicate
        existing = ClassArmAssignment.query.filter_by(
            term_id=term_id,
            class_id=class_id,
            arm_id=arm_id
        ).first()
        if existing:
            flash('This class-arm combination already exists for this term.', 'error')
            return redirect(url_for('academics.assignments_list', term_id=term_id))
        
        assignment = ClassArmAssignment(
            term_id=term_id,
            class_id=class_id,
            arm_id=arm_id,
            form_teacher_name=form_teacher or None,
            form_teacher_phone=form_teacher_phone or None
        )
        db.session.add(assignment)
        db.session.commit()
        
        flash('Class arm assignment created!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.assignments_list', term_id=term_id))


@academics_bp.route('/assignments/<int:assignment_id>')
@login_required
def view_assignment(assignment_id):
    """View class arm assignment and enrolled students"""
    assignment = db.get_or_404(ClassArmAssignment, assignment_id)
    enrollments = assignment.enrollments.filter_by(is_active=True).all()

    # Available = active students NOT already actively enrolled in ANY class
    # for this term. A student must be removed from their current class before
    # they can be reassigned, so they only reappear here once freed up.
    active_elsewhere = (
        db.session.query(StudentEnrollment.student_id)
        .join(ClassArmAssignment,
              StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
        .filter(StudentEnrollment.is_active == True,
                ClassArmAssignment.term_id == assignment.term_id)
    )
    q = Student.query.filter(
        Student.is_active == True,
        ~Student.id.in_(active_elsewhere.scalar_subquery()),
    )
    # Keep the list to this class's branch when the assignment is branch-bound.
    if assignment.branch_id is not None:
        q = q.filter(Student.branch_id == assignment.branch_id)
    available_students = q.order_by(Student.surname, Student.first_name).all()

    return render_template('academics/view_assignment.html',
        assignment=assignment,
        enrollments=enrollments,
        available_students=available_students
    )


@academics_bp.route('/assignments/<int:assignment_id>/enroll', methods=['POST'])
@login_required
def enroll_student(assignment_id):
    """Enroll a student in a class arm"""
    assignment = db.get_or_404(ClassArmAssignment, assignment_id)
    
    try:
        # Accept both "student_ids[]" and "student_ids" field names.
        student_ids = (request.form.getlist('student_ids[]')
                       or request.form.getlist('student_ids'))

        added = 0          # brand-new enrollments
        reactivated = 0    # previously-removed enrollments brought back
        for raw in student_ids:
            try:
                sid = int(raw)
            except (TypeError, ValueError):
                continue
            # A soft-removed enrollment leaves a row (unique student+assignment),
            # so re-enrolling must REACTIVATE it rather than insert a duplicate.
            existing = StudentEnrollment.query.filter_by(
                student_id=sid,
                class_arm_assignment_id=assignment_id
            ).first()
            if existing:
                if not existing.is_active:
                    existing.is_active = True
                    reactivated += 1
                # already active -> nothing to do
            else:
                db.session.add(StudentEnrollment(
                    student_id=sid,
                    class_arm_assignment_id=assignment_id
                ))
                added += 1

        db.session.commit()
        total = added + reactivated
        if total:
            flash(f'{total} student(s) enrolled.', 'success')
        else:
            flash('No new students to enroll — the selected students were '
                  'already in this class.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('academics.view_assignment', assignment_id=assignment_id))


@academics_bp.route('/enrollments/<int:enrollment_id>/remove', methods=['POST'])
@login_required
def remove_enrollment(enrollment_id):
    """Remove a student from a class arm"""
    enrollment = db.get_or_404(StudentEnrollment, enrollment_id)
    assignment_id = enrollment.class_arm_assignment_id
    
    try:
        enrollment.is_active = False
        db.session.commit()
        flash('Student removed from class.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('academics.view_assignment', assignment_id=assignment_id))


# ============================================================================
# API ENDPOINTS
# ============================================================================

@academics_bp.route('/api/terms/<int:session_id>')
@login_required
def api_get_terms(session_id):
    """Get terms for a session (AJAX)"""
    terms = Term.query.filter_by(session_id=session_id).order_by(Term.term_number).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'is_active': t.is_active
    } for t in terms])


@academics_bp.route('/api/assignments/<int:term_id>')
@login_required
def api_get_assignments(term_id):
    """Get class arm assignments for a term (AJAX)"""
    assignments = ClassArmAssignment.query.filter_by(term_id=term_id).join(
        SchoolClass
    ).order_by(SchoolClass.level).all()
    
    return jsonify([{
        'id': a.id,
        'name': a.display_name,
        'class_name': a.school_class.name,
        'arm_name': a.arm.name
    } for a in assignments])


@academics_bp.route('/api/weeks/<int:term_id>')
@login_required
def api_get_weeks(term_id):
    """Get weeks for a term (AJAX)"""
    weeks = Week.query.filter_by(term_id=term_id).order_by(Week.week_number).all()
    return jsonify([{
        'id': w.id,
        'week_number': w.week_number,
        'start_date': w.start_date.isoformat(),
        'end_date': w.end_date.isoformat()
    } for w in weeks])


# ============================================================================
# COPY TERM SETUP
# ============================================================================

@academics_bp.route('/copy-term-setup', methods=['GET', 'POST'])
@login_required
def copy_term_setup():
    """Copy class assignments and enrollments from one term to another"""
    if request.method == 'POST':
        try:
            from_term_id = request.form.get('from_term_id', type=int)
            to_term_id = request.form.get('to_term_id', type=int)
            copy_enrollments = request.form.get('copy_enrollments') == 'on'
            
            if not from_term_id or not to_term_id:
                flash('Select both source and destination terms.', 'error')
                return redirect(url_for('academics.copy_term_setup'))
            
            if from_term_id == to_term_id:
                flash('Source and destination must be different.', 'error')
                return redirect(url_for('academics.copy_term_setup'))
            
            from_term = db.session.get(Term, from_term_id)
            to_term = db.session.get(Term, to_term_id)
            
            # Get source assignments
            source_assignments = ClassArmAssignment.query.filter_by(term_id=from_term_id).all()
            
            assignments_copied = 0
            enrollments_copied = 0
            
            for src_assign in source_assignments:
                # Check if already exists
                existing = ClassArmAssignment.query.filter_by(
                    term_id=to_term_id,
                    class_id=src_assign.class_id,
                    arm_id=src_assign.arm_id
                ).first()
                
                if existing:
                    dest_assign = existing
                else:
                    # Create new assignment
                    dest_assign = ClassArmAssignment(
                        term_id=to_term_id,
                        class_id=src_assign.class_id,
                        arm_id=src_assign.arm_id
                    )
                    db.session.add(dest_assign)
                    db.session.flush()  # Get ID
                    assignments_copied += 1
                
                # Copy enrollments if requested
                if copy_enrollments:
                    src_enrollments = StudentEnrollment.query.filter_by(
                        class_arm_assignment_id=src_assign.id,
                        is_active=True
                    ).all()
                    
                    for src_enroll in src_enrollments:
                        # Check if student already enrolled
                        existing_enroll = StudentEnrollment.query.filter_by(
                            student_id=src_enroll.student_id,
                            class_arm_assignment_id=dest_assign.id
                        ).first()
                        
                        if not existing_enroll:
                            new_enroll = StudentEnrollment(
                                student_id=src_enroll.student_id,
                                class_arm_assignment_id=dest_assign.id
                            )
                            db.session.add(new_enroll)
                            enrollments_copied += 1
            
            db.session.commit()
            
            msg = f'Copied {assignments_copied} class assignments'
            if copy_enrollments:
                msg += f' and {enrollments_copied} student enrollments'
            flash(msg + '!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
        
        return redirect(url_for('academics.copy_term_setup'))
    
    # GET - show form
    terms = Term.query.order_by(Term.id.desc()).all()
    return render_template('academics/copy_term_setup.html', terms=terms)
