"""
Mock JAMB Examination Routes
Full management of mock JAMB exams with analytics and insights
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from utils.helpers import get_active_term, get_active_session
from datetime import datetime
from io import BytesIO
from utils.web_exports import xlsx_response

from models import db, Student, AcademicSession, StudentEnrollment, ClassArmAssignment, SchoolClass
from models.mock_jamb import MockJAMBExam, MockJAMBResult, MockJAMBAnalytics
from utils.helpers import login_required, WAEC_SUBJECTS, get_sss3_students, student_subject_map
from utils.branch_scope import require_branch_access, branch_for_new, scope_query
from utils.csrf import csrf_protect
from utils.jamb_config import (
    convert_correct_to_100, question_count_map, COMPULSORY_SUBJECT,
    MAX_TOTAL_SCORE,
)

mock_jamb_bp = Blueprint('mock_jamb', __name__, url_prefix='/mock-jamb')


def _read_subject_scores(form, suffix=''):
    """
    Read the four subject rows from a submitted form and return a normalised
    list of ``{'name', 'score'}`` dicts.

    Each row may supply either ``subjectN_correct`` (raw number of correct
    answers, which is converted to a score over 100) or, for backwards
    compatibility, an already-computed ``subjectN_score``.
    """
    def safe_int(val):
        try:
            return int(val) if val not in (None, '') else None
        except (TypeError, ValueError):
            return None

    rows = []
    for n in range(1, 5):
        name = (form.get(f'subject{n}{suffix}') or '').strip() or None
        correct = form.get(f'subject{n}_correct{suffix}')
        if correct not in (None, ''):
            score = convert_correct_to_100(name, correct)
        else:
            score = safe_int(form.get(f'subject{n}_score{suffix}'))
        if name is None:
            score = None
        rows.append({'name': name, 'score': score})
    return rows


# =============================================================================
# DASHBOARD & OVERVIEW
# =============================================================================

@mock_jamb_bp.route('/')
@login_required
def index():
    """Mock JAMB main dashboard"""
    active_session = get_active_session()
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    session_id = request.args.get('session_id', type=int)
    if not session_id and active_session:
        session_id = active_session.id
    
    exams = []
    comparison_data = None
    
    if session_id:
        exams = scope_query(MockJAMBExam.query.filter_by(session_id=session_id),
                            MockJAMBExam).order_by(MockJAMBExam.exam_number).all()
        comparison_data = MockJAMBAnalytics.compare_mock_exams(session_id)
    
    return render_template('mock_jamb/index.html',
        sessions=sessions,
        selected_session_id=session_id,
        active_session=active_session,
        exams=exams,
        comparison_data=comparison_data,
        max_mock_exams=4
    )


# =============================================================================
# EXAM MANAGEMENT
# =============================================================================

@mock_jamb_bp.route('/exam/create', methods=['GET', 'POST'])
@login_required
@csrf_protect
def create_exam():
    """Create a new mock JAMB exam"""
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    if request.method == 'POST':
        try:
            session_id = request.form.get('session_id', type=int)
            exam_number = request.form.get('exam_number', type=int)
            exam_date = request.form.get('exam_date')
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            
            # Validate
            if not session_id or not exam_number or not exam_date:
                flash('Please fill all required fields.', 'error')
                return redirect(url_for('mock_jamb.create_exam'))
            
            # The new exam belongs to the creator's branch; uniqueness of the
            # exam number is per (session, branch).
            new_branch_id = branch_for_new(request.form.get('branch_id', type=int))
            existing = MockJAMBExam.query.filter_by(
                session_id=session_id, exam_number=exam_number, branch_id=new_branch_id).first()
            if existing:
                flash(f'Mock exam #{exam_number} already exists for this session.', 'error')
                return redirect(url_for('mock_jamb.create_exam'))
            
            # Parse date
            try:
                exam_date = datetime.strptime(exam_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format.', 'error')
                return redirect(url_for('mock_jamb.create_exam'))
            
            # Create exam
            session_obj = db.session.get(AcademicSession, session_id)
            if not name:
                ordinals = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth'}
                name = f"{ordinals.get(exam_number, str(exam_number))} Mock JAMB {session_obj.name}"
            
            exam = MockJAMBExam(
                name=name,
                exam_number=exam_number,
                session_id=session_id,
                exam_date=exam_date,
                description=description,
                branch_id=new_branch_id
            )
            
            db.session.add(exam)
            db.session.commit()
            
            flash(f'{exam.display_name} created successfully!', 'success')
            return redirect(url_for('mock_jamb.index', session_id=session_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating exam: {str(e)}', 'error')
    
    # Get existing exam numbers for each session
    existing_exams = {}
    for sess in sessions:
        existing_exams[sess.id] = [e.exam_number for e in MockJAMBExam.query.filter_by(session_id=sess.id).all()]
    
    return render_template('mock_jamb/create_exam.html',
        sessions=sessions,
        existing_exams=existing_exams
    )


@mock_jamb_bp.route('/exam/<int:exam_id>')
@login_required
def view_exam(exam_id):
    """View a specific mock exam with detailed statistics"""
    exam = db.get_or_404(MockJAMBExam, exam_id)
    require_branch_access(exam.branch_id)   # no cross-branch exam data
    statistics = MockJAMBAnalytics.get_exam_statistics(exam_id)
    
    # Get sort and filter parameters
    sort_by = request.args.get('sort', 'score')
    sort_order = request.args.get('order', 'desc')
    min_score = request.args.get('min_score', type=int)
    max_score = request.args.get('max_score', type=int)
    search = request.args.get('search', '').strip()
    
    # Build query for results
    query = MockJAMBResult.query.filter_by(mock_exam_id=exam_id).join(Student)
    
    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Student.first_name.ilike(search_term),
                Student.surname.ilike(search_term),
                Student.middle_name.ilike(search_term),
                Student.student_id.ilike(search_term)
            )
        )
    
    if min_score:
        query = query.filter(MockJAMBResult.total_score >= min_score)
    if max_score:
        query = query.filter(MockJAMBResult.total_score <= max_score)
    
    if sort_by == 'score':
        if sort_order == 'desc':
            query = query.order_by(MockJAMBResult.total_score.desc())
        else:
            query = query.order_by(MockJAMBResult.total_score.asc())
    elif sort_by == 'name':
        if sort_order == 'desc':
            query = query.order_by(Student.surname.desc())
        else:
            query = query.order_by(Student.surname.asc())
    else:
        query = query.order_by(MockJAMBResult.total_score.desc())
    
    results = query.all()
    
    # Add rank to results
    results_with_rank = []
    for idx, r in enumerate(results):
        results_with_rank.append({
            'result': r,
            'rank': idx + 1,
            'student': r.student
        })
    
    return render_template('mock_jamb/view_exam.html',
        exam=exam,
        statistics=statistics,
        results=results_with_rank,
        sort_by=sort_by,
        sort_order=sort_order,
        min_score=min_score,
        max_score=max_score,
        search=search
    )


@mock_jamb_bp.route('/exam/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
@csrf_protect
def edit_exam(exam_id):
    """Edit mock exam details"""
    exam = db.get_or_404(MockJAMBExam, exam_id)
    require_branch_access(exam.branch_id)

    if request.method == 'POST':
        try:
            exam.name = request.form.get('name', '').strip()
            exam.description = request.form.get('description', '').strip()
            
            exam_date = request.form.get('exam_date')
            if exam_date:
                exam.exam_date = datetime.strptime(exam_date, '%Y-%m-%d').date()
            
            exam.is_completed = request.form.get('is_completed') == 'on'
            
            db.session.commit()
            flash('Exam updated successfully!', 'success')
            return redirect(url_for('mock_jamb.view_exam', exam_id=exam_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating exam: {str(e)}', 'error')
    
    return render_template('mock_jamb/edit_exam.html', exam=exam)


@mock_jamb_bp.route('/exam/<int:exam_id>/delete', methods=['POST'])
@login_required
@csrf_protect
def delete_exam(exam_id):
    """Delete a mock exam and all its results"""
    exam = db.get_or_404(MockJAMBExam, exam_id)
    require_branch_access(exam.branch_id)
    session_id = exam.session_id
    exam_name = exam.display_name
    
    try:
        db.session.delete(exam)
        db.session.commit()
        flash(f'{exam_name} and all its results have been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting exam: {str(e)}', 'error')
    
    return redirect(url_for('mock_jamb.index', session_id=session_id))


# =============================================================================
# RESULT ENTRY
# =============================================================================

@mock_jamb_bp.route('/exam/<int:exam_id>/results/add', methods=['GET', 'POST'])
@login_required
@csrf_protect
def add_result(exam_id):
    """Add results for a student"""
    exam = db.get_or_404(MockJAMBExam, exam_id)
    require_branch_access(exam.branch_id)
    
    # SSS3 students who don't already have a result for this exam.
    existing_student_ids = {r.student_id for r in exam.results}
    students = [s for s in get_sss3_students() if s.id not in existing_student_ids]
    
    if request.method == 'POST':
        try:
            student_id = request.form.get('student_id', type=int)

            if not student_id:
                flash('Please select a student.', 'error')
                return redirect(url_for('mock_jamb.add_result', exam_id=exam_id))

            # Check if result already exists
            existing = MockJAMBResult.query.filter_by(student_id=student_id, mock_exam_id=exam_id).first()
            if existing:
                flash('Result already exists for this student. Edit instead.', 'error')
                return redirect(url_for('mock_jamb.add_result', exam_id=exam_id))

            # Read each subject and convert the raw number of correct answers
            # (out of 60 for English, 40 for others) into a score over 100.
            subjects_payload = _read_subject_scores(request.form)
            total_score = sum(s['score'] for s in subjects_payload if s['score'] is not None)

            if total_score < 0 or total_score > MAX_TOTAL_SCORE:
                flash(f'Total score must be between 0 and {MAX_TOTAL_SCORE}.', 'error')
                return redirect(url_for('mock_jamb.add_result', exam_id=exam_id))

            result = MockJAMBResult(
                student_id=student_id,
                mock_exam_id=exam_id,
                total_score=total_score,
                subject1=subjects_payload[0]['name'],
                subject1_score=subjects_payload[0]['score'],
                subject2=subjects_payload[1]['name'],
                subject2_score=subjects_payload[1]['score'],
                subject3=subjects_payload[2]['name'],
                subject3_score=subjects_payload[2]['score'],
                subject4=subjects_payload[3]['name'],
                subject4_score=subjects_payload[3]['score'],
            )

            db.session.add(result)
            db.session.commit()
            
            flash('Result added successfully!', 'success')
            
            # Check if more students to add
            if request.form.get('add_another'):
                return redirect(url_for('mock_jamb.add_result', exam_id=exam_id))
            
            return redirect(url_for('mock_jamb.view_exam', exam_id=exam_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding result: {str(e)}', 'error')
    
    return render_template('mock_jamb/add_result.html',
        exam=exam,
        students=students,
        subjects=WAEC_SUBJECTS,
        question_counts=question_count_map(WAEC_SUBJECTS),
        compulsory_subject=COMPULSORY_SUBJECT,
        subject_map=student_subject_map(students)
    )


@mock_jamb_bp.route('/exam/<int:exam_id>/results/bulk', methods=['GET', 'POST'])
@login_required
@csrf_protect
def bulk_entry(exam_id):
    """Bulk entry of results for multiple students"""
    exam = db.get_or_404(MockJAMBExam, exam_id)
    require_branch_access(exam.branch_id)
    
    # Get active term to find enrolled students
    active_term = get_active_term()
    
    # Get SS3 students (most likely to take mock JAMB)
    sss3 = SchoolClass.query.filter_by(name='SSS3').first()
    
    students = []
    if sss3 and active_term:
        assignments = ClassArmAssignment.query.filter_by(class_id=sss3.id, term_id=active_term.id).all()
        for assignment in assignments:
            enrollments = StudentEnrollment.query.filter_by(
                class_arm_assignment_id=assignment.id,
                is_active=True
            ).join(Student).order_by(Student.surname).all()
            
            for enrollment in enrollments:
                # Check if result exists
                existing = MockJAMBResult.query.filter_by(
                    student_id=enrollment.student_id,
                    mock_exam_id=exam_id
                ).first()
                
                students.append({
                    'student': enrollment.student,
                    'arm': assignment.arm.name,
                    'existing_result': existing
                })
    
    if request.method == 'POST':
        try:
            added = 0
            updated = 0
            
            def safe_int(val):
                try:
                    return int(val) if val else None
                except Exception:
                    return None
            
            for student_data in students:
                student = student_data['student']
                score_key = f'score_{student.id}'
                
                total_score = request.form.get(score_key, type=int)
                if total_score is None:
                    continue
                
                if total_score < 0 or total_score > 400:
                    continue
                
                existing = student_data['existing_result']
                
                if existing:
                    existing.total_score = total_score
                    existing.subject1 = request.form.get(f'subject1_{student.id}', '').strip() or None
                    existing.subject1_score = safe_int(request.form.get(f'subject1_score_{student.id}'))
                    existing.subject2 = request.form.get(f'subject2_{student.id}', '').strip() or None
                    existing.subject2_score = safe_int(request.form.get(f'subject2_score_{student.id}'))
                    existing.subject3 = request.form.get(f'subject3_{student.id}', '').strip() or None
                    existing.subject3_score = safe_int(request.form.get(f'subject3_score_{student.id}'))
                    existing.subject4 = request.form.get(f'subject4_{student.id}', '').strip() or None
                    existing.subject4_score = safe_int(request.form.get(f'subject4_score_{student.id}'))
                    updated += 1
                else:
                    result = MockJAMBResult(
                        student_id=student.id,
                        mock_exam_id=exam_id,
                        total_score=total_score,
                        subject1=request.form.get(f'subject1_{student.id}', '').strip() or None,
                        subject1_score=safe_int(request.form.get(f'subject1_score_{student.id}')),
                        subject2=request.form.get(f'subject2_{student.id}', '').strip() or None,
                        subject2_score=safe_int(request.form.get(f'subject2_score_{student.id}')),
                        subject3=request.form.get(f'subject3_{student.id}', '').strip() or None,
                        subject3_score=safe_int(request.form.get(f'subject3_score_{student.id}')),
                        subject4=request.form.get(f'subject4_{student.id}', '').strip() or None,
                        subject4_score=safe_int(request.form.get(f'subject4_score_{student.id}'))
                    )
                    db.session.add(result)
                    added += 1
            
            db.session.commit()
            flash(f'Results saved! Added: {added}, Updated: {updated}', 'success')
            return redirect(url_for('mock_jamb.view_exam', exam_id=exam_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving results: {str(e)}', 'error')
    
    return render_template('mock_jamb/bulk_entry.html',
        exam=exam,
        students=students,
        subjects=WAEC_SUBJECTS
    )


@mock_jamb_bp.route('/result/<int:result_id>/edit', methods=['GET', 'POST'])
@login_required
@csrf_protect
def edit_result(result_id):
    """Edit a specific result"""
    from utils.branch_scope import require_branch_access
    result = db.get_or_404(MockJAMBResult, result_id)
    require_branch_access(result.student.branch_id)   # scope by the result's student

    if request.method == 'POST':
        try:
            total_score = request.form.get('total_score', type=int)
            
            if total_score is None or total_score < 0 or total_score > 400:
                flash('Invalid total score. Must be between 0 and 400.', 'error')
                return redirect(url_for('mock_jamb.edit_result', result_id=result_id))
            
            def safe_int(val):
                try:
                    return int(val) if val else None
                except Exception:
                    return None
            
            result.total_score = total_score
            result.subject1 = request.form.get('subject1', '').strip() or None
            result.subject1_score = safe_int(request.form.get('subject1_score'))
            result.subject2 = request.form.get('subject2', '').strip() or None
            result.subject2_score = safe_int(request.form.get('subject2_score'))
            result.subject3 = request.form.get('subject3', '').strip() or None
            result.subject3_score = safe_int(request.form.get('subject3_score'))
            result.subject4 = request.form.get('subject4', '').strip() or None
            result.subject4_score = safe_int(request.form.get('subject4_score'))
            
            db.session.commit()
            flash('Result updated successfully!', 'success')
            return redirect(url_for('mock_jamb.view_exam', exam_id=result.mock_exam_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating result: {str(e)}', 'error')
    
    return render_template('mock_jamb/edit_result.html',
        result=result,
        subjects=WAEC_SUBJECTS
    )


@mock_jamb_bp.route('/result/<int:result_id>/delete', methods=['POST'])
@login_required
@csrf_protect
def delete_result(result_id):
    """Delete a result"""
    from utils.branch_scope import require_branch_access
    result = db.get_or_404(MockJAMBResult, result_id)
    require_branch_access(result.student.branch_id)   # scope by the result's student
    exam_id = result.mock_exam_id
    student_name = result.student.full_name
    
    try:
        db.session.delete(result)
        db.session.commit()
        flash(f'Result for {student_name} deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting result: {str(e)}', 'error')
    
    return redirect(url_for('mock_jamb.view_exam', exam_id=exam_id))


# =============================================================================
# STUDENT PROGRESS & ANALYTICS
# =============================================================================

@mock_jamb_bp.route('/student/<int:student_id>')
@login_required
def student_progress(student_id):
    """View a student's progress across all mock exams"""
    student = db.get_or_404(Student, student_id)
    from utils.access_control import assert_student_access
    assert_student_access(student)   # branch + form-teacher scope

    session_id = request.args.get('session_id', type=int)
    active_session = get_active_session()
    if not session_id and active_session:
        session_id = active_session.id
    
    progress = MockJAMBAnalytics.get_student_progress(student_id, session_id)
    prediction = MockJAMBAnalytics.predict_real_jamb(student_id, session_id)
    recommendations = MockJAMBAnalytics.get_improvement_recommendations(student_id, session_id)
    
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    return render_template('mock_jamb/student_progress.html',
        student=student,
        progress=progress,
        prediction=prediction,
        recommendations=recommendations,
        sessions=sessions,
        selected_session_id=session_id
    )


