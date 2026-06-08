"""
Subjects and Score Management routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.helpers import get_active_term
from models import (
    db, Subject, ClassSubject, AssessmentType, SubjectAssessmentOverride,
    StudentScore, StudentEnrollment, ClassArmAssignment, Term, SchoolClass,
    ClassArm, Student, GradeScale, SchoolSettings, TermSummary
)
from utils.access_control import (
    login_required, can_access_class, can_enter_results,
    filter_classes_for_user, is_admin
)

subjects_bp = Blueprint('subjects', __name__, url_prefix='/subjects')


# ============================================================================
# SUBJECTS CRUD
# ============================================================================

@subjects_bp.route('/')
@login_required
def subjects_list():
    """List all subjects"""
    from utils.org_scope import scope_subjects
    subjects = scope_subjects(
        Subject.query.filter_by(is_active=True), Subject
    ).order_by(Subject.category, Subject.name).all()
    
    # Group by category
    categories = {}
    for subject in subjects:
        cat = subject.category or 'General'
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(subject)
    
    return render_template('subjects/list.html', subjects=subjects, categories=categories)


@subjects_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_subject():
    """Add a new subject"""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            short_name = request.form.get('short_name', '').strip().upper()
            category = request.form.get('category', '').strip()
            
            if not name:
                flash('Subject name is required.', 'error')
                return redirect(url_for('subjects.add_subject'))
            
            # Check for duplicate
            existing = Subject.query.filter_by(name=name).first()
            if existing:
                flash('Subject already exists.', 'error')
                return redirect(url_for('subjects.add_subject'))
            
            subject = Subject(
                name=name,
                short_name=short_name or name[:3].upper(),
                category=category or 'General',
                has_practical=bool(request.form.get('has_practical'))
            )
            db.session.add(subject)
            db.session.flush()
            from utils.assessments import apply_practical
            apply_practical(db, subject)
            db.session.commit()

            flash(f'Subject "{name}" added!', 'success')
            return redirect(url_for('subjects.subjects_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    categories = ['Science', 'Arts', 'Commercial', 'General', 'Languages', 'Vocational']
    return render_template('subjects/add.html', categories=categories)


@subjects_bp.route('/<int:subject_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_subject(subject_id):
    """Edit a subject"""
    subject = Subject.query.get_or_404(subject_id)
    
    if request.method == 'POST':
        try:
            subject.name = request.form.get('name', '').strip()
            subject.short_name = request.form.get('short_name', '').strip().upper()
            subject.category = request.form.get('category', '').strip()
            subject.has_practical = bool(request.form.get('has_practical'))

            from utils.assessments import apply_practical
            apply_practical(db, subject)
            db.session.commit()
            flash('Subject updated!', 'success')
            return redirect(url_for('subjects.subjects_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    categories = ['Science', 'Arts', 'Commercial', 'General', 'Languages', 'Vocational']
    return render_template('subjects/edit.html', subject=subject, categories=categories)


@subjects_bp.route('/<int:subject_id>/delete', methods=['POST'])
@login_required
def delete_subject(subject_id):
    """Delete (deactivate) a subject"""
    subject = Subject.query.get_or_404(subject_id)
    
    try:
        subject.is_active = False
        db.session.commit()
        flash('Subject deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('subjects.subjects_list'))


@subjects_bp.route('/bulk-add', methods=['GET', 'POST'])
@login_required
def bulk_add_subjects():
    """Bulk add subjects"""
    if request.method == 'POST':
        try:
            subjects_text = request.form.get('subjects', '')
            category = request.form.get('category', 'General')
            
            lines = [line.strip() for line in subjects_text.split('\n') if line.strip()]
            added = 0
            
            for line in lines:
                # Check if already exists
                if not Subject.query.filter_by(name=line).first():
                    subject = Subject(
                        name=line,
                        short_name=line[:3].upper(),
                        category=category
                    )
                    db.session.add(subject)
                    added += 1
            
            db.session.commit()
            flash(f'{added} subjects added!', 'success')
            return redirect(url_for('subjects.subjects_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    categories = ['Science', 'Arts', 'Commercial', 'General', 'Languages', 'Vocational']
    return render_template('subjects/bulk_add.html', categories=categories)


# ============================================================================
# CLASS-SUBJECT ASSIGNMENT
# ============================================================================

@subjects_bp.route('/class-subjects')
@login_required
def class_subjects_list():
    """List class-subject assignments for a term"""
    term_id = request.args.get('term_id', type=int)
    class_id = request.args.get('class_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    
    # Get active term if not specified
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    class_subjects = []
    selected_term = None
    selected_class = None
    
    if term_id:
        selected_term = Term.query.get(term_id)
        query = ClassSubject.query.filter_by(term_id=term_id, is_active=True)
        
        if class_id:
            selected_class = SchoolClass.query.get(class_id)
            query = query.filter_by(class_id=class_id)
        
        class_subjects = query.join(Subject).order_by(Subject.name).all()
    
    return render_template('subjects/class_subjects.html',
        terms=terms, classes=classes,
        selected_term=selected_term, selected_class=selected_class,
        class_subjects=class_subjects, term_id=term_id, class_id=class_id
    )


@subjects_bp.route('/class-subjects/copy', methods=['POST'])
@login_required
def copy_class_subjects():
    """Copy subject assignments from one term into another (modifiable later)."""
    from_term_id = request.form.get('from_term_id', type=int)
    to_term_id = request.form.get('to_term_id', type=int)
    class_id = request.form.get('class_id', type=int)

    if not from_term_id or not to_term_id or from_term_id == to_term_id:
        flash('Choose two different terms to copy between.', 'error')
        return redirect(url_for('subjects.class_subjects_list', term_id=to_term_id, class_id=class_id))

    source = ClassSubject.query.filter_by(term_id=from_term_id, is_active=True)
    if class_id:
        source = source.filter_by(class_id=class_id)
    source = source.all()

    copied, skipped = 0, 0
    for cs in source:
        exists = ClassSubject.query.filter_by(
            term_id=to_term_id, class_id=cs.class_id, arm_id=cs.arm_id,
            subject_id=cs.subject_id
        ).first()
        if exists:
            skipped += 1
            continue
        db.session.add(ClassSubject(
            subject_id=cs.subject_id, class_id=cs.class_id, arm_id=cs.arm_id,
            term_id=to_term_id, teacher_name=cs.teacher_name, is_active=True))
        copied += 1
    db.session.commit()
    flash(f'Copied {copied} subject assignment(s){" (" + str(skipped) + " already existed)" if skipped else ""}.', 'success')
    return redirect(url_for('subjects.class_subjects_list', term_id=to_term_id, class_id=class_id))


@subjects_bp.route('/class-subjects/assign', methods=['GET', 'POST'])
@login_required
def assign_class_subjects():
    """Assign subjects to a class for a term"""
    if request.method == 'POST':
        try:
            term_id = request.form.get('term_id', type=int)
            class_id = request.form.get('class_id', type=int)
            arm_id = request.form.get('arm_id', type=int) or None
            subject_ids = request.form.getlist('subject_ids[]')
            teacher_names = request.form.getlist('teacher_names[]')
            
            if not term_id or not class_id:
                flash('Term and class are required.', 'error')
                return redirect(url_for('subjects.assign_class_subjects'))
            
            added = 0
            for i, subject_id in enumerate(subject_ids):
                if subject_id:
                    # Check if already exists
                    existing = ClassSubject.query.filter_by(
                        subject_id=int(subject_id),
                        class_id=class_id,
                        arm_id=arm_id,
                        term_id=term_id
                    ).first()
                    
                    if existing:
                        # Update teacher name
                        existing.teacher_name = teacher_names[i] if i < len(teacher_names) else None
                        existing.is_active = True
                    else:
                        cs = ClassSubject(
                            subject_id=int(subject_id),
                            class_id=class_id,
                            arm_id=arm_id,
                            term_id=term_id,
                            teacher_name=teacher_names[i] if i < len(teacher_names) else None
                        )
                        db.session.add(cs)
                        added += 1
            
            db.session.commit()
            flash(f'{added} subjects assigned!', 'success')
            return redirect(url_for('subjects.class_subjects_list', term_id=term_id, class_id=class_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    terms = Term.query.order_by(Term.id.desc()).all()
    classes = SchoolClass.query.order_by(SchoolClass.level).all()
    arms = ClassArm.query.order_by(ClassArm.name).all()
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
    
    return render_template('subjects/assign.html',
        terms=terms, classes=classes, arms=arms, subjects=subjects
    )


@subjects_bp.route('/class-subjects/<int:cs_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_class_subject(cs_id):
    """Edit class-subject assignment (mainly teacher name)"""
    cs = ClassSubject.query.get_or_404(cs_id)
    
    if request.method == 'POST':
        try:
            cs.teacher_name = request.form.get('teacher_name', '').strip() or None
            db.session.commit()
            flash('Updated!', 'success')
            return redirect(url_for('subjects.class_subjects_list', term_id=cs.term_id, class_id=cs.class_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('subjects/edit_class_subject.html', cs=cs)


@subjects_bp.route('/class-subjects/<int:cs_id>/delete', methods=['POST'])
@login_required
def delete_class_subject(cs_id):
    """Remove class-subject assignment"""
    cs = ClassSubject.query.get_or_404(cs_id)
    term_id = cs.term_id
    class_id = cs.class_id
    
    try:
        cs.is_active = False
        db.session.commit()
        flash('Subject removed from class!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('subjects.class_subjects_list', term_id=term_id, class_id=class_id))


# ============================================================================
# SCORE ENTRY
# ============================================================================

@subjects_bp.route('/scores')
@login_required
def scores_entry():
    """Score entry page"""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    class_subject_id = request.args.get('class_subject_id', type=int)
    assessment_type_id = request.args.get('assessment_type_id', type=int)
    
    # Check if user can enter results
    if not can_enter_results() and not is_admin():
        flash('You do not have permission to enter scores.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Check class access
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.scores_entry'))
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    # Get active term if not specified
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = Term.query.get(term_id) if term_id else None
    
    # Get class arm assignments for selected term (filtered for teachers)
    assignments = []
    if term_id:
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        assignments = filter_classes_for_user(all_assignments)
    
    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    
    # Get subjects for selected class (filter by teacher's assigned subjects if not admin)
    class_subjects = []
    if selected_assignment:
        from utils.access_control import get_teacher_profile
        teacher = get_teacher_profile()
        
        class_subjects_query = ClassSubject.query.filter_by(
            term_id=term_id,
            class_id=selected_assignment.class_id,
            is_active=True
        ).filter(
            (ClassSubject.arm_id == None) | (ClassSubject.arm_id == selected_assignment.arm_id)
        ).join(Subject).order_by(Subject.name)
        
        all_class_subjects = class_subjects_query.all()
        
        # Filter by teacher's assigned subjects if not admin
        if teacher and not is_admin():
            teacher_subject_ids = [
                a.subject_id for a in teacher.subject_assignments.filter_by(
                    class_arm_assignment_id=assignment_id,
                    is_active=True
                ).all()
            ]
            class_subjects = [cs for cs in all_class_subjects if cs.subject_id in teacher_subject_ids]
        else:
            class_subjects = all_class_subjects
    
    selected_class_subject = ClassSubject.query.get(class_subject_id) if class_subject_id else None
    
    # Get assessment types
    assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    selected_assessment = AssessmentType.query.get(assessment_type_id) if assessment_type_id else None
    
    # Get students and existing scores
    students_data = []
    if selected_assignment and selected_class_subject and selected_assessment:
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).join(Student).order_by(Student.surname, Student.first_name).all()
        
        for enrollment in enrollments:
            # Get existing score
            existing_score = StudentScore.query.filter_by(
                student_id=enrollment.student_id,
                class_subject_id=class_subject_id,
                assessment_type_id=assessment_type_id
            ).first()
            
            students_data.append({
                'enrollment': enrollment,
                'student': enrollment.student,
                'score': existing_score.score if existing_score else None
            })
    
    # Get max score (check for override)
    max_score = selected_assessment.max_score if selected_assessment else 0
    if selected_class_subject and selected_assessment:
        override = SubjectAssessmentOverride.query.filter_by(
            subject_id=selected_class_subject.subject_id,
            assessment_type_id=assessment_type_id,
            is_active=True
        ).first()
        if override:
            max_score = override.max_score
    
    return render_template('subjects/scores.html',
        terms=terms, term_id=term_id, selected_term=selected_term,
        assignments=assignments, assignment_id=assignment_id, selected_assignment=selected_assignment,
        class_subjects=class_subjects, class_subject_id=class_subject_id, selected_class_subject=selected_class_subject,
        assessment_types=assessment_types, assessment_type_id=assessment_type_id, selected_assessment=selected_assessment,
        students_data=students_data, max_score=max_score
    )


@subjects_bp.route('/scores/save', methods=['POST'])
@login_required
def save_scores():
    """Save student scores"""
    try:
        class_subject_id = request.form.get('class_subject_id', type=int)
        assessment_type_id = request.form.get('assessment_type_id', type=int)
        assignment_id = request.form.get('assignment_id', type=int)
        term_id = request.form.get('term_id', type=int)
        
        student_ids = request.form.getlist('student_id[]')
        scores = request.form.getlist('score[]')

        at = AssessmentType.query.get(assessment_type_id)
        max_score = at.max_score if at else None
        saved = 0
        rejected = 0
        for i, student_id in enumerate(student_ids):
            score_value = scores[i].strip() if i < len(scores) else ''

            if score_value:
                try:
                    score_float = float(score_value)
                except ValueError:
                    continue
                if max_score and score_float > max_score:
                    rejected += 1
                    continue
                # Get or create score record
                existing = StudentScore.query.filter_by(
                    student_id=int(student_id),
                    class_subject_id=class_subject_id,
                    assessment_type_id=assessment_type_id
                ).first()
                
                if existing:
                    existing.score = score_float
                else:
                    score = StudentScore(
                        student_id=int(student_id),
                        class_subject_id=class_subject_id,
                        assessment_type_id=assessment_type_id,
                        score=score_float
                    )
                    db.session.add(score)
                saved += 1
            else:
                # Remove score if empty
                StudentScore.query.filter_by(
                    student_id=int(student_id),
                    class_subject_id=class_subject_id,
                    assessment_type_id=assessment_type_id
                ).delete()
        
        db.session.commit()
        # Keep term results/positions fresh as scores change.
        if term_id and assignment_id:
            asg = ClassArmAssignment.query.get(assignment_id)
            if asg:
                from utils.report_card import compute_term_summaries
                compute_term_summaries(term_id, asg.class_id)
        msg = f'{saved} scores saved!'
        if rejected:
            msg += f' {rejected} skipped (above the {max_score:g} maximum).'
        flash(msg, 'success' if not rejected else 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('subjects.scores_entry',
        term_id=term_id, assignment_id=assignment_id,
        class_subject_id=class_subject_id, assessment_type_id=assessment_type_id
    ))


# ============================================================================
# VIEW SCORES / BROADSHEET
# ============================================================================

@subjects_bp.route('/workflow')
@login_required
def workflow():
    """Guided results checklist for a class+term: setup → entry → finalize → print."""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.workflow'))
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = (filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term_id).all()) if term_id else [])
    selected = ClassArmAssignment.query.get(assignment_id) if assignment_id else None

    steps = None
    if selected and term_id:
        enr = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True).all()
        sids = [e.student_id for e in enr]
        css = ClassSubject.query.filter_by(
            term_id=term_id, class_id=selected.class_id, is_active=True).all()
        n_assess = AssessmentType.query.filter_by(is_active=True).count()
        entered = 0
        if sids and css:
            entered = (StudentScore.query.join(ClassSubject).filter(
                ClassSubject.term_id == term_id,
                ClassSubject.class_id == selected.class_id,
                StudentScore.student_id.in_(sids)).count())
        ts_rows = (TermSummary.query.filter(
            TermSummary.term_id == term_id,
            TermSummary.student_id.in_(sids or [-1])).all())
        steps = {
            'students': len(sids),
            'subjects': len(css),
            'scores_entered': entered,
            'scores_expected': len(sids) * len(css) * (n_assess or 1),
            'positions': sum(1 for t in ts_rows if t.position_in_class),
            'comments': sum(1 for t in ts_rows if t.teacher_comment),
            'behaviour': sum(1 for t in ts_rows if t.affective),
        }
    selected_term = Term.query.get(term_id) if term_id else None
    return render_template('subjects/workflow.html', terms=terms, term_id=term_id,
        assignments=assignments, assignment_id=assignment_id, selected=selected,
        steps=steps, published=bool(selected_term and selected_term.results_published))


@subjects_bp.route('/bulk-entry', methods=['GET', 'POST'])
@login_required
def bulk_entry():
    """Enter every subject's scores for a whole class on one screen."""
    term_id = request.values.get('term_id', type=int)
    assignment_id = request.values.get('assignment_id', type=int)
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.bulk_entry'))
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = (filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term_id).all()) if term_id else [])
    selected = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()

    class_subjects, enrollments = [], []
    if selected:
        class_subjects = (ClassSubject.query.filter_by(
            term_id=term_id, class_id=selected.class_id, is_active=True)
            .filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == selected.arm_id))
            .join(Subject).order_by(Subject.name).all())
        enrollments = (StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True)
            .join(Student).order_by(Student.surname, Student.first_name).all())

    if request.method == 'POST' and selected and class_subjects and enrollments:
        sids = [e.student_id for e in enrollments]
        cs_ids = [cs.id for cs in class_subjects]
        existing = {(s.student_id, s.class_subject_id, s.assessment_type_id): s
                    for s in StudentScore.query.filter(
                        StudentScore.student_id.in_(sids),
                        StudentScore.class_subject_id.in_(cs_ids)).all()}
        changed = 0
        rejected = 0
        for e in enrollments:
            for cs in class_subjects:
                for at in assessment_types:
                    raw = (request.form.get(f's_{e.student_id}_{cs.id}_{at.id}') or '').strip()
                    obj = existing.get((e.student_id, cs.id, at.id))
                    if raw:
                        try:
                            val = float(raw)
                        except ValueError:
                            continue
                        if at.max_score and val > at.max_score:
                            rejected += 1
                            continue
                        if obj:
                            if obj.score != val:
                                obj.score = val; changed += 1
                        else:
                            db.session.add(StudentScore(student_id=e.student_id,
                                class_subject_id=cs.id, assessment_type_id=at.id, score=val))
                            changed += 1
                    elif obj:
                        db.session.delete(obj); changed += 1
        db.session.commit()
        from utils.report_card import compute_term_summaries
        compute_term_summaries(term_id, selected.class_id)
        msg = f'Saved — {changed} change(s).'
        if rejected:
            msg += f' {rejected} skipped (above the subject maximum).'
        flash(msg, 'success' if not rejected else 'warning')
        return redirect(url_for('subjects.bulk_entry', term_id=term_id, assignment_id=assignment_id))

    scores = {}
    if selected and class_subjects and enrollments:
        sids = [e.student_id for e in enrollments]
        cs_ids = [cs.id for cs in class_subjects]
        for s in StudentScore.query.filter(StudentScore.student_id.in_(sids),
                                           StudentScore.class_subject_id.in_(cs_ids)).all():
            scores[(s.student_id, s.class_subject_id, s.assessment_type_id)] = s.score

    return render_template('subjects/bulk_entry.html', terms=terms, term_id=term_id,
        assignments=assignments, assignment_id=assignment_id, selected=selected,
        class_subjects=class_subjects, assessment_types=assessment_types,
        enrollments=[e.student for e in enrollments], scores=scores)


