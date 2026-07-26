"""
Student Promotion Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.helpers import get_active_session
from models import (
    db, Student, StudentEnrollment, ClassArmAssignment, PromotionRule, PromotionRecord,
    Term, AcademicSession, SchoolClass, StudentScore, ClassSubject, Subject,
    SchoolSettings, ClassArm
)
from utils.helpers import login_required, get_sss3_enrolled_students, safe_redirect
from utils.access_control import (
    admin_required, graduates_access_required, assert_graduate_access,
)
from utils.branch_scope import scope_query, scope_by_student
from utils.db_tx import safe_transaction
from utils.audit import log_action
from datetime import date
import json

promotion_bp = Blueprint('promotion', __name__, url_prefix='/promotion')

_STATUS_BADGE = {'promoted': 'badge-success', 'graduated': 'badge-primary',
                 'repeated': 'badge-warning'}


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch' or request.is_json


def _ok(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': True, 'message': message, 'redirect': redirect_url})
    flash(message, 'success')
    return redirect(redirect_url or url_for('promotion.index'))


def _err(message, redirect_url=None):
    if _wants_json():
        return jsonify({'ok': False, 'error': message}), 400
    flash(message, 'error')
    return redirect(redirect_url or url_for('promotion.index'))


def _render(payload):
    from utils.spa import render_or_json
    return render_or_json('promotion/app.html', 'promo_json', payload)


def _sessions_json():
    return [{'id': s.id, 'name': s.name} for s in
            AcademicSession.query.order_by(AcademicSession.id.desc()).all()]


# ============================================================================
# GRADUATES
# ============================================================================

@promotion_bp.route('/graduates')
@graduates_access_required
def graduates_list():
    """List all graduated students"""
    session_id = request.args.get('session_id', type=int)

    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()

    from utils.branch_scope import scope_query
    query = scope_query(Student.query.filter_by(is_graduated=True), Student)

    if session_id:
        query = query.filter_by(graduation_session_id=session_id)

    graduates = query.order_by(Student.surname, Student.first_name).all()

    return _render({
        'page': 'graduates', 'session_id': session_id or '', 'sessions': _sessions_json(),
        'preview_url': url_for('promotion.graduate_sss3_preview'),
        'compare_url': url_for('promotion.graduate_compare'),
        'graduates': [{
            'id': s.id, 'full_name': s.full_name, 'student_id': s.student_id, 'gender': s.gender,
            'graduation_date': s.graduation_date.strftime('%d %b %Y') if s.graduation_date else None,
            'graduation_session': s.graduation_session.name if s.graduation_session else None,
            'has_waec': s.waec_results.count() > 0, 'has_jamb': s.jamb_results.count() > 0,
            'profile_url': url_for('promotion.graduate_profile', student_id=s.id),
        } for s in graduates],
    })


@promotion_bp.route('/graduate/<int:student_id>', methods=['POST'])
@admin_required
def mark_graduate(student_id):
    """Mark a single (SSS3) student as graduated."""
    from utils.branch_scope import require_branch_access
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)   # don't graduate another branch's student
    active_session = get_active_session()
    try:
        student.is_graduated = True
        student.graduation_date = date.today()
        if active_session:
            student.graduation_session_id = active_session.id
        db.session.commit()
        log_action('graduate', student.full_name)
        flash(f'{student.full_name} has been marked as a graduate.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return safe_redirect(url_for('main.view_student', student_id=student.id))


@promotion_bp.route('/ungraduate/<int:student_id>', methods=['POST'])
@admin_required
def unmark_graduate(student_id):
    """Reverse a graduation (in case it was marked by mistake)."""
    from utils.branch_scope import require_branch_access
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)   # don't alter another branch's student
    try:
        student.is_graduated = False
        student.graduation_date = None
        student.graduation_session_id = None
        db.session.commit()
        log_action('ungraduate', student.full_name)
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('main.view_student', student_id=student.id))
    return _ok(f'{student.full_name} is no longer marked as a graduate.',
               url_for('promotion.graduates_list'))


@promotion_bp.route('/graduate-sss3/preview')
@admin_required
def graduate_sss3_preview():
    """Review which SSS3 students will be graduated before committing."""
    enrolled = get_sss3_enrolled_students()
    students = [s for s in enrolled if not s.is_graduated]
    already = [s for s in enrolled if s.is_graduated]
    return _render({
        'page': 'graduate_preview', 'already_count': len(already),
        'confirm_url': url_for('promotion.graduate_sss3'),
        'urls': {'graduates': url_for('promotion.graduates_list')},
        'students': [{'student_id': s.student_id, 'full_name': s.full_name, 'gender': s.gender}
                     for s in students],
    })


@promotion_bp.route('/graduate-sss3', methods=['POST'])
@admin_required
def graduate_sss3():
    """Mark every current SSS3 student (active term) as a graduate in one click."""
    active_session = get_active_session()
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
        log_action('graduate_sss3', f'{graduated} students')
        msg = (f'{graduated} SSS3 student(s) marked as graduates.' if graduated
               else 'No new SSS3 students to graduate.')
        return _ok(msg, url_for('promotion.graduates_list'))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('promotion.graduates_list'))


@promotion_bp.route('/graduates/<int:student_id>')
@graduates_access_required
def graduate_profile(student_id):
    """View graduate profile with all external results"""
    from models import WAECResult, JAMBResult

    student = db.get_or_404(Student, student_id)
    assert_graduate_access(student)   # admin / SSS3 form teacher, branch-scoped

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
        graduation_session = db.session.get(AcademicSession, student.graduation_session_id)
    
    return _render({
        'page': 'graduate_profile',
        'student': {'id': student.id, 'full_name': student.full_name,
                    'student_id': student.student_id, 'gender': student.gender},
        'graduation_session': graduation_session.name if graduation_session else None,
        'graduation_date': student.graduation_date.strftime('%d %B %Y') if student.graduation_date else None,
        'waec_by_year': [{'exam_year': v['exam_year'], 'exam_number': v['exam_number'],
                          'subjects': [{'subject': r.subject, 'grade': r.grade} for r in v['subjects']]}
                         for v in waec_by_year.values()],
        'jamb_results': [{'exam_year': j.exam_year, 'total_score': j.total_score,
                          'registration_number': j.registration_number,
                          'subjects': [{'name': j.subject1, 'score': j.subject1_score},
                                       {'name': j.subject2, 'score': j.subject2_score},
                                       {'name': j.subject3, 'score': j.subject3_score},
                                       {'name': j.subject4, 'score': j.subject4_score}]} for j in jamb_results],
        'contacts': [{'name': c.name or c.relationship, 'relationship': c.relationship,
                      'phone': c.phone_number} for c in student.parent_contacts],
        'urls': {'graduates': url_for('promotion.graduates_list'),
                 'full_profile': url_for('main.view_student', student_id=student.id),
                 'ungraduate': url_for('promotion.unmark_graduate', student_id=student.id),
                 'add_waec': url_for('results.add_waec') + f'?student_id={student.id}',
                 'add_jamb': url_for('results.add_jamb') + f'?student_id={student.id}'},
    })


@promotion_bp.route('/graduates/compare')
@graduates_access_required
def graduate_compare():
    """Compare a graduate cohort's mock & real WAEC/JAMB with the current SSS3
    class — credit patterns, pass rates, grade spreads and a data-grounded
    projection of where the current class is tracking. Restricted to branch /
    central admins and SSS3 form teachers, branch-scoped throughout."""
    from models.graduate_compare import compare_cohorts
    from utils.branch_scope import scope_query

    session_id = request.args.get('session_id', type=int)

    grad_q = scope_query(Student.query.filter_by(is_active=True, is_graduated=True), Student)
    if session_id:
        grad_q = grad_q.filter_by(graduation_session_id=session_id)
    grad_ids = [s.id for s in grad_q.all()]

    # Current SSS3 (already branch/section/term scoped, graduates excluded).
    sss3 = [s for s in get_sss3_enrolled_students() if not s.is_graduated]
    sss3_ids = [s.id for s in sss3]

    data = compare_cohorts(grad_ids, sss3_ids)

    return _render({
        'page': 'graduate_compare', 'session_id': session_id or '',
        'sessions': _sessions_json(),
        'urls': {'graduates': url_for('promotion.graduates_list'),
                 'self': url_for('promotion.graduate_compare')},
        'comparison': data,
    })


@promotion_bp.route('/')
@login_required
def index():
    """Promotion dashboard"""
    # Get sessions
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    active_session = get_active_session()
    
    # Get promotion rules count
    rules_count = PromotionRule.query.filter_by(is_active=True).count()
    
    # Get recent promotions (branch-scoped)
    recent_promotions = scope_by_student(PromotionRecord.query, PromotionRecord).order_by(
        PromotionRecord.created_at.desc()
    ).limit(10).all()
    
    return _render({
        'page': 'index', 'rules_count': rules_count,
        'active_session': active_session.name if active_session else None,
        'recent': [{'name': p.student.full_name, 'status': p.status,
                    'status_badge': _STATUS_BADGE.get(p.status, 'badge-secondary'),
                    'from_class': p.from_class.name if p.from_class else '-',
                    'to_class': p.to_class.name if p.to_class else '-', 'stream': p.stream}
                   for p in recent_promotions],
        'urls': {'rules': url_for('promotion.rules_list'), 'process': url_for('promotion.process_promotion'),
                 'graduates': url_for('promotion.graduates_list'), 'history': url_for('promotion.promotion_history')},
    })


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
    
    return _render({
        'page': 'rules', 'add_url': url_for('promotion.add_rule'),
        'rules': [{'id': r.id, 'from_class': r.from_class.name, 'to_class': r.to_class.name,
                   'stream_name': r.stream_name, 'min_average': r.min_average, 'priority': r.priority,
                   'required_count': len(r.get_required_subjects()) if r.required_subjects else 0,
                   'delete_url': url_for('promotion.delete_rule', rule_id=r.id)} for r in rules],
    })


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
            return _ok('Promotion rule added!', url_for('promotion.rules_list'))
        except Exception as e:
            db.session.rollback()
            return _err(f'Error: {str(e)}', url_for('promotion.add_rule'))

    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    return _render({
        'page': 'add_rule', 'submit_url': url_for('promotion.add_rule'),
        'urls': {'rules': url_for('promotion.rules_list')},
        'classes': [{'id': c.id, 'name': c.name} for c in classes],
        'subjects': [{'id': s.id, 'name': s.name} for s in subjects],
    })


@promotion_bp.route('/rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_rule(rule_id):
    """Delete promotion rule"""
    rule = db.get_or_404(PromotionRule, rule_id)
    rule.is_active = False
    db.session.commit()
    return _ok('Rule deleted!', url_for('promotion.rules_list'))


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
        from_session = db.session.get(AcademicSession, from_session_id)
        to_session = db.session.get(AcademicSession, to_session_id) if to_session_id else None
        selected_class = db.session.get(SchoolClass, class_id)
        
        # Get third term for the session
        third_term = Term.query.filter_by(
            session_id=from_session_id,
            term_number=3
        ).first()
        
        if third_term:
            # Get all class arm assignments for this class in the term (scoped)
            assignments = scope_query(ClassArmAssignment.query.filter_by(
                term_id=third_term.id,
                class_id=class_id
            ), ClassArmAssignment).all()
            
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
    
    classes_json = [{'id': c.id, 'name': c.name} for c in classes]
    # Streams (class arms) available per class, so the UI can prefill a dropdown
    # for the chosen destination class. Falls back to the global stream list.
    from utils.helpers import STREAMS
    from collections import defaultdict
    arm_pairs = (db.session.query(ClassArmAssignment.class_id, ClassArm.name)
                 .join(ClassArm, ClassArmAssignment.arm_id == ClassArm.id)
                 .filter(ClassArm.is_active.is_(True),
                         ClassArm.is_default.is_(False)).distinct().all())   # hide the default arm
    class_streams = defaultdict(list)
    for cid, arm_name in arm_pairs:
        if arm_name and arm_name not in class_streams[cid]:
            class_streams[cid].append(arm_name)
    class_streams_json = {str(cid): sorted(names) for cid, names in class_streams.items()}
    return _render({
        'page': 'process', 'sessions': _sessions_json(), 'classes': classes_json,
        'class_streams': class_streams_json, 'streams': list(STREAMS),
        'from_session_id': from_session_id or '', 'to_session_id': to_session_id or '',
        'class_id': class_id or '', 'threshold': promotion_threshold,
        'selected_class_name': selected_class.name if selected_class else '',
        'execute_url': url_for('promotion.execute_promotion'),
        'urls': {'self': url_for('promotion.process_promotion')},
        'students': [{
            'id': it['student'].id, 'name': it['student'].full_name,
            'assignment': it['assignment'].display_name, 'average': it['average'],
            'over_threshold': bool(it['average'] and it['average'] >= promotion_threshold),
            'recommendation': {'message': it['recommendation'].get('message', ''),
                               'status': it['recommendation'].get('status'),
                               'to_class': it['recommendation'].get('to_class'),
                               'stream': it['recommendation'].get('stream')},
            'existing_status': it['existing_promotion'].status if it['existing_promotion'] else None,
        } for it in students_data],
    })


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
            
            student = db.session.get(Student, int(student_id))
            if not student:
                continue
            # Never promote/graduate a student outside the user's branch, even if
            # a crafted student_id[] is posted (the single-student routes already
            # guard; the bulk path must match).
            from utils.branch_scope import can_access_branch
            if not can_access_branch(student.branch_id):
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
        
        dest = url_for('promotion.process_promotion',
                       from_session_id=from_session_id, to_session_id=to_session_id)
        return _ok(f'Processed: {", ".join(msg_parts)}', dest)
    except Exception as e:
        db.session.rollback()
        return _err(f'Error: {str(e)}', url_for('promotion.process_promotion',
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
        
        to_session = db.session.get(AcademicSession, to_session_id)
        
        # Get first term of new session
        first_term = Term.query.filter_by(
            session_id=to_session_id,
            term_number=1
        ).first()
        
        if not first_term:
            flash('First term not found for new session. Please create terms first.', 'error')
            return redirect(url_for('promotion.index'))
        
        # Get promoted students (branch-scoped)
        promotions = scope_by_student(PromotionRecord.query, PromotionRecord).filter_by(
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

            assignment = None
            # Prefer the explicitly chosen stream (arm) for the destination class.
            if promo.stream:
                assignment = (ClassArmAssignment.query.join(ClassArm)
                              .filter(ClassArmAssignment.term_id == first_term.id,
                                      ClassArmAssignment.class_id == promo.to_class_id,
                                      ClassArm.name == promo.stream).first())
            # Otherwise keep the same arm as before.
            if not assignment and arm_id is not None:
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
        records = scope_by_student(PromotionRecord.query.filter_by(
            from_session_id=session_id
        ), PromotionRecord).join(Student).order_by(Student.surname).all()
    
    return _render({
        'page': 'history', 'session_id': session_id or '', 'sessions': _sessions_json(),
        'records': [{'name': r.student.full_name, 'status': r.status,
                     'status_badge': _STATUS_BADGE.get(r.status, 'badge-secondary'),
                     'from_class': r.from_class.name if r.from_class else '-',
                     'to_class': r.to_class.name if r.to_class else '-', 'stream': r.stream,
                     'average': r.average_score, 'is_manual': bool(r.is_manual)} for r in records],
    })


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
    
    current_class = db.session.get(SchoolClass, class_id)
    
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
