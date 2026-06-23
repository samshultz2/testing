"""
Mock JAMB Examination Routes
Full management of mock JAMB exams with analytics and insights
"""
from flask import Blueprint, request, redirect, url_for, flash, jsonify, Response
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

from utils.spa import section_responders
_wants_json, _render, _ok, _err = section_responders(
    'mock_jamb/app.html', 'mj_json', 'mock_jamb.index')


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
    
    def exam_row(e):
        above_200 = sum(1 for r in e.results if r.total_score and r.total_score >= 200)
        return {
            'id': e.id, 'display_name': e.display_name, 'is_completed': bool(e.is_completed),
            'exam_date': e.exam_date.strftime('%d %B %Y') if e.exam_date else '',
            'student_count': e.student_count,
            'average_score': round(e.average_score, 1) if e.student_count > 0 else None,
            'above_200': above_200,
            'view_url': url_for('mock_jamb.view_exam', exam_id=e.id),
            'add_url': url_for('mock_jamb.add_result', exam_id=e.id),
            'bulk_url': url_for('mock_jamb.bulk_entry', exam_id=e.id),
        }
    avg_scores = [e.average_score for e in exams if e.student_count > 0]
    return _render({
        'page': 'index', 'selected_session_id': session_id or '',
        'sessions': [{'id': s.id, 'name': s.name} for s in sessions],
        'exams': [exam_row(e) for e in exams],
        'stats': {'count': len(exams), 'total_results': sum(e.student_count for e in exams),
                  'avg_score': round(sum(avg_scores) / len(avg_scores), 1) if avg_scores else None,
                  'remaining': 4 - len(exams)},
        'comparison': [{'label': c['exam'].display_name, 'average': round(c['average'], 1),
                        'above_250': round((c.get('above_250_pct') or 0) * c['student_count'] / 100)}
                       for c in (comparison_data or [])],
        'urls': {'create': url_for('mock_jamb.create_exam'), 'analytics': url_for('mock_jamb.analytics'),
                 'predictions': url_for('results.predictions_dashboard'), 'self': url_for('mock_jamb.index')},
    })


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
                return _err('Please fill all required fields.', url_for('mock_jamb.create_exam'))

            # The new exam belongs to the creator's branch; uniqueness of the
            # exam number is per (session, branch).
            new_branch_id = branch_for_new(request.form.get('branch_id', type=int))
            existing = MockJAMBExam.query.filter_by(
                session_id=session_id, exam_number=exam_number, branch_id=new_branch_id).first()
            if existing:
                return _err(f'Mock exam #{exam_number} already exists for this session.', url_for('mock_jamb.create_exam'))

            # Parse date
            try:
                exam_date = datetime.strptime(exam_date, '%Y-%m-%d').date()
            except ValueError:
                return _err('Invalid date format.', url_for('mock_jamb.create_exam'))
            
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
            return _ok(f'{exam.display_name} created successfully!',
                       url_for('mock_jamb.index', session_id=session_id))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error creating exam: {str(e)}', url_for('mock_jamb.create_exam'))

    # Get existing exam numbers for each session
    existing_exams = {}
    for sess in sessions:
        existing_exams[str(sess.id)] = [e.exam_number for e in MockJAMBExam.query.filter_by(session_id=sess.id).all()]

    return _render({
        'page': 'create_exam', 'existing_exams': existing_exams,
        'sessions': [{'id': s.id, 'name': s.name} for s in sessions],
        'submit_url': url_for('mock_jamb.create_exam'),
        'urls': {'index': url_for('mock_jamb.index')},
    })


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

    def subj_arr(r):
        out = []
        for i in (1, 2, 3, 4):
            name = getattr(r, f'subject{i}')
            score = getattr(r, f'subject{i}_score')
            out.append({'name': name, 'score': score} if name else None)
        return out

    results_payload = []
    for idx, r in enumerate(results):
        st = r.student
        results_payload.append({
            'rank': idx + 1,
            'student': {'id': st.id, 'full_name': st.full_name, 'student_id': st.student_id,
                        'progress_url': url_for('mock_jamb.student_progress', student_id=st.id)},
            'total_score': r.total_score,
            'performance_level': r.performance_level,
            'perf_class': r.performance_level.lower().replace(' ', '_'),
            'subjects': subj_arr(r),
            'edit_url': url_for('mock_jamb.edit_result', result_id=r.id),
            'delete_url': url_for('mock_jamb.delete_result', result_id=r.id),
        })

    stats_payload = None
    if statistics and statistics.get('statistics'):
        stats_payload = {
            'student_count': statistics['student_count'],
            'statistics': statistics['statistics'],
            'distribution': statistics['distribution'],
            'subject_analysis': statistics['subject_analysis'],
        }

    return _render({
        'page': 'view_exam',
        'exam': {'id': exam.id, 'display_name': exam.display_name,
                 'exam_date': exam.exam_date.strftime('%d %B %Y') if exam.exam_date else '',
                 'session_name': exam.session.name if exam.session else ''},
        'statistics': stats_payload,
        'results': results_payload,
        'filters': {'search': search, 'min_score': min_score or '', 'max_score': max_score or '',
                    'sort': sort_by, 'order': sort_order},
        'has_filter': bool(search or min_score or max_score),
        'urls': {'add': url_for('mock_jamb.add_result', exam_id=exam.id),
                 'bulk': url_for('mock_jamb.bulk_entry', exam_id=exam.id),
                 'export': url_for('mock_jamb.export_results', exam_id=exam.id),
                 'edit': url_for('mock_jamb.edit_exam', exam_id=exam.id),
                 'index': url_for('mock_jamb.index'),
                 'self': url_for('mock_jamb.view_exam', exam_id=exam.id),
                 'delete_exam': url_for('mock_jamb.delete_exam', exam_id=exam.id)},
    })


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
            return _ok('Exam updated successfully!', url_for('mock_jamb.view_exam', exam_id=exam_id))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error updating exam: {str(e)}', url_for('mock_jamb.edit_exam', exam_id=exam_id))

    return _render({
        'page': 'edit_exam',
        'exam': {'id': exam.id, 'name': exam.name or '', 'description': exam.description or '',
                 'exam_date': exam.exam_date.strftime('%Y-%m-%d') if exam.exam_date else '',
                 'is_completed': bool(exam.is_completed), 'display_name': exam.display_name,
                 'session_name': exam.session.name if exam.session else ''},
        'submit_url': url_for('mock_jamb.edit_exam', exam_id=exam.id),
        'delete_url': url_for('mock_jamb.delete_exam', exam_id=exam.id),
        'view_url': url_for('mock_jamb.view_exam', exam_id=exam.id),
    })


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
        return _ok(f'{exam_name} and all its results have been deleted.',
                   url_for('mock_jamb.index', session_id=session_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error deleting exam: {str(e)}', url_for('mock_jamb.index', session_id=session_id))


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
                return _err('Please select a student.', url_for('mock_jamb.add_result', exam_id=exam_id))

            # Check if result already exists
            existing = MockJAMBResult.query.filter_by(student_id=student_id, mock_exam_id=exam_id).first()
            if existing:
                return _err('Result already exists for this student. Edit instead.', url_for('mock_jamb.add_result', exam_id=exam_id))

            # Read each subject and convert the raw number of correct answers
            # (out of 60 for English, 40 for others) into a score over 100.
            subjects_payload = _read_subject_scores(request.form)
            total_score = sum(s['score'] for s in subjects_payload if s['score'] is not None)

            if total_score < 0 or total_score > MAX_TOTAL_SCORE:
                return _err(f'Total score must be between 0 and {MAX_TOTAL_SCORE}.', url_for('mock_jamb.add_result', exam_id=exam_id))

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
            dest = (url_for('mock_jamb.add_result', exam_id=exam_id) if request.form.get('add_another')
                    else url_for('mock_jamb.view_exam', exam_id=exam_id))
            return _ok('Result added successfully!', dest)

        except Exception as e:
            db.session.rollback()
            return _err(f'Error adding result: {str(e)}', url_for('mock_jamb.add_result', exam_id=exam_id))

    return _render({
        'page': 'add_result',
        'exam': {'id': exam.id, 'display_name': exam.display_name,
                 'exam_date': exam.exam_date.strftime('%d %B %Y') if exam.exam_date else ''},
        'students': [{'id': s.id, 'label': f'{s.full_name} ({s.student_id})'} for s in students],
        'subjects': list(WAEC_SUBJECTS),
        'question_counts': question_count_map(WAEC_SUBJECTS),
        'compulsory_subject': COMPULSORY_SUBJECT,
        'subject_map': student_subject_map(students),
        'max_total': MAX_TOTAL_SCORE,
        'submit_url': url_for('mock_jamb.add_result', exam_id=exam.id),
        'view_url': url_for('mock_jamb.view_exam', exam_id=exam.id),
    })


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
        assignments = scope_query(ClassArmAssignment.query.filter_by(
            class_id=sss3.id, term_id=active_term.id), ClassArmAssignment).all()
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
                    'arm': assignment.arm_label,
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
            return _ok(f'Results saved! Added: {added}, Updated: {updated}',
                       url_for('mock_jamb.view_exam', exam_id=exam_id))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error saving results: {str(e)}', url_for('mock_jamb.bulk_entry', exam_id=exam_id))

    return _render({
        'page': 'bulk_entry',
        'exam': {'id': exam.id, 'display_name': exam.display_name},
        'students': [{'id': it['student'].id, 'full_name': it['student'].full_name,
                      'student_id': it['student'].student_id, 'arm': it['arm'],
                      'total_score': it['existing_result'].total_score if it['existing_result'] else '',
                      'entered': bool(it['existing_result'])} for it in students],
        'submit_url': url_for('mock_jamb.bulk_entry', exam_id=exam.id),
        'urls': {'view': url_for('mock_jamb.view_exam', exam_id=exam.id),
                 'add': url_for('mock_jamb.add_result', exam_id=exam.id)},
    })


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
                return _err('Invalid total score. Must be between 0 and 400.',
                            url_for('mock_jamb.edit_result', result_id=result_id))
            
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
            return _ok('Result updated successfully!', url_for('mock_jamb.view_exam', exam_id=result.mock_exam_id))

        except Exception as e:
            db.session.rollback()
            return _err(f'Error updating result: {str(e)}', url_for('mock_jamb.edit_result', result_id=result_id))

    r = result
    return _render({
        'page': 'edit_result',
        'result': {'id': r.id, 'student_name': r.student.full_name, 'student_id': r.student.student_id,
                   'subject1': r.subject1 or '', 'subject1_score': r.subject1_score if r.subject1_score is not None else '',
                   'subject2': r.subject2 or '', 'subject2_score': r.subject2_score if r.subject2_score is not None else '',
                   'subject3': r.subject3 or '', 'subject3_score': r.subject3_score if r.subject3_score is not None else '',
                   'subject4': r.subject4 or '', 'subject4_score': r.subject4_score if r.subject4_score is not None else '',
                   'total_score': r.total_score, 'exam_name': r.exam.display_name,
                   'exam_id': r.mock_exam_id},
        'subjects': list(WAEC_SUBJECTS),
        'submit_url': url_for('mock_jamb.edit_result', result_id=r.id),
        'delete_url': url_for('mock_jamb.delete_result', result_id=r.id),
        'view_url': url_for('mock_jamb.view_exam', exam_id=r.mock_exam_id),
    })


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
        return _ok(f'Result for {student_name} deleted.', url_for('mock_jamb.view_exam', exam_id=exam_id))
    except Exception as e:
        db.session.rollback()
        return _err(f'Error deleting result: {str(e)}', url_for('mock_jamb.view_exam', exam_id=exam_id))


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

    prog_payload = None
    if progress:
        prog_payload = {
            'average_score': progress['average_score'],
            'best_score': progress['best_score'],
            'latest_score': progress['latest_score'],
            'exam_count': progress['exam_count'],
            'progress': [{'exam': p['exam'], 'exam_number': p['exam_number'],
                          'exam_date': p['exam_date'].strftime('%d %b %Y') if p['exam_date'] else '',
                          'score': p['score'], 'change': p['change'],
                          'subjects': p['subjects']} for p in progress['progress']],
        }

    return _render({
        'page': 'student_progress',
        'student': {'id': student.id, 'full_name': student.full_name,
                    'student_id': student.student_id, 'gender': student.gender or '',
                    'jamb_target': student.jamb_target},
        'progress': prog_payload,
        'prediction': prediction,
        'recommendations': recommendations,
        'sessions': [{'id': s.id, 'name': s.name} for s in sessions],
        'selected_session_id': session_id or '',
        'urls': {'index': url_for('mock_jamb.index'),
                 'self': url_for('mock_jamb.student_progress', student_id=student.id),
                 'predictions': url_for('results.student_predictions', student_id=student.id)},
    })


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
        # Only the creator's branch should appear; compare_mock_exams is not
        # branch-scoped, so intersect it with the scoped exam ids.
        scoped_ids = {e.id for e in exams}
        comparison = [c for c in (comparison or []) if c['exam'].id in scoped_ids]
        for exam in exams:
            stats = MockJAMBAnalytics.get_exam_statistics(exam.id)
            if stats:
                exams_stats.append(stats)

    comp_payload = [{'exam': {'id': c['exam'].id, 'display_name': c['exam'].display_name},
                     'student_count': c['student_count'], 'average': c['average'],
                     'max': c['max'], 'min': c['min'], 'above_200': c['above_200'],
                     'above_250_pct': c['above_250_pct']} for c in comparison]
    estats_payload = [{'exam': {'id': s['exam'].id, 'display_name': s['exam'].display_name,
                                'view_url': url_for('mock_jamb.view_exam', exam_id=s['exam'].id),
                                'exam_date': s['exam'].exam_date.strftime('%d %B %Y') if s['exam'].exam_date else ''},
                       'student_count': s['student_count'], 'statistics': s['statistics'],
                       'distribution': s['distribution'], 'subject_analysis': s['subject_analysis']}
                      for s in exams_stats if s.get('statistics')]

    return _render({
        'page': 'analytics',
        'sessions': [{'id': s.id, 'name': s.name} for s in sessions],
        'selected_session_id': session_id or '',
        'comparison': comp_payload,
        'exams_stats': estats_payload,
        'urls': {'index': url_for('mock_jamb.index'), 'create': url_for('mock_jamb.create_exam'),
                 'self': url_for('mock_jamb.analytics')},
    })


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