@subjects_bp.route('/broadsheet')
@login_required
def broadsheet():
    """View broadsheet (all scores for a class)"""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    
    # Check class access
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.broadsheet'))
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = Term.query.get(term_id) if term_id else None
    
    # Filter assignments for teachers
    assignments = []
    if term_id:
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        assignments = filter_classes_for_user(all_assignments)
    
    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    
    # Build broadsheet data
    broadsheet_data = []
    class_subjects = []
    assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    
    if selected_assignment:
        # Get subjects for this class
        class_subjects = ClassSubject.query.filter_by(
            term_id=term_id,
            class_id=selected_assignment.class_id,
            is_active=True
        ).filter(
            (ClassSubject.arm_id == None) | (ClassSubject.arm_id == selected_assignment.arm_id)
        ).join(Subject).order_by(Subject.name).all()
        
        # Get enrolled students
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).join(Student).order_by(Student.surname, Student.first_name).all()
        
        pass_mark = SchoolSettings.get('pass_mark', 50)
        
        for enrollment in enrollments:
            student_row = {
                'student': enrollment.student,
                'subjects': {},
                'total': 0,
                'average': 0,
                'subjects_passed': 0,
                'subjects_failed': 0
            }
            
            for cs in class_subjects:
                subject_data = {'assessments': {}, 'total': 0}
                
                # Get all scores for this student-subject
                scores = StudentScore.query.filter_by(
                    student_id=enrollment.student_id,
                    class_subject_id=cs.id
                ).all()
                
                scores_dict = {s.assessment_type_id: s.score for s in scores}
                
                subject_total = 0
                for at in assessment_types:
                    score = scores_dict.get(at.id)
                    subject_data['assessments'][at.id] = score
                    if score:
                        subject_total += score
                
                subject_data['total'] = subject_total
                subject_data['grade'] = GradeScale.get_grade(subject_total) if subject_total else '-'
                
                if subject_total >= pass_mark:
                    student_row['subjects_passed'] += 1
                elif subject_total > 0:
                    student_row['subjects_failed'] += 1
                
                student_row['subjects'][cs.id] = subject_data
                student_row['total'] += subject_total
            
            if class_subjects:
                student_row['average'] = round(student_row['total'] / len(class_subjects), 2)
            
            broadsheet_data.append(student_row)
        
        # Sort by average (descending) for ranking
        broadsheet_data.sort(key=lambda x: x['average'], reverse=True)
        
        # Add positions
        for i, row in enumerate(broadsheet_data):
            row['position'] = i + 1
    
    return render_template('subjects/broadsheet.html',
        terms=terms, term_id=term_id, selected_term=selected_term,
        assignments=assignments, assignment_id=assignment_id, selected_assignment=selected_assignment,
        class_subjects=class_subjects, assessment_types=assessment_types,
        broadsheet_data=broadsheet_data
    )


