"""Parent portal — parents sign in with their child's Student ID + portal
password to view results, attendance and fee balance (read-only)."""
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import Student, Term, Week, Announcement
from utils.finance import student_bill
from utils.report_card import build_report_card, _attendance_pct
from utils.helpers import get_active_term

parent_bp = Blueprint('parent', __name__, url_prefix='/parent')
PKEY = 'parent_student_id'


def parent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get(PKEY):
            return redirect(url_for('parent.login'))
        return f(*args, **kwargs)
    return wrapper


def _current_student():
    sid = session.get(PKEY)
    return Student.query.get(sid) if sid else None


@parent_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get(PKEY):
        return redirect(url_for('parent.home'))
    if request.method == 'POST':
        sid = (request.form.get('student_id') or '').strip()
        pw = request.form.get('password') or ''
        student = Student.query.filter_by(student_id=sid).first()
        if student and student.is_active and student.check_portal_password(pw):
            session[PKEY] = student.id
            session.permanent = True
            return redirect(url_for('parent.home'))
        flash('Invalid Student ID or password.', 'error')
        return redirect(url_for('parent.login'))
    return render_template('parent/login.html')


@parent_bp.route('/logout')
def logout():
    session.pop(PKEY, None)
    flash('You have been signed out.', 'info')
    return redirect(url_for('parent.login'))


@parent_bp.route('/')
@parent_required
def home():
    student = _current_student()
    if not student:
        session.pop(PKEY, None)
        return redirect(url_for('parent.login'))

    term_id = request.args.get('term_id', type=int)
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()

    bill = student_bill(student.id, term_id) if term_id else None
    enrollment, report = build_report_card(student.id, term_id) if term_id else (None, None)
    # Only reveal results once they have been finalised (positions computed).
    results_ready = bool(report and report.get('term_summary'))

    attendance = None
    if enrollment:
        week_ids = [w.id for w in Week.query.filter_by(term_id=term_id).all()]
        attendance = _attendance_pct(enrollment.id, week_ids)

    announcements = [a for a in Announcement.query.filter(
        Announcement.audience.in_(['All', 'Parents'])).order_by(
        Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(10).all()
        if a.is_active][:5]

    return render_template('parent/home.html',
        student=student, terms=terms, term_id=term_id, bill=bill,
        report=report if results_ready else None, results_ready=results_ready,
        enrollment=enrollment, attendance=attendance, announcements=announcements)
