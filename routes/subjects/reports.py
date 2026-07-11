"""subjects blueprint — reports routes (split from the former routes/subjects.py)."""
from routes.subjects import *  # noqa: F401,F403
from utils.security import strip_tags


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
    
    selected_term = db.session.get(Term, term_id) if term_id else None
    
    # Filter assignments for teachers
    assignments = []
    if term_id:
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        assignments = filter_classes_for_user(all_assignments)
    
    selected_assignment = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    
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
        
        # Get enrolled students (eager-load the student to avoid a lazy load each)
        from sqlalchemy.orm import joinedload
        enrollments = (StudentEnrollment.query
                       .options(joinedload(StudentEnrollment.student))
                       .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                       .join(Student).order_by(Student.surname, Student.first_name).all())

        pass_mark = SchoolSettings.get('pass_mark', 50)

        # Every score for the whole class in one query, indexed by (student,
        # class-subject, assessment) — replaces a query per student × subject.
        cs_ids = [cs.id for cs in class_subjects]
        sids = [e.student_id for e in enrollments]
        score_map = {}
        if cs_ids and sids:
            for s in StudentScore.query.filter(
                    StudentScore.student_id.in_(sids),
                    StudentScore.class_subject_id.in_(cs_ids)).all():
                score_map[(s.student_id, s.class_subject_id, s.assessment_type_id)] = s.score

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

                subject_total = 0
                for at in assessment_types:
                    score = score_map.get((enrollment.student_id, cs.id, at.id))
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
    
    return _render({
        'page': 'broadsheet', 'nav': _nav_urls(),
        'term_id': term_id or '', 'assignment_id': assignment_id or '',
        'selected_assignment': selected_assignment.display_name if selected_assignment else '',
        'has_selection': bool(selected_assignment),
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'assignments': [{'id': a.id, 'display_name': a.display_name} for a in assignments],
        'class_subjects': [{'id': cs.id, 'short': cs.subject.short_name or cs.subject.name[:3],
                            'name': cs.subject.name} for cs in class_subjects],
        'rows': [{'position': r['position'], 'student': r['student'].full_name,
                  'subjects': {str(cs.id): (round(r['subjects'].get(cs.id, {}).get('total', 0), 1)
                                            if r['subjects'].get(cs.id, {}).get('total') else None)
                               for cs in class_subjects},
                  'total': round(r['total'], 1), 'average': r['average'],
                  'passed': r['subjects_passed'], 'failed': r['subjects_failed']}
                 for r in broadsheet_data],
        'self_url': url_for('subjects.broadsheet'),
        'urls': {'compute': url_for('subjects.compute_summaries'),
                 'bulk_entry': url_for('subjects.bulk_entry', term_id=term_id or '', assignment_id=assignment_id or ''),
                 'affective': url_for('subjects.affective', term_id=term_id or '', assignment_id=assignment_id or ''),
                 'comments': url_for('subjects.comments', term_id=term_id or '', assignment_id=assignment_id or ''),
                 'export': url_for('subjects.export_broadsheet', term_id=term_id or '', assignment_id=assignment_id or ''),
                 'scores': url_for('subjects.scores_entry', term_id=term_id or '', assignment_id=assignment_id or ''),
                 'analytics': url_for('subjects.analytics_dashboard', term_id=term_id or '', assignment_id=assignment_id or '')},
    })


@subjects_bp.route('/broadsheet/compute', methods=['POST'])
@login_required
def compute_summaries():
    """Compute & persist term results + class/arm positions for a class."""
    term_id = request.form.get('term_id', type=int)
    assignment_id = request.form.get('assignment_id', type=int)
    asg = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    if not (term_id and asg):
        return _err('Select a term and class first.', url_for('subjects.broadsheet'))
    from utils.report_card import compute_term_summaries
    from utils.audit import log_action
    count = compute_term_summaries(term_id, asg.class_id)
    log_action('results.compute_summaries',
               detail=f'term {term_id}, class {asg.class_id}: {count} student(s)')
    return _ok(f'Computed results and positions for {count} student(s).',
               url_for('subjects.broadsheet', term_id=term_id, assignment_id=assignment_id))


@subjects_bp.route('/analytics')
@login_required
def analytics_dashboard():
    """Academic analytics for a class in a term — grade distribution, subject
    difficulty, pass/fail rate, intervention list and a term-on-term trend.
    Computed from entered scores (cached; ?refresh=1 forces recomputation)."""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('subjects.analytics_dashboard'))
    terms = Term.query.order_by(Term.id.desc()).all()
    assignments = (filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term_id).all()) if term_id else [])
    data = None
    if term_id and assignment_id:
        from utils.results_analytics import class_analytics
        data = class_analytics(term_id, assignment_id,
                               use_cache=(request.args.get('refresh') != '1'))
    return _render({
        'page': 'analytics', 'nav': _nav_urls(),
        'term_id': term_id or '', 'assignment_id': assignment_id or '',
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'assignments': [{'id': a.id, 'display_name': a.display_name} for a in assignments],
        'has_selection': bool(term_id and assignment_id),
        'analytics': data,
        'self_url': url_for('subjects.analytics_dashboard'),
        'refresh_url': url_for('subjects.analytics_dashboard', term_id=term_id or '',
                               assignment_id=assignment_id or '', refresh=1),
        'report_card_base': url_for('subjects.student_report_card', student_id=0)[:-1],
        'urls': {'broadsheet': url_for('subjects.broadsheet', term_id=term_id or '', assignment_id=assignment_id or ''),
                 'scores': url_for('subjects.scores_entry', term_id=term_id or '', assignment_id=assignment_id or '')},
    })