@subjects_bp.route('/broadsheet/compute', methods=['POST'])
@login_required
def compute_summaries():
    """Compute & persist term results + class/arm positions for a class."""
    term_id = request.form.get('term_id', type=int)
    assignment_id = request.form.get('assignment_id', type=int)
    asg = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    if not (term_id and asg):
        flash('Select a term and class first.', 'error')
        return redirect(url_for('subjects.broadsheet'))
    from utils.report_card import compute_term_summaries
    from utils.audit import log_action
    count = compute_term_summaries(term_id, asg.class_id)
    log_action('results.compute_summaries',
               detail=f'term {term_id}, class {asg.class_id}: {count} student(s)')
    flash(f'Computed results and positions for {count} student(s).', 'success')
    return redirect(url_for('subjects.broadsheet', term_id=term_id, assignment_id=assignment_id))


@subjects_bp.route('/affective', methods=['GET', 'POST'])
@login_required
def affective():
    """Enter behavioural / affective ratings (1–5) for a class arm in a term."""
    from utils.report_card import AFFECTIVE_TRAITS, AFFECTIVE_KEYS
    term_id = request.values.get('term_id', type=int)
    assignment_id = request.values.get('assignment_id', type=int)
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.affective'))
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = (filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term_id).all()) if term_id else [])
    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None

    if request.method == 'POST' and selected_assignment and term_id:
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True).all()
        for e in enrollments:
            mapping = {k: request.form.get(f'r_{e.student_id}_{k}', type=int)
                       for k in AFFECTIVE_KEYS}
            ts = TermSummary.query.filter_by(student_id=e.student_id, term_id=term_id).first()
            if not ts:
                ts = TermSummary(student_id=e.student_id, term_id=term_id, enrollment_id=e.id)
                db.session.add(ts)
            ts.set_affective(mapping)
        db.session.commit()
        from utils.audit import log_action
        log_action('results.affective',
                   detail=f'term {term_id}, {selected_assignment.display_name}')
        flash('Behavioural ratings saved.', 'success')
        return redirect(url_for('subjects.affective', term_id=term_id, assignment_id=assignment_id))

    students = []
    if selected_assignment:
        enrollments = (StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True)
            .join(Student).order_by(Student.surname, Student.first_name).all())
        ratings = {ts.student_id: ts.affective_map
                   for ts in TermSummary.query.filter_by(term_id=term_id).all()}
        for e in enrollments:
            students.append({'student': e.student, 'ratings': ratings.get(e.student_id, {})})

    return render_template('subjects/affective.html', terms=terms, term_id=term_id,
        assignments=assignments, assignment_id=assignment_id,
        selected_assignment=selected_assignment, students=students, traits=AFFECTIVE_TRAITS)


