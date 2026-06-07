"""
CBT / Online Tests.

Two surfaces:
  * Admin/teacher (``cbt_bp`` at /cbt): build exams + questions, set the per-exam
    access password, publish, view results, and manage student portal passwords.
  * Student portal (``cbt_portal_bp`` at /exam): a separate login (student ID +
    portal password); shows exams active for the student's class *today*; each
    exam is gated by its own access password; answers are auto-graded.
"""
from datetime import datetime, date, timedelta
from functools import wraps
import csv
import io
import random
import secrets

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, jsonify, Response)
from sqlalchemy import func

from models import (db, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer,
                    Subject, SchoolClass, ClassArm, Term, Student,
                    StudentEnrollment, ClassArmAssignment, SchoolSettings)
from utils.access_control import login_required, admin_required, is_admin
from utils import timeutil

cbt_bp = Blueprint('cbt', __name__, url_prefix='/cbt')
cbt_portal_bp = Blueprint('cbt_portal', __name__, url_prefix='/exam')

PORTAL_KEY = 'cbt_student_id'
MAX_VIOLATIONS = 3   # leave-page events allowed before the test auto-submits


def _d(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default


def _active_term():
    return Term.query.filter_by(is_active=True).first()


def _student_placement(student_id, term):
    if not term:
        return None, None
    enr = (StudentEnrollment.query
           .join(ClassArmAssignment,
                 StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
           .filter(StudentEnrollment.student_id == student_id,
                   StudentEnrollment.is_active == True,
                   ClassArmAssignment.term_id == term.id).first())
    if not enr:
        return None, None
    asg = enr.class_arm_assignment
    return asg.class_id, asg.arm_id


# ============================================================================
# ADMIN — DASHBOARD + EXAM MANAGEMENT
# ============================================================================

@cbt_bp.route('/')
@login_required
def dashboard():
    exams = CBTExam.query.order_by(CBTExam.exam_date.desc(), CBTExam.id.desc()).all()
    total = len(exams)
    published = sum(1 for e in exams if e.is_published)
    today_count = sum(1 for e in exams if e.exam_date == timeutil.today() and e.is_published)
    attempts = CBTAttempt.query.filter_by(status='Submitted').count()
    return render_template('cbt/dashboard.html', exams=exams, total=total,
        published=published, today_count=today_count, attempts=attempts)


def _exam_choices():
    return {
        'subjects': Subject.query.filter_by(is_active=True).order_by(Subject.name).all(),
        'classes': SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all(),
        'arms': ClassArm.query.filter_by(is_active=True).order_by(ClassArm.name).all(),
        'terms': Term.query.order_by(Term.id.desc()).all(),
    }


def _read_exam(e):
    e.title = (request.form.get('title') or '').strip()
    e.subject_id = request.form.get('subject_id', type=int) or None
    e.class_id = request.form.get('class_id', type=int) or None
    e.arm_id = request.form.get('arm_id', type=int) or None
    e.term_id = request.form.get('term_id', type=int) or None
    e.exam_date = _d(request.form.get('exam_date')) or timeutil.today()
    e.start_time = (request.form.get('start_time') or '').strip() or None
    e.end_time = (request.form.get('end_time') or '').strip() or None
    e.duration_minutes = request.form.get('duration_minutes', type=int) or 30
    e.max_score = request.form.get('max_score', type=float)
    e.access_password = (request.form.get('access_password') or '').strip()
    e.instructions = (request.form.get('instructions') or '').strip() or None
    e.shuffle = bool(request.form.get('shuffle'))


@cbt_bp.route('/exams/add', methods=['GET', 'POST'])
@login_required
def add_exam():
    if request.method == 'POST':
        if not (request.form.get('title') and request.form.get('access_password')):
            flash('Title and an access password are required.', 'error')
            return redirect(url_for('cbt.add_exam'))
        from flask import session as _s
        e = CBTExam(created_by=_s.get('username') or 'Admin')
        _read_exam(e)
        db.session.add(e)
        db.session.commit()
        flash('Exam created — now add questions.', 'success')
        return redirect(url_for('cbt.exam_detail', exam_id=e.id))
    active = _active_term()
    return render_template('cbt/exam_form.html', exam=None, active_term=active, **_exam_choices())


@cbt_bp.route('/exams/<int:exam_id>')
@login_required
def exam_detail(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    questions = e.questions.order_by(CBTQuestion.order, CBTQuestion.id).all()
    return render_template('cbt/exam_detail.html', e=e, questions=questions)


@cbt_bp.route('/exams/<int:exam_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_exam(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    if request.method == 'POST':
        _read_exam(e)
        db.session.commit()
        flash('Exam updated.', 'success')
        return redirect(url_for('cbt.exam_detail', exam_id=e.id))
    return render_template('cbt/exam_form.html', exam=e, active_term=_active_term(), **_exam_choices())


@cbt_bp.route('/exams/<int:exam_id>/publish', methods=['POST'])
@login_required
def toggle_publish(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    if not e.is_published and e.question_count == 0:
        flash('Add at least one question before publishing.', 'error')
        return redirect(url_for('cbt.exam_detail', exam_id=e.id))
    e.is_published = not e.is_published
    db.session.commit()
    flash('Exam published.' if e.is_published else 'Exam unpublished.', 'success')
    return redirect(url_for('cbt.exam_detail', exam_id=e.id))


@cbt_bp.route('/exams/<int:exam_id>/delete', methods=['POST'])
@admin_required
def delete_exam(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    db.session.delete(e)
    db.session.commit()
    flash('Exam deleted.', 'success')
    return redirect(url_for('cbt.dashboard'))


@cbt_bp.route('/exams/<int:exam_id>/questions/add', methods=['POST'])
@login_required
def add_question(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    text = (request.form.get('question_text') or '').strip()
    correct = (request.form.get('correct_option') or '').strip().upper()
    if not text or correct not in ('A', 'B', 'C', 'D'):
        flash('Question text and a correct option (A–D) are required.', 'error')
        return redirect(url_for('cbt.exam_detail', exam_id=exam_id))
    nextord = (db.session.query(func.coalesce(func.max(CBTQuestion.order), 0))
               .filter(CBTQuestion.exam_id == exam_id).scalar()) + 1
    db.session.add(CBTQuestion(
        exam_id=exam_id, question_text=text,
        option_a=(request.form.get('option_a') or '').strip(),
        option_b=(request.form.get('option_b') or '').strip(),
        option_c=(request.form.get('option_c') or '').strip(),
        option_d=(request.form.get('option_d') or '').strip(),
        correct_option=correct, marks=request.form.get('marks', type=float) or 1,
        order=nextord))
    db.session.commit()
    flash('Question added.', 'success')
    return redirect(url_for('cbt.exam_detail', exam_id=exam_id))


@cbt_bp.route('/questions/<int:question_id>/delete', methods=['POST'])
@login_required
def delete_question(question_id):
    q = CBTQuestion.query.get_or_404(question_id)
    exam_id = q.exam_id
    db.session.delete(q)
    db.session.commit()
    flash('Question removed.', 'success')
    return redirect(url_for('cbt.exam_detail', exam_id=exam_id))


@cbt_bp.route('/exams/<int:exam_id>/results')
@login_required
def results(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    attempts = (e.attempts.join(Student).order_by(Student.surname, Student.first_name).all())
    submitted = [a for a in attempts if a.status == 'Submitted']
    avg = round(sum(a.score for a in submitted) / len(submitted), 1) if submitted else 0

    # Per-question analytics: % of submitted attempts that got each question right.
    questions = e.questions.order_by(CBTQuestion.order, CBTQuestion.id).all()
    sub_ids = [a.id for a in submitted]
    analysis = []
    for q in questions:
        correct = 0
        if sub_ids:
            correct = CBTAnswer.query.filter(
                CBTAnswer.question_id == q.id,
                CBTAnswer.attempt_id.in_(sub_ids),
                CBTAnswer.is_correct == True).count()
        pct = round(correct / len(submitted) * 100, 1) if submitted else 0
        analysis.append({'q': q, 'correct': correct, 'pct': pct})
    return render_template('cbt/results.html', e=e, attempts=attempts, avg=avg,
                           analysis=analysis, submitted_count=len(submitted))


def _review_rows(exam, attempt):
    """Per-question review: each question with the student's pick + correctness."""
    ans = {a.question_id: a for a in attempt.answers}
    rows = []
    for q in exam.questions.order_by(CBTQuestion.order, CBTQuestion.id).all():
        a = ans.get(q.id)
        rows.append({'q': q,
                     'selected': a.selected_option if a else None,
                     'is_correct': bool(a and a.is_correct)})
    return rows


@cbt_bp.route('/attempts/<int:attempt_id>/review')
@login_required
def attempt_review(attempt_id):
    attempt = CBTAttempt.query.get_or_404(attempt_id)
    rows = _review_rows(attempt.exam, attempt)
    return render_template('cbt/attempt_review.html', attempt=attempt,
                           exam=attempt.exam, rows=rows)



def _exam_sheet(ws, exam):
    """Write one exam's results (alphabetical by name) into an openpyxl sheet."""
    from openpyxl.styles import Font, PatternFill, Alignment
    head_fill = PatternFill(start_color='0d6a4e', end_color='0d6a4e', fill_type='solid')
    head_font = Font(bold=True, color='FFFFFF')
    title = f'{exam.subject.name if exam.subject else "Exam"} — {exam.title}'
    ws.merge_cells('A1:E1')
    ws['A1'] = title
    ws['A1'].font = Font(bold=True, size=13)
    ws.merge_cells('A2:E2')
    ws['A2'] = (f'{exam.school_class.name if exam.school_class else ""} · '
                f'{exam.exam_date.strftime("%d %b %Y") if exam.exam_date else ""} · '
                f'Total {exam.total_marks} marks')
    ws['A2'].font = Font(italic=True, color='666666')
    headers = ['S/N', 'Student ID', 'Name', 'Raw', f'Score (/{exam.total_marks:g})', '%']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=h)
        cell.fill = head_fill
        cell.font = head_font
    # Submitted attempts, alphabetical by surname then first name.
    attempts = (exam.attempts.filter_by(status='Submitted')
                .join(Student).order_by(Student.surname, Student.first_name).all())
    r = 5
    for i, a in enumerate(attempts, 1):
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=a.student.student_id if a.student else '')
        ws.cell(row=r, column=3, value=a.student.full_name if a.student else '')
        ws.cell(row=r, column=4, value=f'{a.raw_score:g}/{a.raw_total:g}' if a.raw_total else a.score)
        ws.cell(row=r, column=5, value=a.score)
        ws.cell(row=r, column=6, value=a.percentage)
        r += 1
    widths = [6, 16, 32, 12, 12, 8]
    for i, wd in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + i)].width = wd
    return len(attempts)


def _safe_sheet_title(text):
    bad = set('[]:*?/\\')
    return ''.join(c for c in text if c not in bad)[:31] or 'Sheet'


@cbt_bp.route('/exams/<int:exam_id>/results/export')
@login_required
def results_export(exam_id):
    from openpyxl import Workbook
    e = CBTExam.query.get_or_404(exam_id)
    wb = Workbook()
    ws = wb.active
    ws.title = _safe_sheet_title(e.subject.name if e.subject else 'Results')
    _exam_sheet(ws, e)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    fname = _safe_sheet_title(f'{e.subject.name if e.subject else "exam"}_{e.title}') + '.xlsx'
    return Response(output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={fname}'})


@cbt_bp.route('/results/export-all')
@login_required
def results_export_all():
    """Workbook with one alphabetical results sheet per exam (grouped by subject)."""
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    exams = (CBTExam.query.join(Subject, isouter=True)
             .order_by(Subject.name, CBTExam.exam_date).all())
    exams = [e for e in exams if e.attempts.filter_by(status='Submitted').count()]
    if not exams:
        ws = wb.create_sheet('No results')
        ws['A1'] = 'No submitted exam results yet.'
    seen = {}
    for e in exams:
        base = _safe_sheet_title(f'{e.subject.name if e.subject else "Exam"}-{e.title}')
        title, n = base, seen.get(base, 0)
        if n:
            title = _safe_sheet_title(f'{base} {n+1}')
        seen[base] = n + 1
        _exam_sheet(wb.create_sheet(title), e)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return Response(output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=cbt_all_results.xlsx'})


# ============================================================================
# ADMIN — STUDENT PORTAL PASSWORDS
# ============================================================================

@cbt_bp.route('/passwords', methods=['GET', 'POST'])
@login_required
def passwords():
    term = _active_term()
    class_id = request.values.get('class_id', type=int)
    arm_id = request.values.get('arm_id', type=int)
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()
    arms = ClassArm.query.filter_by(is_active=True).order_by(ClassArm.name).all()

    if request.method == 'POST':
        action = request.form.get('action')
        ids = request.form.getlist('student_id', type=int)
        students = Student.query.filter(Student.id.in_(ids or [-1])).all()
        if action == 'set_individual':
            sid = request.form.get('one_student_id', type=int)
            pw = (request.form.get('one_password') or '').strip()
            s = Student.query.get(sid) if sid else None
            if s and pw:
                s.set_portal_password(pw)
                db.session.commit()
                flash(f'Password set for {s.full_name}.', 'success')
        elif action == 'set_same' and students:
            pw = (request.form.get('bulk_password') or '').strip()
            if pw:
                for s in students:
                    s.set_portal_password(pw)
                db.session.commit()
                flash(f'Set the same password for {len(students)} student(s).', 'success')
        elif action == 'generate' and students:
            generated = []
            for s in students:
                pw = secrets.token_hex(3)   # 6-char one-time password
                s.set_portal_password(pw)
                generated.append((s, pw))
            db.session.commit()
            return render_template('cbt/passwords.html', classes=classes, arms=arms, term=term,
                class_id=class_id, arm_id=arm_id,
                students=_password_roster(class_id, arm_id, term), generated=generated)
        return redirect(url_for('cbt.passwords', class_id=class_id or '', arm_id=arm_id or ''))

    return render_template('cbt/passwords.html', classes=classes, arms=arms, term=term,
        class_id=class_id, arm_id=arm_id,
        students=_password_roster(class_id, arm_id, term), generated=None)


def _password_roster(class_id, arm_id, term):
    if class_id and term:
        q = (StudentEnrollment.query
             .join(ClassArmAssignment,
                   StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
             .filter(StudentEnrollment.is_active == True,
                     ClassArmAssignment.term_id == term.id,
                     ClassArmAssignment.class_id == class_id))
        if arm_id:
            q = q.filter(ClassArmAssignment.arm_id == arm_id)
        ids = [e.student_id for e in q.all()]
        return Student.query.filter(Student.id.in_(ids or [-1])).order_by(Student.surname, Student.first_name).all()
    return Student.query.filter_by(is_active=True).order_by(Student.surname).limit(300).all()


def _roster_label(class_id, arm_id, classes, arms):
    cls = next((c for c in classes if c.id == class_id), None)
    arm = next((a for a in arms if a.id == arm_id), None)
    return ' '.join(p for p in [cls.name if cls else 'All students', arm.name if arm else ''] if p)


@cbt_bp.route('/passwords/export')
@login_required
def passwords_export():
    """Export portal passwords for a class arm as Excel / Word / PDF."""
    term = _active_term()
    class_id = request.args.get('class_id', type=int)
    arm_id = request.args.get('arm_id', type=int)
    fmt = (request.args.get('format') or 'xlsx').lower()
    classes = SchoolClass.query.all()
    arms = ClassArm.query.all()
    label = _roster_label(class_id, arm_id, classes, arms)
    students = _password_roster(class_id, arm_id, term)
    rows = [(i + 1, s.student_id, s.full_name, s.portal_password_plain or '—')
            for i, s in enumerate(students)]
    school = SchoolSettings.get('school_name', 'School')
    safe = ''.join(c for c in label if c.isalnum() or c in ' -_').strip().replace(' ', '_') or 'students'

    if fmt == 'docx':
        return _passwords_docx(school, label, rows, safe)
    if fmt == 'pdf':
        return _passwords_pdf(school, label, rows, safe)
    return _passwords_xlsx(school, label, rows, safe)


def _passwords_xlsx(school, label, rows, safe):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = 'Passwords'
    ws.merge_cells('A1:D1')
    ws['A1'] = f'{school} — Test Portal Passwords ({label})'
    ws['A1'].font = Font(bold=True, size=13)
    fill = PatternFill(start_color='0d6a4e', end_color='0d6a4e', fill_type='solid')
    for col, h in enumerate(['S/N', 'Student ID', 'Name', 'Password'], 1):
        c = ws.cell(row=3, column=col, value=h)
        c.fill = fill
        c.font = Font(bold=True, color='FFFFFF')
    for r, row in enumerate(rows, 4):
        for col, val in enumerate(row, 1):
            ws.cell(row=r, column=col, value=val)
    for i, w in enumerate([6, 18, 34, 16], 1):
        ws.column_dimensions[chr(64 + i)].width = w
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return Response(out.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename=passwords_{safe}.xlsx'})


def _passwords_docx(school, label, rows, safe):
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    doc.add_heading(f'{school}', level=1)
    doc.add_heading(f'Test Portal Passwords — {label}', level=2)
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Light Grid Accent 1'
    hdr = table.rows[0].cells
    for i, h in enumerate(['S/N', 'Student ID', 'Name', 'Password']):
        hdr[i].text = h
        hdr[i].paragraphs[0].runs[0].font.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return Response(out.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename=passwords_{safe}.docx'})


def _passwords_pdf(school, label, rows, safe):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    elems = [Paragraph(f'<b>{school}</b>', styles['Title']),
             Paragraph(f'Test Portal Passwords — {label}', styles['Heading2']),
             Spacer(1, 6 * mm)]
    data = [['S/N', 'Student ID', 'Name', 'Password']] + [[str(c) for c in row] for row in rows]
    t = Table(data, colWidths=[14 * mm, 32 * mm, 78 * mm, 36 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d6a4e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f6f4')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (3, 1), (3, -1), 'Courier-Bold'),
    ]))
    elems.append(t)
    doc.build(elems)
    out.seek(0)
    return Response(out.getvalue(), mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename=passwords_{safe}.pdf'})


# ============================================================================
# STUDENT PORTAL
# ============================================================================

def cbt_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get(PORTAL_KEY):
            return redirect(url_for('cbt_portal.login'))
        return f(*args, **kwargs)
    return wrapper


def _current_student():
    sid = session.get(PORTAL_KEY)
    return Student.query.get(sid) if sid else None


@cbt_portal_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get(PORTAL_KEY):
        return redirect(url_for('cbt_portal.home'))
    if request.method == 'POST':
        student_id = (request.form.get('student_id') or '').strip()
        password = request.form.get('password') or ''
        student = Student.query.filter_by(student_id=student_id, is_active=True).first()
        if student and student.check_portal_password(password):
            session[PORTAL_KEY] = student.id
            return redirect(url_for('cbt_portal.home'))
        flash('Invalid student ID or password.', 'error')
    return render_template('cbt/portal_login.html')


@cbt_portal_bp.route('/logout')
def logout():
    session.pop(PORTAL_KEY, None)
    return redirect(url_for('cbt_portal.login'))


@cbt_portal_bp.route('/')
@cbt_login_required
def home():
    student = _current_student()
    if not student:
        session.pop(PORTAL_KEY, None)
        return redirect(url_for('cbt_portal.login'))
    term = _active_term()
    class_id, arm_id = _student_placement(student.id, term)
    exams = []
    if class_id:
        q = CBTExam.query.filter(CBTExam.is_published == True,
                                 CBTExam.exam_date == timeutil.today(),
                                 CBTExam.class_id == class_id)
        q = q.filter((CBTExam.arm_id == None) | (CBTExam.arm_id == arm_id))
        exams = q.order_by(CBTExam.start_time, CBTExam.title).all()
    # attach this student's attempt status + availability window
    rows = []
    for e in exams:
        att = CBTAttempt.query.filter_by(exam_id=e.id, student_id=student.id).first()
        state, msg = e.access_state()
        rows.append({'exam': e, 'attempt': att, 'state': state, 'msg': msg})
    return render_template('cbt/portal_home.html', student=student, rows=rows,
                           has_class=bool(class_id))


def _student_can_access(student, exam):
    """The exam must be for the student's current class/arm."""
    class_id, arm_id = _student_placement(student.id, _active_term())
    if not class_id or exam.class_id != class_id:
        return False
    if exam.arm_id and exam.arm_id != arm_id:
        return False
    return True


@cbt_portal_bp.route('/<int:exam_id>/start', methods=['GET', 'POST'])
@cbt_login_required
def start(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    if not exam.is_published or not _student_can_access(student, exam):
        flash('This exam is not available for your class.', 'error')
        return redirect(url_for('cbt_portal.home'))
    existing = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if existing and existing.status == 'Submitted':
        return redirect(url_for('cbt_portal.result', exam_id=exam.id))
    state, msg = exam.access_state()
    if state != 'open' and not (existing and existing.status == 'In progress'):
        flash(f'This test is not open right now — {msg}.', 'error')
        return redirect(url_for('cbt_portal.home'))
    if request.method == 'POST':
        pw = (request.form.get('access_password') or '').strip()
        if pw != (exam.access_password or ''):
            flash('Incorrect exam password.', 'error')
            return render_template('cbt/portal_start.html', exam=exam, student=student)
        if not existing:
            existing = CBTAttempt(exam_id=exam.id, student_id=student.id,
                                  started_at=timeutil.now(), total=exam.total_marks)
            db.session.add(existing)
            db.session.commit()
        return redirect(url_for('cbt_portal.take', exam_id=exam.id))
    return render_template('cbt/portal_start.html', exam=exam, student=student)


def _deadline(attempt, exam):
    return attempt.started_at + timedelta(minutes=exam.duration_minutes or 30)


def _finalize(attempt, exam):
    """Grade from saved answers, apply the exam's scaling, mark Submitted."""
    raw_score = 0.0
    raw_total = exam.raw_total
    saved = {a.question_id: a for a in attempt.answers}
    for q in exam.questions.all():
        ans = saved.get(q.id)
        correct = bool(ans and ans.selected_option == q.correct_option)
        if ans:
            ans.is_correct = correct
        if correct:
            raw_score += q.marks or 0
    attempt.raw_score = raw_score
    attempt.raw_total = raw_total
    attempt.total = exam.total_marks
    attempt.score = exam.scale(raw_score)
    attempt.status = 'Submitted'
    attempt.submitted_at = timeutil.now()
    db.session.commit()


@cbt_portal_bp.route('/<int:exam_id>/take')
@cbt_login_required
def take(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    if not _student_can_access(student, exam):
        flash('This exam is not available for your class.', 'error')
        return redirect(url_for('cbt_portal.home'))
    attempt = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if not attempt:
        return redirect(url_for('cbt_portal.start', exam_id=exam.id))
    if attempt.status == 'Submitted':
        return redirect(url_for('cbt_portal.result', exam_id=exam.id))
    # Timer already expired while away -> auto-submit from saved answers.
    remaining = int((_deadline(attempt, exam) - timeutil.now()).total_seconds())
    if remaining <= 0:
        _finalize(attempt, exam)
        flash('Time was up — your test was submitted automatically.', 'info')
        return redirect(url_for('cbt_portal.result', exam_id=exam.id))
    questions = exam.questions.order_by(CBTQuestion.order, CBTQuestion.id).all()
    if exam.shuffle:
        random.Random(attempt.id).shuffle(questions)   # stable per attempt
    # Build per-question option lists, shuffled per attempt (each option keeps
    # its original letter, so two students rarely see "the answer is C").
    qview = []
    for q in questions:
        opts = [(l, t) for l, t in q.options if t]
        if exam.shuffle:
            random.Random(attempt.id * 1009 + q.id).shuffle(opts)
        qview.append({'q': q, 'options': opts})
    saved = {a.question_id: a.selected_option for a in attempt.answers}
    return render_template('cbt/portal_take.html', exam=exam, student=student,
        qview=qview, attempt=attempt, remaining=remaining, saved=saved,
        max_violations=MAX_VIOLATIONS)


@cbt_portal_bp.route('/<int:exam_id>/flag', methods=['POST'])
@cbt_login_required
def flag(exam_id):
    """Record an anti-malpractice event (student left the exam tab/window)."""
    student = _current_student()
    attempt = CBTAttempt.query.filter_by(exam_id=exam_id, student_id=student.id).first()
    if not attempt or attempt.status != 'In progress':
        return jsonify({'ok': False}), 400
    attempt.violations = (attempt.violations or 0) + 1
    db.session.commit()
    over = attempt.violations >= MAX_VIOLATIONS
    if over:
        _finalize(attempt, CBTExam.query.get(exam_id))   # forced submit
    return jsonify({'ok': True, 'violations': attempt.violations,
                    'max': MAX_VIOLATIONS, 'autosubmit': over})


@cbt_portal_bp.route('/<int:exam_id>/answer', methods=['POST'])
@cbt_login_required
def answer(exam_id):
    """Autosave a single answer so a refresh / disconnect never loses progress."""
    student = _current_student()
    attempt = CBTAttempt.query.filter_by(exam_id=exam_id, student_id=student.id).first()
    if not attempt or attempt.status == 'Submitted':
        return jsonify({'ok': False}), 400
    qid = request.form.get('question_id', type=int)
    sel = (request.form.get('option') or '').strip().upper() or None
    q = CBTQuestion.query.filter_by(id=qid, exam_id=exam_id).first()
    if not q:
        return jsonify({'ok': False}), 400
    ans = CBTAnswer.query.filter_by(attempt_id=attempt.id, question_id=qid).first()
    if not ans:
        ans = CBTAnswer(attempt_id=attempt.id, question_id=qid)
        db.session.add(ans)
    ans.selected_option = sel
    ans.is_correct = (sel == q.correct_option)
    db.session.commit()
    return jsonify({'ok': True})


@cbt_portal_bp.route('/<int:exam_id>/submit', methods=['POST'])
@cbt_login_required
def submit(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    attempt = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if not attempt:
        return redirect(url_for('cbt_portal.home'))
    if attempt.status == 'Submitted':
        return redirect(url_for('cbt_portal.result', exam_id=exam.id))
    # Persist any answers posted with the final submit (covers JS-off / last picks).
    for q in exam.questions.all():
        if f'q_{q.id}' not in request.form:
            continue
        sel = (request.form.get(f'q_{q.id}') or '').strip().upper() or None
        ans = CBTAnswer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
        if not ans:
            ans = CBTAnswer(attempt_id=attempt.id, question_id=q.id)
            db.session.add(ans)
        ans.selected_option = sel
    db.session.flush()
    _finalize(attempt, exam)
    return redirect(url_for('cbt_portal.result', exam_id=exam.id))


@cbt_portal_bp.route('/<int:exam_id>/result')
@cbt_login_required
def result(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    attempt = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if not attempt or attempt.status != 'Submitted':
        return redirect(url_for('cbt_portal.home'))
    rows = _review_rows(exam, attempt)
    return render_template('cbt/portal_result.html', exam=exam, student=student,
                           attempt=attempt, rows=rows)
