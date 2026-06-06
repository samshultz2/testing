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

cbt_bp = Blueprint('cbt', __name__, url_prefix='/cbt')
cbt_portal_bp = Blueprint('cbt_portal', __name__, url_prefix='/exam')

PORTAL_KEY = 'cbt_student_id'


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
    today_count = sum(1 for e in exams if e.exam_date == date.today() and e.is_published)
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
    e.exam_date = _d(request.form.get('exam_date')) or date.today()
    e.duration_minutes = request.form.get('duration_minutes', type=int) or 30
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
    return render_template('cbt/results.html', e=e, attempts=attempts, avg=avg)


@cbt_bp.route('/exams/<int:exam_id>/results/export')
@login_required
def results_export(exam_id):
    e = CBTExam.query.get_or_404(exam_id)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Student', 'Student ID', 'Score', 'Total', 'Percentage', 'Status', 'Submitted'])
    for a in e.attempts.join(Student).order_by(Student.surname).all():
        w.writerow([a.student.full_name if a.student else '', a.student.student_id if a.student else '',
                    a.score, a.total, a.percentage, a.status,
                    a.submitted_at.strftime('%Y-%m-%d %H:%M') if a.submitted_at else ''])
    return Response(out.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=cbt_results_{exam_id}.csv'})


# ============================================================================
# ADMIN — STUDENT PORTAL PASSWORDS
# ============================================================================

@cbt_bp.route('/passwords', methods=['GET', 'POST'])
@login_required
def passwords():
    term = _active_term()
    class_id = request.values.get('class_id', type=int)
    classes = SchoolClass.query.filter_by(is_active=True).order_by(SchoolClass.level).all()

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
            # show the generated passwords once
            return render_template('cbt/passwords.html', classes=classes, term=term,
                class_id=class_id, students=_password_roster(class_id, term),
                generated=generated)
        return redirect(url_for('cbt.passwords', class_id=class_id or ''))

    return render_template('cbt/passwords.html', classes=classes, term=term,
        class_id=class_id, students=_password_roster(class_id, term), generated=None)


def _password_roster(class_id, term):
    if class_id and term:
        ids = [e.student_id for e in (StudentEnrollment.query
               .join(ClassArmAssignment,
                     StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
               .filter(StudentEnrollment.is_active == True,
                       ClassArmAssignment.term_id == term.id,
                       ClassArmAssignment.class_id == class_id).all())]
        return Student.query.filter(Student.id.in_(ids or [-1])).order_by(Student.surname).all()
    return Student.query.filter_by(is_active=True).order_by(Student.surname).limit(300).all()


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
                                 CBTExam.exam_date == date.today(),
                                 CBTExam.class_id == class_id)
        q = q.filter((CBTExam.arm_id == None) | (CBTExam.arm_id == arm_id))
        exams = q.order_by(CBTExam.title).all()
    # attach this student's attempt status
    rows = []
    for e in exams:
        att = CBTAttempt.query.filter_by(exam_id=e.id, student_id=student.id).first()
        rows.append({'exam': e, 'attempt': att})
    return render_template('cbt/portal_home.html', student=student, rows=rows,
                           has_class=bool(class_id))


@cbt_portal_bp.route('/<int:exam_id>/start', methods=['GET', 'POST'])
@cbt_login_required
def start(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    if not (exam.is_published and exam.exam_date == date.today()):
        flash('This exam is not available.', 'error')
        return redirect(url_for('cbt_portal.home'))
    existing = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if existing and existing.status == 'Submitted':
        return redirect(url_for('cbt_portal.result', exam_id=exam.id))
    if request.method == 'POST':
        pw = (request.form.get('access_password') or '').strip()
        if pw != (exam.access_password or ''):
            flash('Incorrect exam password.', 'error')
            return render_template('cbt/portal_start.html', exam=exam, student=student)
        if not existing:
            existing = CBTAttempt(exam_id=exam.id, student_id=student.id,
                                  started_at=datetime.now(), total=exam.total_marks)
            db.session.add(existing)
            db.session.commit()
        return redirect(url_for('cbt_portal.take', exam_id=exam.id))
    return render_template('cbt/portal_start.html', exam=exam, student=student)


@cbt_portal_bp.route('/<int:exam_id>/take')
@cbt_login_required
def take(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    attempt = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if not attempt:
        return redirect(url_for('cbt_portal.start', exam_id=exam.id))
    if attempt.status == 'Submitted':
        return redirect(url_for('cbt_portal.result', exam_id=exam.id))
    questions = exam.questions.order_by(CBTQuestion.order, CBTQuestion.id).all()
    if exam.shuffle:
        random.Random(attempt.id).shuffle(questions)   # stable per attempt
    deadline = attempt.started_at + timedelta(minutes=exam.duration_minutes or 30)
    remaining = int((deadline - datetime.now()).total_seconds())
    return render_template('cbt/portal_take.html', exam=exam, student=student,
        questions=questions, attempt=attempt, remaining=max(remaining, 0))


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

    score = 0.0
    total = 0.0
    for q in exam.questions.all():
        total += q.marks or 0
        sel = (request.form.get(f'q_{q.id}') or '').strip().upper() or None
        correct = sel == q.correct_option
        if correct:
            score += q.marks or 0
        ans = CBTAnswer.query.filter_by(attempt_id=attempt.id, question_id=q.id).first()
        if not ans:
            ans = CBTAnswer(attempt_id=attempt.id, question_id=q.id)
            db.session.add(ans)
        ans.selected_option = sel
        ans.is_correct = correct
    attempt.score = score
    attempt.total = total
    attempt.status = 'Submitted'
    attempt.submitted_at = datetime.now()
    db.session.commit()
    return redirect(url_for('cbt_portal.result', exam_id=exam.id))


@cbt_portal_bp.route('/<int:exam_id>/result')
@cbt_login_required
def result(exam_id):
    student = _current_student()
    exam = CBTExam.query.get_or_404(exam_id)
    attempt = CBTAttempt.query.filter_by(exam_id=exam.id, student_id=student.id).first()
    if not attempt or attempt.status != 'Submitted':
        return redirect(url_for('cbt_portal.home'))
    return render_template('cbt/portal_result.html', exam=exam, student=student, attempt=attempt)