@subjects_bp.route('/comments', methods=['GET', 'POST'])
@login_required
def comments():
    """Enter form-teacher & principal comments for a class arm in a term."""
    term_id = request.values.get('term_id', type=int)
    assignment_id = request.values.get('assignment_id', type=int)
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.comments'))
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = (filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term_id).all()) if term_id else [])
    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None

    if request.method == 'POST' and selected_assignment and term_id:
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True).all()
        for e in enrollments:
            ts = TermSummary.query.filter_by(student_id=e.student_id, term_id=term_id).first()
            if not ts:
                ts = TermSummary(student_id=e.student_id, term_id=term_id, enrollment_id=e.id)
                db.session.add(ts)
            ts.teacher_comment = (request.form.get(f't_{e.student_id}') or '').strip() or None
            ts.principal_comment = (request.form.get(f'p_{e.student_id}') or '').strip() or None
        db.session.commit()
        from utils.audit import log_action
        log_action('results.comments', detail=f'term {term_id}, {selected_assignment.display_name}')
        flash('Comments saved.', 'success')
        return redirect(url_for('subjects.comments', term_id=term_id, assignment_id=assignment_id))

    students = []
    if selected_assignment:
        enrollments = (StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True)
            .join(Student).order_by(Student.surname, Student.first_name).all())
        summ = {ts.student_id: ts for ts in TermSummary.query.filter_by(term_id=term_id).all()}
        for e in enrollments:
            ts = summ.get(e.student_id)
            students.append({'student': e.student,
                             'teacher_comment': ts.teacher_comment if ts else '',
                             'principal_comment': ts.principal_comment if ts else ''})

    return render_template('subjects/comments.html', terms=terms, term_id=term_id,
        assignments=assignments, assignment_id=assignment_id,
        selected_assignment=selected_assignment, students=students)


