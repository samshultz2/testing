"""
Mock WAEC Examination Routes

Full management of internal Mock WAEC exams (multiple per session), mirroring the
real WAEC section but marked out of 100 with auto-derived A1-F9 grades. Includes
single-student entry, a paste-and-preview bulk importer, per-student progression,
school analytics, Excel export, and live feeding of the analytics inference engine.
"""
from datetime import datetime

from flask import (Blueprint, request, redirect, url_for, flash, render_template,
                   abort)
from openpyxl import Workbook

from models import db, Student, AcademicSession
from models.mock_waec import (MockWAECExam, MockWAECResult, MockWAECAnalytics,
                              waec_grade_from_score, PASS_GRADES)
from utils.helpers import (login_required, get_active_session, get_sss3_students,
                           WAEC_SUBJECTS, WAEC_GRADES)
from utils.access_control import admin_required
from utils.branch_scope import require_branch_access, branch_for_new, scope_query
from utils.csrf import csrf_protect
from utils.web_exports import xlsx_response
from utils.analytics_engine import recompute_student_safe

mock_waec_bp = Blueprint('mock_waec', __name__, url_prefix='/mock-waec')

_CANON_SUBJECTS = {s.upper(): s for s in WAEC_SUBJECTS}


# =============================================================================
# DASHBOARD
# =============================================================================

@mock_waec_bp.route('/')
@login_required
def index():
    """Mock WAEC dashboard: exams for the selected session + cohort comparison."""
    active_session = get_active_session()
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()

    session_id = request.args.get('session_id', type=int)
    if not session_id and active_session:
        session_id = active_session.id

    exams, comparison = [], []
    if session_id:
        exams = scope_query(MockWAECExam.query.filter_by(session_id=session_id),
                            MockWAECExam).order_by(MockWAECExam.exam_number).all()
        comparison = MockWAECAnalytics.compare_mock_exams(session_id)

    return render_template('mock_waec/index.html',
        sessions=sessions, selected_session_id=session_id,
        exams=exams, comparison=comparison)


# =============================================================================
# EXAM MANAGEMENT
# =============================================================================

