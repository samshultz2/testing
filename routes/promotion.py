"""
Student Promotion Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import (
    db, Student, StudentEnrollment, ClassArmAssignment, PromotionRule, PromotionRecord,
    Term, AcademicSession, SchoolClass, ClassArm, TermSummary, StudentScore,
    ClassSubject, Subject, SchoolSettings, GradeScale
)
from utils.helpers import login_required, get_sss3_enrolled_students
from sqlalchemy import func
from datetime import date
import json

promotion_bp = Blueprint('promotion', __name__, url_prefix='/promotion')


# ============================================================================
# GRADUATES
# ============================================================================

@promotion_bp.route('/graduates')
@login_required
def graduates_list():
    """List all graduated students"""
    session_id = request.args.get('session_id', type=int)
    
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    
    query = Student.query.filter_by(is_graduated=True)
    
    if session_id:
        query = query.filter_by(graduation_session_id=session_id)
    
    graduates = query.order_by(Student.surname, Student.first_name).all()
    
    return render_template('promotion/graduates.html',
        sessions=sessions, session_id=session_id, graduates=graduates
    )


@promotion_bp.route('/graduate/<int:student_id>', methods=['POST'])
@login_required
def mark_graduate(student_id):
    """Mark a single (SSS3) student as graduated."""
    student = Student.query.get_or_404(student_id)
    active_session = AcademicSession.query.filter_by(is_active=True).first()
    try:
        student.is_graduated = True
        student.graduation_date = date.today()
        if active_session:
            student.graduation_session_id = active_session.id
        db.session.commit()
        flash(f'{student.full_name} has been marked as a graduate.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(request.referrer or url_for('main.view_student', student_id=student.id))


@promotion_bp.route('/ungraduate/<int:student_id>', methods=['POST'])
@login_required
def unmark_graduate(student_id):
    """Reverse a graduation (in case it was marked by mistake)."""
    student = Student.query.get_or_404(student_id)
    try:
        student.is_graduated = False
        student.graduation_date = None
        student.graduation_session_id = None
        db.session.commit()
        flash(f'{student.full_name} is no longer marked as a graduate.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(request.referrer or url_for('main.view_student', student_id=student.id))


@promotion_bp.route('/graduate-sss3', methods=['POST'])
@login_required
def graduate_sss3():
    """Mark every current SSS3 student (active term) as a graduate in one click."""
    active_session = AcademicSession.query.filter_by(is_active=True).first()
    students = get_sss3_enrolled_students()
    graduated = 0
    try:
        for student in students:
            if not student.is_graduated:
                student.is_graduated = True
                student.graduation_date = date.today()
                if active_session:
                    student.graduation_session_id = active_session.id
                graduated += 1
        db.session.commit()
        if graduated:
            flash(f'{graduated} SSS3 student(s) marked as graduates.', 'success')
        else:
            flash('No new SSS3 students to graduate.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('promotion.graduates_list'))


@promotion_bp.route('/graduates/<int:student_id>')
@login_required
def graduate_profile(student_id):
    """View graduate profile with all external results"""
    from models import WAECResult, JAMBResult
    
    student = Student.query.get_or_404(student_id)
    
    # Get WAEC results
    waec_results = WAECResult.query.filter_by(student_id=student_id).order_by(
        WAECResult.exam_year.desc()
    ).all()
    
    # Group WAEC by exam year
    waec_by_year = {}
    for result in waec_results:
        key = f"{result.exam_year}"
        if key not in waec_by_year:
            waec_by_year[key] = {
                'exam_year': result.exam_year,
                'exam_number': result.exam_number,
                'subjects': []
            }
        waec_by_year[key]['subjects'].append(result)
    
    # Get JAMB results
    jamb_results = JAMBResult.query.filter_by(student_id=student_id).order_by(
        JAMBResult.exam_year.desc()
    ).all()
    
    # Get graduation info
    graduation_session = None
    if student.graduation_session_id:
        graduation_session = AcademicSession.query.get(student.graduation_session_id)
    
    return render_template('promotion/graduate_profile.html',
        student=student,
        waec_by_year=waec_by_year,
        jamb_results=jamb_results,
        graduation_session=graduation_session
    )


@promotion_bp.route('/')
@login_required
def index():
    """Promotion dashboard"""
    # Get sessions
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    active_session = AcademicSession.query.filter_by(is_active=True).first()
    
    # Get promotion rules count
    rules_count = PromotionRule.query.filter_by(is_active=True).count()
    
    # Get recent promotions
    recent_promotions = PromotionRecord.query.order_by(
        PromotionRecord.created_at.desc()
    ).limit(10).all()
    
    return render_template('promotion/index.html',
        sessions=sessions, active_session=active_session,
        rules_count=rules_count, recent_promotions=recent_promotions
    )


# ============================================================================
# PROMOTION RULES
# ============================================================================

@promotion_bp.route('/rules')
@login_required
def rules_list():
    """List promotion rules"""
    rules = PromotionRule.query.filter_by(is_active=True).order_by(
        PromotionRule.from_class_id, PromotionRule.priority.desc()
    ).all()
    
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    
    return render_template('promotion/rules.html',
        rules=rules, classes=classes, subjects=subjects
    )


@promotion_bp.route('/rules/add', methods=['GET', 'POST'])
@login_required
def add_rule():
    """Add promotion rule"""
    if request.method == 'POST':
        try:
            from_class_id = request.form.get('from_class_id', type=int)
            to_class_id = request.form.get('to_class_id', type=int)
            stream_name = request.form.get('stream_name', '').strip() or None
            min_average = request.form.get('min_average', type=float) or 50.0
            priority = request.form.get('priority', type=int) or 0
            required_subject_ids = request.form.getlist('required_subjects[]')
            
            rule = PromotionRule(
                from_class_id=from_class_id,
                to_class_id=to_class_id,
                stream_name=stream_name,
                min_average=min_average,
                priority=priority,
                required_subjects=json.dumps([int(s) for s in required_subject_ids]) if required_subject_ids else None
            )
            db.session.add(rule)
            db.session.commit()
            
            flash('Promotion rule added!', 'success')
            return redirect(url_for('promotion.rules_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    
    return render_template('promotion/add_rule.html', classes=classes, subjects=subjects)


@promotion_bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_rule(rule_id):
    """Delete promotion rule"""
    rule = PromotionRule.query.get_or_404(rule_id)
    
    try:
        rule.is_active = False
        db.session.commit()
        flash('Rule deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('promotion.rules_list'))


# ============================================================================
# PROMOTION PROCESSING
# ============================================================================

@promotion_bp.route('/process')
@login_required
def process_promotion():
    """Process promotions for a session"""
    from_session_id = request.args.get('from_session_id', type=int)
    to_session_id = request.args.get('to_session_id', type=int)
    class_id = request.args.get('class_id', type=int)
    
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    
    students_data = []
    from_session = None
    to_session = None
    selected_class = None
    promotion_threshold = SchoolSettings.get('promotion_threshold', 50)
    
    if from_session_id and class_id:
        from_session = AcademicSession.query.get(from_session_id)
        to_session = AcademicSession.query.get(to_session_id) if to_session_id else None
        selected_class = SchoolClass.query.get(class_id)
        
        # Get third term for the session
        third_term = Term.query.filter_by(
            session_id=from_session_id,
            term_number=3
        ).first()
        
        if third_term:
            # Get all class arm assignments for this class in the term
            assignments = ClassArmAssignment.query.filter_by(
                term_id=third_term.id,
                class_id=class_id
            ).all()
            
            for assignment in assignments:
                # Get enrolled students
                enrollments = StudentEnrollment.query.filter_by(
                    class_arm_assignment_id=assignment.id,
                    is_active=True
                ).all()
                
                for enrollment in enrollments:
                    student = enrollment.student
                    
                    # Calculate average score
                    avg_score = calculate_student_average(student.id, third_term.id, assignment)
                    
                    # Check existing promotion record
                    existing_promotion = PromotionRecord.query.filter_by(
                        student_id=student.id,
                        from_session_id=from_session_id
                    ).first()
                    
                    # Determine recommended action
                    recommendation = get_promotion_recommendation(
                        student.id, class_id, avg_score, promotion_threshold
                    )
                    
                    students_data.append({
                        'student': student,
                        'enrollment': enrollment,
                        'assignment': assignment,
                        'average': avg_score,
                        'recommendation': recommendation,
                        'existing_promotion': existing_promotion
                    })
            
            # Sort by average descending
            students_data.sort(key=lambda x: x['average'] or 0, reverse=True)
    
    return render_template('promotion/process.html',
        sessions=sessions, classes=classes,
        from_session_id=from_session_id, to_session_id=to_session_id,
        class_id=class_id, from_session=from_session, to_session=to_session,
        selected_class=selected_class, students_data=students_data,
        promotion_threshold=promotion_threshold
    )


@promotion_bp.route('/execute', methods=['POST'])
@login_required
def execute_promotion():
    """Execute promotions"""
    try:
        from datetime import date
        
        from_session_id = request.form.get('from_session_id', type=int)
        to_session_id = request.form.get('to_session_id', type=int)
        
        student_ids = request.form.getlist('student_id[]')
        actions = request.form.getlist('action[]')
        to_class_ids = request.form.getlist('to_class_id[]')
        streams = request.form.getlist('stream[]')
        averages = request.form.getlist('average[]')
        
        promoted = 0
        repeated = 0
        graduated = 0
        
        for i, student_id in enumerate(student_ids):
            action = actions[i] if i < len(actions) else 'skip'
            
            if action == 'skip':
                continue
            
            student = Student.query.get(int(student_id))
            if not student:
                continue
            
            # Get current class
            current_enrollment = StudentEnrollment.query.join(ClassArmAssignment).join(Term).filter(
                StudentEnrollment.student_id == int(student_id),
                Term.session_id == from_session_id,
                StudentEnrollment.is_active == True
            ).first()
            
            if not current_enrollment:
                continue
            
            from_class_id = current_enrollment.class_arm_assignment.class_id
            to_class_id = int(to_class_ids[i]) if i < len(to_class_ids) and to_class_ids[i] else from_class_id
            stream = streams[i] if i < len(streams) else None
            avg = float(averages[i]) if i < len(averages) and averages[i] else None
            
            # Check for existing record
            existing = PromotionRecord.query.filter_by(
                student_id=int(student_id),
                from_session_id=from_session_id
            ).first()
            
            if existing:
                # Update existing
                existing.to_session_id = to_session_id
                existing.to_class_id = to_class_id
                existing.stream = stream or None
                existing.average_score = avg
                existing.status = action
                existing.is_manual = True
            else:
                # Create new record
                record = PromotionRecord(
                    student_id=int(student_id),
                    from_session_id=from_session_id,
                    to_session_id=to_session_id,
                    from_class_id=from_class_id,
                    to_class_id=to_class_id,
                    stream=stream or None,
                    average_score=avg,
                    status=action,
                    is_manual=True,
                    promoted_by='Admin'
                )
                db.session.add(record)
            
            # Handle graduation - update student record
            if action == 'graduated':
                student.is_graduated = True
                student.graduation_date = date.today()
                student.graduation_session_id = from_session_id
                graduated += 1
            elif action == 'promoted':
                promoted += 1
            elif action == 'repeated':
                repeated += 1
        
        db.session.commit()
        
        msg_parts = []
        if promoted:
            msg_parts.append(f'{promoted} promoted')
        if repeated:
            msg_parts.append(f'{repeated} repeated')
        if graduated:
            msg_parts.append(f'{graduated} graduated')
        
        flash(f'Processed: {", ".join(msg_parts)}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('promotion.process_promotion',
        from_session_id=from_session_id, to_session_id=to_session_id))


@promotion_bp.route('/enroll-promoted', methods=['POST'])
@login_required
def enroll_promoted():
    """Enroll promoted students in new session"""
    try:
        to_session_id = request.form.get('to_session_id', type=int)
        from_session_id = request.form.get('from_session_id', type=int)
        
        if not to_session_id:
            flash('Select destination session.', 'error')
            return redirect(url_for('promotion.index'))
        
        to_session = AcademicSession.query.get(to_session_id)
        
        # Get first term of new session
        first_term = Term.query.filter_by(
            session_id=to_session_id,
            term_number=1
        ).first()
        
        if not first_term:
            flash('First term not found for new session. Please create terms first.', 'error')
            return redirect(url_for('promotion.index'))
        
        # Get promoted students
        promotions = PromotionRecord.query.filter_by(
            from_session_id=from_session_id,
            to_session_id=to_session_id,
            status='promoted'
        ).all()
        
        enrolled = 0
        for promo in promotions:
            # Find or create class arm assignment
            # Try to keep same arm as before
            old_enrollment = StudentEnrollment.query.join(ClassArmAssignment).join(Term).filter(
                StudentEnrollment.student_id == promo.student_id,
                Term.session_id == from_session_id
            ).first()
            
            arm_id = old_enrollment.class_arm_assignment.arm_id if old_enrollment else None
            
            # Find assignment for new class
            assignment = ClassArmAssignment.query.filter_by(
                term_id=first_term.id,
                class_id=promo.to_class_id,
                arm_id=arm_id
            ).first()
            
            if not assignment:
                # Try any arm
                assignment = ClassArmAssignment.query.filter_by(
                    term_id=first_term.id,
                    class_id=promo.to_class_id
                ).first()
            
            if assignment:
                # Check not already enrolled
                existing = StudentEnrollment.query.filter_by(
                    student_id=promo.student_id,
                    class_arm_assignment_id=assignment.id
                ).first()
                
                if not existing:
                    enrollment = StudentEnrollment(
                        student_id=promo.student_id,
                        class_arm_assignment_id=assignment.id
                    )
                    db.session.add(enrollment)
                    enrolled += 1
        
        db.session.commit()
        flash(f'{enrolled} students enrolled in new session!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('promotion.index'))


@promotion_bp.route('/history')
@login_required
def promotion_history():
    """View promotion history"""
    session_id = request.args.get('session_id', type=int)
    
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    
    records = []
    if session_id:
        records = PromotionRecord.query.filter_by(
            from_session_id=session_id
        ).join(Student).order_by(Student.surname).all()
    
    return render_template('promotion/history.html',
        sessions=sessions, session_id=session_id, records=records
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_student_average(student_id, term_id, assignment):
    """Calculate student's average score for a term"""
    # Get class subjects
    class_subjects = ClassSubject.query.filter_by(
        term_id=term_id,
        class_id=assignment.class_id,
        is_active=True
    ).filter(
        (ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id)
    ).all()
    
    if not class_subjects:
        return None
    
    total_score = 0
    subjects_with_scores = 0
    
    for cs in class_subjects:
        # Sum all scores for this subject
        scores = StudentScore.query.filter_by(
            student_id=student_id,
            class_subject_id=cs.id
        ).all()
        
        subject_total = sum(s.score for s in scores)
        if subject_total > 0:
            total_score += subject_total
            subjects_with_scores += 1
    
    if subjects_with_scores == 0:
        return None
    
    return round(total_score / subjects_with_scores, 2)