# ============================================================================
# STUDENT REPORT CARD
# ============================================================================

@subjects_bp.route('/report-card/<int:student_id>')
@login_required
def student_report_card(student_id):
    """View student report card"""
    student = Student.query.get_or_404(student_id)
    term_id = request.args.get('term_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = Term.query.get(term_id) if term_id else None

    report_data = None
    enrollment = None

    from utils.report_card import AFFECTIVE_TRAITS, RATING_LABELS
    if selected_term:
        from utils.report_card import build_report_card
        enrollment, report_data = build_report_card(student_id, term_id)

    return render_template('subjects/report_card.html',
        student=student, terms=terms, term_id=term_id, selected_term=selected_term,
        report_data=report_data, enrollment=enrollment,
        affective_traits=AFFECTIVE_TRAITS, rating_labels=RATING_LABELS
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@subjects_bp.route('/api/class-subjects/<int:term_id>/<int:class_id>')
@login_required
def api_class_subjects(term_id, class_id):
    """Get subjects for a class in a term"""
    class_subjects = ClassSubject.query.filter_by(
        term_id=term_id,
        class_id=class_id,
        is_active=True
    ).join(Subject).order_by(Subject.name).all()
    
    return jsonify([{
        'id': cs.id,
        'subject_id': cs.subject_id,
        'subject_name': cs.subject.name,
        'teacher_name': cs.teacher_name
    } for cs in class_subjects])


@subjects_bp.route('/api/student-scores/<int:student_id>/<int:term_id>')
@login_required
def api_student_scores(student_id, term_id):
    """Get all scores for a student in a term"""
    scores = StudentScore.query.join(ClassSubject).filter(
        StudentScore.student_id == student_id,
        ClassSubject.term_id == term_id
    ).all()
    
    return jsonify([{
        'subject': s.class_subject.subject.name,
        'assessment': s.assessment_type.name,
        'score': s.score
    } for s in scores])


# ============================================================================
# EXPORT BROADSHEET TO EXCEL
# ============================================================================

@subjects_bp.route('/broadsheet/export')
@login_required
def export_broadsheet():
    """Export broadsheet to Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from flask import Response
    import io
    
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    
    if not term_id or not assignment_id:
        flash('Select term and class first.', 'error')
        return redirect(url_for('subjects.broadsheet'))
    
    selected_term = Term.query.get(term_id)
    selected_assignment = ClassArmAssignment.query.get(assignment_id)
    
    if not selected_term or not selected_assignment:
        flash('Invalid selection.', 'error')
        return redirect(url_for('subjects.broadsheet'))
    
    # Get data (same as broadsheet view)
    class_subjects = ClassSubject.query.filter_by(
        term_id=term_id,
        class_id=selected_assignment.class_id,
        is_active=True
    ).filter(
        (ClassSubject.arm_id == None) | (ClassSubject.arm_id == selected_assignment.arm_id)
    ).join(Subject).order_by(Subject.name).all()
    
    assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=assignment_id,
        is_active=True
    ).join(Student).order_by(Student.surname, Student.first_name).all()
    
    pass_mark = SchoolSettings.get('pass_mark', 50)
    
    # Build data
    broadsheet_data = []
    for enrollment in enrollments:
        student_row = {
            'student': enrollment.student,
            'subjects': {},
            'total': 0,
            'average': 0
        }
        
        for cs in class_subjects:
            scores = StudentScore.query.filter_by(
                student_id=enrollment.student_id,
                class_subject_id=cs.id
            ).all()
            
            subject_total = sum(s.score for s in scores)
            student_row['subjects'][cs.id] = subject_total
            student_row['total'] += subject_total
        
        if class_subjects:
            student_row['average'] = round(student_row['total'] / len(class_subjects), 2)
        
        broadsheet_data.append(student_row)
    
    # Sort by average
    broadsheet_data.sort(key=lambda x: x['average'], reverse=True)
    
    # Create Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Broadsheet"
    
    # Styles
    header_font = Font(bold=True, size=12)
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font_white = Font(bold=True, color='FFFFFF')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    
    # Title
    ws['A1'] = f"{selected_assignment.display_name} - Broadsheet"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f"{selected_term.full_name}"
    
    # Headers
    row = 4
    headers = ['Pos', 'Student Name', 'Student ID']
    for cs in class_subjects:
        headers.append(cs.subject.short_name or cs.subject.name[:5])
    headers.extend(['Total', 'Average', 'Grade'])
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    # Data rows
    for idx, data in enumerate(broadsheet_data, 1):
        row += 1
        ws.cell(row=row, column=1, value=idx).border = thin_border
        ws.cell(row=row, column=2, value=data['student'].full_name).border = thin_border
        ws.cell(row=row, column=3, value=data['student'].student_id).border = thin_border
        
        col = 4
        for cs in class_subjects:
            score = data['subjects'].get(cs.id, 0)
            cell = ws.cell(row=row, column=col, value=score if score else '')
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')
            col += 1
        
        ws.cell(row=row, column=col, value=data['total']).border = thin_border
        ws.cell(row=row, column=col+1, value=data['average']).border = thin_border
        ws.cell(row=row, column=col+2, value=GradeScale.get_grade(data['average']) if data['average'] else '').border = thin_border
    
    # Auto-width columns
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column].width = min(max_length + 2, 30)
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    filename = f"broadsheet_{selected_assignment.school_class.name}_{selected_assignment.arm.name}_{selected_term.name}.xlsx"
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


# ============================================================================
# BULK SCORE IMPORT FROM EXCEL
# ============================================================================

@subjects_bp.route('/scores/import', methods=['GET', 'POST'])
@login_required
def import_scores():
    """Import scores from Excel"""
    if request.method == 'POST':
        try:
            from openpyxl import load_workbook
            
            term_id = request.form.get('term_id', type=int)
            assignment_id = request.form.get('assignment_id', type=int)
            class_subject_id = request.form.get('class_subject_id', type=int)
            
            if 'file' not in request.files:
                flash('No file selected.', 'error')
                return redirect(url_for('subjects.import_scores'))
            
            file = request.files['file']
            if not file.filename.endswith(('.xlsx', '.xls')):
                flash('Please upload an Excel file.', 'error')
                return redirect(url_for('subjects.import_scores'))
            
            wb = load_workbook(file)
            ws = wb.active
            
            # Get assessment types
            assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
            
            # Expected columns: Student ID, then assessment type names
            imported = 0
            errors = []
            
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                if not row[0]:
                    continue
                
                student_id_str = str(row[0]).strip()
                student = Student.query.filter_by(student_id=student_id_str).first()
                
                if not student:
                    errors.append(f"Row {row_num}: Student {student_id_str} not found")
                    continue
                
                # Import each assessment score
                for col_idx, at in enumerate(assessment_types, 1):
                    if col_idx < len(row) and row[col_idx] is not None:
                        try:
                            score_value = float(row[col_idx])
                            
                            # Get or create score
                            existing = StudentScore.query.filter_by(
                                student_id=student.id,
                                class_subject_id=class_subject_id,
                                assessment_type_id=at.id
                            ).first()
                            
                            if existing:
                                existing.score = score_value
                            else:
                                score = StudentScore(
                                    student_id=student.id,
                                    class_subject_id=class_subject_id,
                                    assessment_type_id=at.id,
                                    score=score_value
                                )
                                db.session.add(score)
                            imported += 1
                        except ValueError:
                            pass
            
            db.session.commit()
            flash(f'Imported {imported} scores!', 'success')
            
            if errors:
                for err in errors[:5]:
                    flash(err, 'warning')
                    
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
        
        return redirect(url_for('subjects.scores_entry', term_id=term_id, assignment_id=assignment_id, class_subject_id=class_subject_id))
    
    # GET - show form
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    class_subject_id = request.args.get('class_subject_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term_id).all()) if term_id else []
    class_subjects = []
    
    if assignment_id:
        assignment = ClassArmAssignment.query.get(assignment_id)
        if assignment:
            class_subjects = ClassSubject.query.filter_by(
                term_id=term_id,
                class_id=assignment.class_id,
                is_active=True
            ).join(Subject).order_by(Subject.name).all()
    
    return render_template('subjects/import_scores.html',
        terms=terms, term_id=term_id,
        assignments=assignments, assignment_id=assignment_id,
        class_subjects=class_subjects, class_subject_id=class_subject_id
    )


@subjects_bp.route('/scores/import/template')
@login_required
def score_import_template():
    """Download score import template"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from flask import Response
    import io
    
    assignment_id = request.args.get('assignment_id', type=int)
    class_subject_id = request.args.get('class_subject_id', type=int)
    
    if not assignment_id:
        flash('Select a class first.', 'error')
        return redirect(url_for('subjects.import_scores'))
    
    assignment = ClassArmAssignment.query.get(assignment_id)
    assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
    
    # Get students
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=assignment_id,
        is_active=True
    ).join(Student).order_by(Student.surname, Student.first_name).all()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Score Import"
    
    # Headers
    headers = ['Student ID', 'Student Name'] + [at.short_name or at.name for at in assessment_types]
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
    
    # Student rows
    for row_num, enrollment in enumerate(enrollments, 2):
        ws.cell(row=row_num, column=1, value=enrollment.student.student_id)
        ws.cell(row=row_num, column=2, value=enrollment.student.full_name)
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=score_import_template.xlsx'}
    )