@mock_waec_bp.route('/exam/create', methods=['GET', 'POST'])
@login_required
@csrf_protect
def create_exam():
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    if request.method == 'POST':
        try:
            session_id = request.form.get('session_id', type=int)
            exam_number = request.form.get('exam_number', type=int)
            exam_date = request.form.get('exam_date')
            name = (request.form.get('name') or '').strip()
            description = (request.form.get('description') or '').strip()

            if not session_id or not exam_number or not exam_date:
                flash('Please fill all required fields.', 'error')
                return redirect(url_for('mock_waec.create_exam'))

            new_branch_id = branch_for_new(request.form.get('branch_id', type=int))
            if MockWAECExam.query.filter_by(session_id=session_id, exam_number=exam_number,
                                            branch_id=new_branch_id).first():
                flash(f'Mock WAEC #{exam_number} already exists for this session.', 'error')
                return redirect(url_for('mock_waec.create_exam'))

            try:
                exam_date = datetime.strptime(exam_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid date format.', 'error')
                return redirect(url_for('mock_waec.create_exam'))

            session_obj = db.session.get(AcademicSession, session_id)
            if not name:
                ordinals = {1: 'First', 2: 'Second', 3: 'Third', 4: 'Fourth'}
                name = f"{ordinals.get(exam_number, str(exam_number))} Mock WAEC {session_obj.name}"

            exam = MockWAECExam(name=name, exam_number=exam_number, session_id=session_id,
                                exam_date=exam_date, description=description, branch_id=new_branch_id)
            db.session.add(exam)
            db.session.commit()
            flash(f'{exam.display_name} created.', 'success')
            return redirect(url_for('mock_waec.view_exam', exam_id=exam.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating exam: {e}', 'error')

    existing = {str(s.id): [e.exam_number for e in MockWAECExam.query.filter_by(session_id=s.id).all()]
                for s in sessions}
    return render_template('mock_waec/create_exam.html',
        sessions=sessions, existing_exams=existing, exam=None)


@mock_waec_bp.route('/exam/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
@csrf_protect
def edit_exam(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    if request.method == 'POST':
        exam.name = (request.form.get('name') or exam.name).strip()
        d = request.form.get('exam_date')
        if d:
            try:
                exam.exam_date = datetime.strptime(d, '%Y-%m-%d').date()
            except ValueError:
                pass
        exam.description = (request.form.get('description') or '').strip()
        exam.is_completed = bool(request.form.get('is_completed'))
        db.session.commit()
        flash('Mock WAEC exam updated.', 'success')
        return redirect(url_for('mock_waec.view_exam', exam_id=exam.id))
    return render_template('mock_waec/create_exam.html', exam=exam,
        sessions=AcademicSession.query.order_by(AcademicSession.name.desc()).all(),
        existing_exams={})


@mock_waec_bp.route('/exam/<int:exam_id>/delete', methods=['POST'])
@admin_required
@csrf_protect
def delete_exam(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    session_id = exam.session_id
    affected = [sid for (sid,) in db.session.query(MockWAECResult.student_id)
                .filter_by(mock_exam_id=exam_id).distinct().all()]
    db.session.delete(exam)
    db.session.commit()
    for sid in affected:
        recompute_student_safe(sid)
    flash('Mock WAEC exam and its results deleted.', 'success')
    return redirect(url_for('mock_waec.index', session_id=session_id))


@mock_waec_bp.route('/exam/<int:exam_id>')
@login_required
def view_exam(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    stats = MockWAECAnalytics.get_exam_statistics(exam_id)

    # Per-student rows (subject grades collapsed) for the results table.
    rows = {}
    for r in MockWAECResult.query.filter_by(mock_exam_id=exam_id).join(Student).all():
        rows.setdefault(r.student_id, {'student': r.student, 'results': []})
        rows[r.student_id]['results'].append(r)
    students = []
    for sid, info in rows.items():
        summary = MockWAECAnalytics._summarise(info['results'])
        students.append({'student': info['student'],
                         'results': sorted(info['results'], key=lambda x: x.subject),
                         **summary})
    students.sort(key=lambda s: (s['credits'], s['average_score'] or 0), reverse=True)
    return render_template('mock_waec/view_exam.html', exam=exam, stats=stats, students=students)


# =============================================================================
# RESULT ENTRY — single student
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/results/add', methods=['GET', 'POST'])
@login_required
@csrf_protect
def add_result(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    students = get_sss3_students()

    if request.method == 'POST':
        student_id = request.form.get('student_id', type=int)
        if not student_id:
            flash('Please select a student.', 'error')
            return redirect(url_for('mock_waec.add_result', exam_id=exam_id))
        subjects = request.form.getlist('subject[]')
        scores = request.form.getlist('score[]')
        saved = 0
        for i, subject in enumerate(subjects):
            subject = (subject or '').strip()
            raw = scores[i] if i < len(scores) else ''
            if not subject or raw in (None, ''):
                continue
            try:
                score = max(0, min(100, int(raw)))
            except (TypeError, ValueError):
                continue
            _upsert_result(student_id, exam_id, subject, score)
            saved += 1
        db.session.commit()
        recompute_student_safe(student_id)
        flash(f'{saved} subject result(s) saved.', 'success')
        return redirect(url_for('mock_waec.view_exam', exam_id=exam_id))

    return render_template('mock_waec/add_result.html',
        exam=exam, students=students, subjects=WAEC_SUBJECTS)


# =============================================================================
# RESULT ENTRY — paste & preview bulk importer
# =============================================================================

def _match_student_index():
    """Build lookup maps (admission-no -> student, full-name -> student) over the
    SSS3 cohort, for resolving pasted rows to students."""
    by_admission, by_name = {}, {}
    for s in get_sss3_students():
        if s.student_id:
            by_admission[s.student_id.strip().upper()] = s
        by_name[s.full_name.strip().upper()] = s
    return by_admission, by_name


def _parse_paste(text):
    """Parse pasted CSV lines into preview rows.

    Each line: ``student, subject, score[, grade]`` where *student* is an
    admission number or full name. Grade is optional (auto-derived from score).
    Returns ``(rows, ok_count)`` — every row carries a status so the preview can
    show exactly what will (and won't) be imported.
    """
    by_admission, by_name = _match_student_index()
    rows, ok = [], 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        row = {'lineno': lineno, 'raw': line, 'status': 'error', 'message': '',
               'student': None, 'student_id': None, 'student_name': parts[0] if parts else '',
               'subject': '', 'score': None, 'grade': None}
        if len(parts) < 3:
            row['message'] = 'Need at least: student, subject, score'
            rows.append(row)
            continue

        ident, subject_raw, score_raw = parts[0], parts[1], parts[2]
        grade_raw = parts[3] if len(parts) >= 4 else ''

        # Resolve student.
        student = by_admission.get(ident.upper()) or by_name.get(ident.upper())
        if not student:
            row['message'] = f'No SSS3 student matches "{ident}"'
            rows.append(row)
            continue
        row['student'] = student
        row['student_id'] = student.id
        row['student_name'] = student.full_name

        # Canonicalise subject against the WAEC list (case-insensitive).
        subject = _CANON_SUBJECTS.get(subject_raw.upper(), subject_raw.strip().title())
        row['subject'] = subject
        if subject_raw.upper() not in _CANON_SUBJECTS:
            row['message'] = 'Unrecognised subject (will still be saved)'

        # Score.
        try:
            score = int(round(float(score_raw)))
        except (TypeError, ValueError):
            row['message'] = f'Invalid score "{score_raw}"'
            rows.append(row)
            continue
        if not 0 <= score <= 100:
            row['message'] = f'Score {score} out of range (0-100)'
            rows.append(row)
            continue
        row['score'] = score

        # Grade: honour a valid supplied grade, else derive.
        grade = grade_raw.upper() if grade_raw else ''
        row['grade'] = grade if grade in WAEC_GRADES else waec_grade_from_score(score)

        row['status'] = 'warning' if row['message'] else 'ok'
        ok += 1
        rows.append(row)
    return rows, ok


@mock_waec_bp.route('/exam/<int:exam_id>/results/paste', methods=['GET', 'POST'])
@login_required
@csrf_protect
def paste_entry(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    text = request.form.get('data', '')
    action = request.form.get('action')

    if request.method == 'POST' and action == 'confirm':
        rows, _ = _parse_paste(text)          # re-parse: never trust a serialized blob
        touched, saved = set(), 0
        for row in rows:
            if row['status'] in ('ok', 'warning') and row['student_id']:
                _upsert_result(row['student_id'], exam_id, row['subject'],
                               row['score'], row['grade'])
                touched.add(row['student_id'])
                saved += 1
        db.session.commit()
        for sid in touched:
            recompute_student_safe(sid)
        flash(f'Imported {saved} result(s) for {len(touched)} student(s).', 'success')
        return redirect(url_for('mock_waec.view_exam', exam_id=exam_id))

    preview = None
    if request.method == 'POST' and action == 'preview':
        rows, ok = _parse_paste(text)
        preview = {'rows': rows, 'ok': ok, 'errors': sum(1 for r in rows if r['status'] == 'error')}

    return render_template('mock_waec/paste_entry.html', exam=exam, text=text, preview=preview)


def _upsert_result(student_id, exam_id, subject, score, grade=None):
    """Insert or update one subject result (no commit)."""
    row = MockWAECResult.query.filter_by(
        student_id=student_id, mock_exam_id=exam_id, subject=subject).first()
    if row is None:
        row = MockWAECResult(student_id=student_id, mock_exam_id=exam_id, subject=subject)
        db.session.add(row)
    row.apply_score(score, grade)
    return row


@mock_waec_bp.route('/result/<int:result_id>/delete', methods=['POST'])
@login_required
@csrf_protect
def delete_result(result_id):
    result = db.get_or_404(MockWAECResult, result_id)
    exam = db.session.get(MockWAECExam, result.mock_exam_id)
    require_branch_access(exam.branch_id)
    exam_id, student_id = result.mock_exam_id, result.student_id
    db.session.delete(result)
    db.session.commit()
    recompute_student_safe(student_id)
    flash('Result deleted.', 'success')
    return redirect(url_for('mock_waec.view_exam', exam_id=exam_id))


# =============================================================================
# STUDENT PROGRESSION
# =============================================================================

@mock_waec_bp.route('/student/<int:student_id>')
@login_required
def student_progress(student_id):
    student = db.get_or_404(Student, student_id)
    require_branch_access(student.branch_id)
    progress = MockWAECAnalytics.get_student_progress(student_id)
    prediction = MockWAECAnalytics.predict_waec(student_id)
    return render_template('mock_waec/student_progress.html',
        student=student, progress=progress, prediction=prediction)


# =============================================================================
# EXPORT
# =============================================================================

@mock_waec_bp.route('/exam/<int:exam_id>/export')
@login_required
def export_results(exam_id):
    exam = db.get_or_404(MockWAECExam, exam_id)
    require_branch_access(exam.branch_id)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Mock WAEC'
    ws.append(['Student', 'Admission No', 'Subject', 'Score', 'Grade'])
    results = (MockWAECResult.query.filter_by(mock_exam_id=exam_id)
               .join(Student).order_by(Student.surname, MockWAECResult.subject).all())
    for r in results:
        ws.append([r.student.full_name, r.student.student_id, r.subject, r.score, r.grade])
    return xlsx_response(wb, f'mock_waec_{exam.exam_number}_{exam.session.name.replace("/", "-")}.xlsx')