@mock_jamb_bp.route('/analytics')
@login_required
def analytics():
    """Comprehensive analytics dashboard"""
    session_id = request.args.get('session_id', type=int)
    active_session = get_active_session()
    if not session_id and active_session:
        session_id = active_session.id
    
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    comparison = None
    exams_stats = []
    
    if session_id:
        comparison = MockJAMBAnalytics.compare_mock_exams(session_id)
        exams = scope_query(MockJAMBExam.query.filter_by(session_id=session_id),
                            MockJAMBExam).order_by(MockJAMBExam.exam_number).all()
        for exam in exams:
            stats = MockJAMBAnalytics.get_exam_statistics(exam.id)
            if stats:
                exams_stats.append(stats)
    
    return render_template('mock_jamb/analytics.html',
        sessions=sessions,
        selected_session_id=session_id,
        comparison=comparison,
        exams_stats=exams_stats
    )


# =============================================================================
# EXPORT FUNCTIONALITY
# =============================================================================

@mock_jamb_bp.route('/exam/<int:exam_id>/export')
@login_required
def export_results(exam_id):
    """Export exam results to Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

    exam = db.get_or_404(MockJAMBExam, exam_id)
    require_branch_access(exam.branch_id)
    results = MockJAMBResult.query.filter_by(mock_exam_id=exam_id).join(Student).order_by(
        MockJAMBResult.total_score.desc()
    ).all()
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Mock JAMB Results"
    
    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1a5f4a", end_color="1a5f4a", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Title
    ws.merge_cells('A1:M1')
    ws['A1'] = f"{exam.name} - Results"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A1'].alignment = Alignment(horizontal='center')
    
    ws.merge_cells('A2:M2')
    ws['A2'] = f"Date: {exam.exam_date.strftime('%d %B %Y')}"
    ws['A2'].alignment = Alignment(horizontal='center')
    
    # Headers
    headers = ['Rank', 'Student ID', 'Name', 'Subject 1', 'Score 1', 'Subject 2', 'Score 2',
               'Subject 3', 'Score 3', 'Subject 4', 'Score 4', 'Total Score', 'Performance']
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center')
    
    # Data
    for row_idx, result in enumerate(results, 5):
        ws.cell(row=row_idx, column=1, value=row_idx - 4).border = border
        ws.cell(row=row_idx, column=2, value=result.student.student_id).border = border
        ws.cell(row=row_idx, column=3, value=result.student.full_name).border = border
        ws.cell(row=row_idx, column=4, value=result.subject1 or '').border = border
        ws.cell(row=row_idx, column=5, value=result.subject1_score or 0).border = border
        ws.cell(row=row_idx, column=6, value=result.subject2 or '').border = border
        ws.cell(row=row_idx, column=7, value=result.subject2_score or 0).border = border
        ws.cell(row=row_idx, column=8, value=result.subject3 or '').border = border
        ws.cell(row=row_idx, column=9, value=result.subject3_score or 0).border = border
        ws.cell(row=row_idx, column=10, value=result.subject4 or '').border = border
        ws.cell(row=row_idx, column=11, value=result.subject4_score or 0).border = border
        ws.cell(row=row_idx, column=12, value=result.total_score).border = border
        ws.cell(row=row_idx, column=13, value=result.performance_level).border = border
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 25
    for col in ['D', 'F', 'H', 'J']:
        ws.column_dimensions[col].width = 18
    for col in ['E', 'G', 'I', 'K']:
        ws.column_dimensions[col].width = 8
    ws.column_dimensions['L'].width = 12
    ws.column_dimensions['M'].width = 15
    
    filename = f"mock_jamb_{exam.exam_number}_{exam.session.name.replace('/', '_')}.xlsx"

    return xlsx_response(wb, filename)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@mock_jamb_bp.route('/api/exam/<int:exam_id>/stats')
@login_required
def api_exam_stats(exam_id):
    """API endpoint for exam statistics (for charts)"""
    stats = MockJAMBAnalytics.get_exam_statistics(exam_id)
    
    if not stats or not stats['statistics']:
        return jsonify({'error': 'No data available'}), 404
    
    return jsonify({
        'exam_name': stats['exam'].name,
        'student_count': stats['student_count'],
        'statistics': stats['statistics'],
        'distribution': stats['distribution'],
        'subject_analysis': stats['subject_analysis']
    })


@mock_jamb_bp.route('/api/student/<int:student_id>/progress')
@login_required
def api_student_progress(student_id):
    """API endpoint for student progress (for charts)"""
    require_branch_access(db.get_or_404(Student, student_id).branch_id)
    session_id = request.args.get('session_id', type=int)
    progress = MockJAMBAnalytics.get_student_progress(student_id, session_id)
    
    if not progress:
        return jsonify({'error': 'No data available'}), 404
    
    return jsonify(progress)