def get_promotion_recommendation(student_id, class_id, average, threshold):
    """Get promotion recommendation based on rules"""
    if average is None:
        return {'status': 'unknown', 'message': 'No scores', 'to_class': None, 'stream': None}
    
    current_class = SchoolClass.query.get(class_id)
    
    # Check if graduating (SSS3) - always graduate, no repeating
    if current_class and current_class.level == 6:
        return {'status': 'graduated', 'message': 'Graduate', 'to_class': None, 'stream': None}
    
    # Get promotion rules
    rules = PromotionRule.query.filter_by(
        from_class_id=class_id,
        is_active=True
    ).order_by(PromotionRule.priority.desc()).all()
    
    # Check each rule
    for rule in rules:
        if average >= rule.min_average:
            # Check required subjects if specified
            if rule.required_subjects:
                # For stream-based promotion (like Science/Arts)
                # This would need subject-specific score checking
                pass
            
            return {
                'status': 'promote',
                'message': f'Promote to {rule.to_class.name}' + (f' ({rule.stream_name})' if rule.stream_name else ''),
                'to_class': rule.to_class_id,
                'stream': rule.stream_name
            }
    
    # Default: check basic threshold
    if average >= threshold:
        next_class = SchoolClass.query.filter(SchoolClass.level == current_class.level + 1).first()
        if next_class:
            return {'status': 'promote', 'message': f'Promote to {next_class.name}', 'to_class': next_class.id, 'stream': None}
    
    return {'status': 'repeat', 'message': f'Below threshold ({average:.1f}%)', 'to_class': class_id, 'stream': None}