# ============================================================================
# SCORE-SHEET (BROADSHEET) IMAGE IMPORT — Tesseract OCR
# ============================================================================

def _sheet_columns(class_subject):
    """Assessment columns for a subject, ordered as they appear on a printed
    broadsheet. Returns [(assessment_type, max_score), ...]."""
    from utils.assessments import subject_columns
    from utils.waec_ocr import SHEET_COLUMN_ORDER
    cols = subject_columns(class_subject.subject)  # [(at, max)] in storage order
    present = {at.short_name: (at, mx) for at, mx in cols}
    ordered = [present[sn] for sn in SHEET_COLUMN_ORDER if sn in present]
    # Append any columns not covered by the canonical order (defensive).
    seen = {at.id for at, _ in ordered}
    ordered += [(at, mx) for at, mx in cols if at.id not in seen]
    return ordered


def _scan_selector_context():
    """Shared term/class/subject selector context for the scan pages."""
    term_id = request.values.get('term_id', type=int)
    assignment_id = request.values.get('assignment_id', type=int)
    class_subject_id = request.values.get('class_subject_id', type=int)

    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id

    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = []
    if term_id:
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        assignments = filter_classes_for_user(all_assignments)

    class_subjects = []
    assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    if assignment:
        class_subjects = ClassSubject.query.filter_by(
            term_id=term_id, class_id=assignment.class_id, is_active=True
        ).filter(
            (ClassSubject.arm_id == None) | (ClassSubject.arm_id == assignment.arm_id)
        ).join(Subject).order_by(Subject.name).all()

    return {
        'terms': terms, 'term_id': term_id,
        'assignments': assignments, 'assignment_id': assignment_id,
        'class_subjects': class_subjects, 'class_subject_id': class_subject_id,
    }