@subjects_bp.route('/affective', methods=['GET', 'POST'])
@login_required
def affective():
    """Enter behavioural / affective ratings (1–5) for a class arm in a term."""
    from utils.report_card import active_traits
    AFFECTIVE_TRAITS = active_traits()
    AFFECTIVE_KEYS = [k for k, _ in AFFECTIVE_TRAITS]
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
    selected_assignment = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None

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
        return _ok('Behavioural ratings saved.',
                   url_for('subjects.affective', term_id=term_id, assignment_id=assignment_id))

    students = []
    if selected_assignment:
        enrollments = (StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True)
            .join(Student).order_by(Student.surname, Student.first_name).all())
        ratings = {ts.student_id: ts.affective_map
                   for ts in TermSummary.query.filter_by(term_id=term_id).all()}
        for e in enrollments:
            students.append({'student': e.student, 'ratings': ratings.get(e.student_id, {})})

    return _render({
        'page': 'affective', 'nav': _nav_urls(),
        'term_id': term_id or '', 'assignment_id': assignment_id or '',
        'has_students': bool(selected_assignment and students),
        'selected': bool(selected_assignment),
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'assignments': [{'id': a.id, 'display_name': a.display_name} for a in assignments],
        'traits': [{'key': k, 'label': lbl} for k, lbl in AFFECTIVE_TRAITS],
        'students': [{'id': r['student'].id, 'full_name': r['student'].full_name,
                      'ratings': r['ratings']} for r in students],
        'self_url': url_for('subjects.affective'), 'submit_url': url_for('subjects.affective'),
        'broadsheet_url': url_for('subjects.broadsheet', term_id=term_id or '', assignment_id=assignment_id or ''),
    })


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
    selected_assignment = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None

    if request.method == 'POST' and selected_assignment and term_id:
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id, is_active=True).all()
        for e in enrollments:
            ts = TermSummary.query.filter_by(student_id=e.student_id, term_id=term_id).first()
            if not ts:
                ts = TermSummary(student_id=e.student_id, term_id=term_id, enrollment_id=e.id)
                db.session.add(ts)
            ts.teacher_comment = strip_tags(request.form.get(f't_{e.student_id}')) or None
            ts.principal_comment = strip_tags(request.form.get(f'p_{e.student_id}')) or None
        db.session.commit()
        from utils.audit import log_action
        log_action('results.comments', detail=f'term {term_id}, {selected_assignment.display_name}')
        return _ok('Comments saved.',
                   url_for('subjects.comments', term_id=term_id, assignment_id=assignment_id))

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

    return _render({
        'page': 'comments', 'nav': _nav_urls(),
        'term_id': term_id or '', 'assignment_id': assignment_id or '',
        'has_students': bool(selected_assignment and students),
        'selected': bool(selected_assignment),
        'terms': [{'id': t.id, 'full_name': t.full_name} for t in terms],
        'assignments': [{'id': a.id, 'display_name': a.display_name} for a in assignments],
        'students': [{'id': r['student'].id, 'full_name': r['student'].full_name,
                      'teacher_comment': r['teacher_comment'] or '',
                      'principal_comment': r['principal_comment'] or ''} for r in students],
        'self_url': url_for('subjects.comments'), 'submit_url': url_for('subjects.comments'),
        'broadsheet_url': url_for('subjects.broadsheet', term_id=term_id or '', assignment_id=assignment_id or ''),
    })


@subjects_bp.route('/report-card/<int:student_id>')
@login_required
@result_card_required
def student_report_card(student_id):
    """View student report card"""
    student = db.get_or_404(Student, student_id)
    from utils.access_control import assert_student_access
    assert_student_access(student)   # branch + form-teacher scope
    term_id = request.args.get('term_id', type=int)

    terms = Term.query.order_by(Term.id.desc()).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = db.session.get(Term, term_id) if term_id else None

    report_data = None
    enrollment = None

    from utils.report_card import active_traits, RATING_LABELS
    if selected_term:
        from utils.report_card import build_report_card
        enrollment, report_data = build_report_card(student_id, term_id)

    return render_template('subjects/report_card.html',
        student=student, terms=terms, term_id=term_id, selected_term=selected_term,
        report_data=report_data, enrollment=enrollment,
        affective_traits=active_traits(), rating_labels=RATING_LABELS
    )


