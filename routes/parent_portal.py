"""Parent portal — parents sign in with their child's Student ID + portal
password to view results, attendance and fee balance (read-only)."""
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Student, Term, Week, Announcement, FeePayment
from utils.finance import student_bill, next_receipt_no
from utils.report_card import build_report_card, _attendance_pct
from utils.helpers import get_active_term
from utils import payments

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
        enrollment=enrollment, attendance=attendance, announcements=announcements,
        pay_enabled=payments.is_configured())


@parent_bp.route('/pay', methods=['POST'])
@parent_required
def pay():
    """Start an online fee payment for the signed-in parent's child."""
    student = _current_student()
    if not student:
        return redirect(url_for('parent.login'))
    if not payments.is_configured():
        flash('Online payment is not available right now.', 'error')
        return redirect(url_for('parent.home'))
    term_id = request.form.get('term_id', type=int) or (get_active_term().id if get_active_term() else None)
    amount = request.form.get('amount', type=float)
    bill = student_bill(student.id, term_id) if term_id else None
    if not amount or amount <= 0:
        amount = bill['balance'] if bill else 0
    if not term_id or amount <= 0:
        flash('Nothing to pay for this term.', 'info')
        return redirect(url_for('parent.home', term_id=term_id))
    reference = payments.new_reference()
    session['pay_ref'] = {'ref': reference, 'student_id': student.id,
                          'term_id': term_id, 'amount': amount}
    res = payments.initialize(
        email=request.form.get('email') or '',
        amount_naira=amount, reference=reference,
        callback_url=url_for('parent.pay_callback', _external=True))
    if res.get('ok'):
        return redirect(res['authorization_url'])
    flash(res.get('error', 'Could not start the payment.'), 'error')
    return redirect(url_for('parent.home', term_id=term_id))


@parent_bp.route('/pay/callback')
@parent_required
def pay_callback():
    """Verify the returned transaction and record the fee payment (idempotent)."""
    reference = request.args.get('reference') or request.args.get('trxref')
    pending = session.get('pay_ref') or {}
    if not reference or reference != pending.get('ref'):
        flash('Payment could not be matched. If you were charged, contact the school.', 'error')
        return redirect(url_for('parent.home'))

    # Idempotency: never record the same reference twice.
    if FeePayment.query.filter_by(reference=reference).first():
        session.pop('pay_ref', None)
        flash('Payment already recorded. Thank you.', 'success')
        return redirect(url_for('parent.home', term_id=pending.get('term_id')))

    res = payments.verify(reference)
    if not (res.get('ok') and res.get('success')):
        flash(res.get('error') or 'Payment was not completed.', 'error')
        return redirect(url_for('parent.home', term_id=pending.get('term_id')))

    student = Student.query.get(pending['student_id'])
    amount = res.get('amount_naira') or pending['amount']
    db.session.add(FeePayment(
        student_id=student.id, term_id=pending['term_id'], branch_id=student.branch_id,
        amount=amount, method='Online', reference=reference,
        receipt_no=next_receipt_no(), received_by='Online (Paystack)'))
    db.session.commit()
    session.pop('pay_ref', None)
    flash(f'Payment of ₦{amount:,.0f} received. Thank you!', 'success')
    return redirect(url_for('parent.home', term_id=pending['term_id']))