@subjects_bp.route('/scores/scan', methods=['GET', 'POST'])
@login_required
def scoresheet_scan():
    """Upload a photographed score sheet and OCR it into an editable grid."""
    if not can_enter_results() and not is_admin():
        flash('You do not have permission to enter scores.', 'error')
        return redirect(url_for('main.dashboard'))

    from utils.waec_ocr import (
        tesseract_available, extract_text, extract_text_from_pdf,
        parse_score_sheet, match_student,
    )

    ctx = _scan_selector_context()

    if request.method == 'POST':
        term_id = ctx['term_id']
        assignment_id = ctx['assignment_id']
        class_subject_id = ctx['class_subject_id']

        assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
        class_subject = ClassSubject.query.get(class_subject_id) if class_subject_id else None

        if not (assignment and class_subject):
            flash('Select a class and subject before uploading.', 'error')
            return render_template('subjects/scoresheet_scan.html', **ctx)

        if not can_access_class(assignment_id):
            flash('You do not have access to this class.', 'error')
            return redirect(url_for('subjects.scoresheet_scan'))

        if not tesseract_available():
            flash('OCR engine (Tesseract) is not available on the server.', 'error')
            return render_template('subjects/scoresheet_scan.html', **ctx)

        upload = request.files.get('file')
        if not upload or not upload.filename:
            flash('No file selected.', 'error')
            return render_template('subjects/scoresheet_scan.html', **ctx)

        data = upload.read()
        try:
            if upload.filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(data)
            else:
                text = extract_text(data)
        except Exception as e:
            flash(f'Could not read the image: {e}', 'error')
            return render_template('subjects/scoresheet_scan.html', **ctx)

        sheet_cols = _sheet_columns(class_subject)
        parsed = parse_score_sheet(text, num_columns=len(sheet_cols))

        if not parsed:
            flash('No student rows could be detected. Try a clearer, straight photo.', 'warning')
            return render_template('subjects/scoresheet_scan.html', **ctx)

        # Students enrolled in this class (for matching + the picker).
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True
        ).join(Student).order_by(Student.surname, Student.first_name).all()
        students = [e.student for e in enrollments]
        by_student_id = {s.student_id: s for s in students}

        rows = []
        for p in parsed:
            matched = None
            # 1) exact match on a scanned student number
            if p['student_num'] and p['student_num'] in by_student_id:
                matched = by_student_id[p['student_num']]
            # 2) fuzzy match on the name
            if not matched:
                matched, _ = match_student(p['name'], students)
            # Map the positional cells to assessment-type ids.
            cell_map = {}
            for (at, _mx), value in zip(sheet_cols, p['cells']):
                cell_map[at.id] = value
            rows.append({
                'student_num': p['student_num'],
                'name': p['name'],
                'matched_id': matched.id if matched else None,
                'cells': cell_map,
            })

        return render_template('subjects/scoresheet_review.html',
            term_id=term_id, assignment_id=assignment_id, class_subject_id=class_subject_id,
            assignment=assignment, class_subject=class_subject,
            columns=sheet_cols, rows=rows, students=students,
        )

    return render_template('subjects/scoresheet_scan.html', **ctx)