@subjects_bp.route('/report-card/<int:student_id>/pdf')
@login_required
@result_card_required
def report_card_pdf(student_id):
    """Download the student's term report card as a PDF."""
    from flask import send_file
    from utils.report_card import build_report_card, active_traits, RATING_LABELS
    from utils.report_pdf import report_card_pdf as build_pdf
    from utils.access_control import assert_student_access
    student = db.get_or_404(Student, student_id)
    assert_student_access(student)   # branch + form-teacher scope
    term_id = request.args.get('term_id', type=int) or (
        get_active_term().id if get_active_term() else None)
    _, report_data = build_report_card(student_id, term_id) if term_id else (None, None)
    if not report_data:
        flash('No results to export for this term.', 'error')
        return redirect(url_for('subjects.student_report_card', student_id=student_id, term_id=term_id))
    term = db.session.get(Term, term_id)
    buf = build_pdf(student, report_data, term,
                    SchoolSettings.get('school_name', 'School'),
                    active_traits(), RATING_LABELS)
    name = f"{student.student_id}_{term.name.replace(' ', '_')}_report.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=name)


@subjects_bp.route('/report-cards/pdf')
@login_required
@result_card_required
def report_cards_pdf_batch():
    """Download every report card for a class+term as one PDF (one per page).
    Reuses the single-card renderer, so batch pages match the individual PDFs."""
    from flask import send_file
    from utils.report_card import build_report_card, active_traits, RATING_LABELS
    from utils.report_pdf import batch_report_cards_pdf
    from sqlalchemy.orm import joinedload
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    if not term_id or not assignment_id:
        flash('Select a term and class first.', 'error')
        return redirect(url_for('subjects.print_all_report_cards', term_id=term_id or ''))
    if not can_access_class(assignment_id):
        flash('You do not have access to that class.', 'error')
        return redirect(url_for('subjects.print_all_report_cards'))
    term = db.session.get(Term, term_id)
    asg = db.session.get(ClassArmAssignment, assignment_id)
    if not term or not asg:
        flash('Select a term and class first.', 'error')
        return redirect(url_for('subjects.print_all_report_cards'))
    enrollments = (StudentEnrollment.query
                   .options(joinedload(StudentEnrollment.student))
                   .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                   .join(Student).order_by(Student.surname, Student.first_name).all())
    cards = []
    for e in enrollments:
        _, rc = build_report_card(e.student_id, term_id)
        if rc:
            cards.append((e.student, rc, term))
    if not cards:
        flash('No results to export for this class yet.', 'error')
        return redirect(url_for('subjects.print_all_report_cards', term_id=term_id, assignment_id=assignment_id))
    buf = batch_report_cards_pdf(cards, SchoolSettings.get('school_name', 'School'),
                                 active_traits(), RATING_LABELS,
                                 title=f'{asg.display_name} — {term.full_name}')
    from utils.audit import log_action
    log_action('results.report_cards_pdf', detail=f'{asg.display_name} {term.name}: {len(cards)} card(s)')
    name = f"{asg.display_name.replace(' ', '_')}_{term.name.replace(' ', '_')}_report_cards.pdf"
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=name)


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
    
    selected_term = db.session.get(Term, term_id)
    selected_assignment = db.session.get(ClassArmAssignment, assignment_id)
    
    if not selected_term or not selected_assignment:
        flash('Invalid selection.', 'error')
        return redirect(url_for('subjects.broadsheet'))
    if not can_access_class(assignment_id):
        flash('You do not have access to that class.', 'error')
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
    
    filename = f"broadsheet_{selected_assignment.display_name.replace(' ', '_')}_{selected_term.name}.xlsx"

    return xlsx_response(wb, filename)


@subjects_bp.route('/report-cards/print-all')
@login_required
@result_card_required
def print_all_report_cards():
    """Print all report cards for a class"""
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    
    terms = Term.query.order_by(Term.id.desc()).all()
    
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    selected_term = db.session.get(Term, term_id) if term_id else None

    # A user may only print report cards for classes they can access.
    if assignment_id and not can_access_class(assignment_id):
        flash('You do not have access to that class.', 'error')
        return redirect(url_for('subjects.print_all_report_cards', term_id=term_id))

    assignments = []
    if term_id:
        assignments = filter_classes_for_user(
            ClassArmAssignment.query.filter_by(term_id=term_id).all())

    selected_assignment = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    
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
        
        from sqlalchemy.orm import joinedload
        enrollments = (StudentEnrollment.query
                       .options(joinedload(StudentEnrollment.student))
                       .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                       .join(Student).order_by(Student.surname, Student.first_name).all())

        # Every score for the class in one query, indexed by (student,
        # class-subject, assessment) — was a query per student × subject, the
        # main cost when printing a whole class.
        cs_ids = [cs.id for cs in class_subjects]
        sids = [e.student_id for e in enrollments]
        score_map = {}
        if cs_ids and sids:
            for s in StudentScore.query.filter(
                    StudentScore.student_id.in_(sids),
                    StudentScore.class_subject_id.in_(cs_ids)).all():
                score_map[(s.student_id, s.class_subject_id, s.assessment_type_id)] = s.score

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

                subject_total = 0
                for at in assessment_types:
                    score = score_map.get((student.id, cs.id, at.id))
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