@subjects_bp.route('/scores/scan/save', methods=['POST'])
@login_required
def scoresheet_save():
    """Persist the reviewed score-sheet grid as StudentScores."""
    import re as _re

    if not can_enter_results() and not is_admin():
        flash('You do not have permission to enter scores.', 'error')
        return redirect(url_for('main.dashboard'))

    term_id = request.form.get('term_id', type=int)
    assignment_id = request.form.get('assignment_id', type=int)
    class_subject_id = request.form.get('class_subject_id', type=int)
    row_count = request.form.get('row_count', type=int) or 0

    assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    class_subject = ClassSubject.query.get(class_subject_id) if class_subject_id else None

    if not (assignment and class_subject):
        flash('Missing class/subject context.', 'error')
        return redirect(url_for('subjects.scoresheet_scan'))

    if not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.scoresheet_scan'))

    sheet_cols = _sheet_columns(class_subject)
    auto_id_re = _re.compile(r'^STU\d{3,}$')

    saved_rows = 0
    saved_scores = 0
    adopted = 0
    warnings = []

    try:
        for r in range(row_count):
            student_pk = request.form.get(f'student_{r}', type=int)
            if not student_pk:
                continue  # row skipped by the user
            student = Student.query.get(student_pk)
            if not student:
                continue

            # Adopt the scanned student number only when the student currently
            # has an auto-generated STU##### id (never overwrite a manual id).
            scanned = (request.form.get(f'studentnum_{r}') or '').strip()
            if scanned and scanned != student.student_id and auto_id_re.match(student.student_id or ''):
                clash = Student.query.filter(
                    Student.student_id == scanned, Student.id != student.id).first()
                if clash:
                    warnings.append(f"{student.full_name}: number {scanned} already used by {clash.full_name}")
                else:
                    student.student_id = scanned
                    adopted += 1

            row_has_score = False
            for at, max_score in sheet_cols:
                raw = (request.form.get(f'cell_{r}_{at.id}') or '').strip()
                if raw == '':
                    continue
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if value < 0:
                    value = 0
                if max_score and value > max_score:
                    value = max_score

                existing = StudentScore.query.filter_by(
                    student_id=student.id,
                    class_subject_id=class_subject_id,
                    assessment_type_id=at.id,
                ).first()
                if existing:
                    existing.score = value
                else:
                    db.session.add(StudentScore(
                        student_id=student.id,
                        class_subject_id=class_subject_id,
                        assessment_type_id=at.id,
                        score=value,
                    ))
                saved_scores += 1
                row_has_score = True

            if row_has_score:
                saved_rows += 1

        db.session.commit()
        flash(f'Saved {saved_scores} scores for {saved_rows} students.', 'success')
        if adopted:
            flash(f'Adopted scanned student number for {adopted} student(s).', 'info')
        for w in warnings[:5]:
            flash(w, 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving scores: {e}', 'error')

    return redirect(url_for('subjects.scores_entry',
        term_id=term_id, assignment_id=assignment_id, class_subject_id=class_subject_id))


# ============================================================================
# PRINT ALL REPORT CARDS
# ============================================================================

@subjects_bp.route('/report-cards/print-all')
@login_required
def print_all_report_cards():
    """Print all report cards for a class"""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = Term.query.get(term_id) if term_id else None
    
    assignments = []
    if term_id:
        assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
    
    selected_assignment = ClassArmAssignment.query.get(assignment_id) if assignment_id else None
    
    all_reports = []
    
    if selected_assignment and selected_term:
        assessment_types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
        pass_mark = SchoolSettings.get('pass_mark', 50)
        
        class_subjects = ClassSubject.query.filter_by(
            term_id=term_id,
            class_id=selected_assignment.class_id,
            is_active=True
        ).filter(
            (ClassSubject.arm_id == None) | (ClassSubject.arm_id == selected_assignment.arm_id)
        ).join(Subject).order_by(Subject.name).all()
        
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).join(Student).order_by(Student.surname, Student.first_name).all()
        
        for enrollment in enrollments:
            student = enrollment.student
            subjects_data = []
            total_score = 0
            subjects_passed = 0
            subjects_failed = 0
            
            for cs in class_subjects:
                subject_row = {
                    'subject': cs.subject,
                    'assessments': {},
                    'total': 0,
                    'grade': '-',
                    'remark': '-'
                }
                
                scores = StudentScore.query.filter_by(
                    student_id=student.id,
                    class_subject_id=cs.id
                ).all()
                
                scores_dict = {s.assessment_type_id: s.score for s in scores}
                
                subject_total = 0
                for at in assessment_types:
                    score = scores_dict.get(at.id)
                    subject_row['assessments'][at.id] = score
                    if score:
                        subject_total += score
                
                subject_row['total'] = subject_total
                if subject_total > 0:
                    subject_row['grade'] = GradeScale.get_grade(subject_total)
                    subject_row['remark'] = GradeScale.get_remark(subject_total)
                    total_score += subject_total
                    
                    if subject_total >= pass_mark:
                        subjects_passed += 1
                    else:
                        subjects_failed += 1
                
                subjects_data.append(subject_row)
            
            average = round(total_score / len(class_subjects), 2) if class_subjects else 0
            
            all_reports.append({
                'student': student,
                'enrollment': enrollment,
                'subjects': subjects_data,
                'assessment_types': assessment_types,
                'total_score': total_score,
                'average': average,
                'overall_grade': GradeScale.get_grade(average) if average else '-',
                'subjects_passed': subjects_passed,
                'subjects_failed': subjects_failed,
                'total_subjects': len(class_subjects)
            })
    
    school_name = SchoolSettings.get('school_name', 'School Name')
    
    return render_template('subjects/print_all_report_cards.html',
        terms=terms, term_id=term_id, selected_term=selected_term,
        assignments=assignments, assignment_id=assignment_id, selected_assignment=selected_assignment,
        all_reports=all_reports, school_name=school_name
    )
