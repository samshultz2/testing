"""Parent portal — parents sign in with their child's Student ID + portal
password to view results, attendance and fee balance (read-only)."""
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Student, Term, Week, Announcement, FeePayment
from utils.finance import student_bill, next_receipt_no
from utils.report_card import build_report_card, _attendance_pct
from utils.helpers import get_active_term
from utils import payments
from utils.security import login_limiter

parent_bp = Blueprint('parent', __name__, url_prefix='/parent')
PKEY = 'parent_student_id'      # the child currently being viewed
AUTHKEY = 'parent_auth_id'      # the child whose password was used to sign in


def _render(payload):
    """Parent portal shell, or JSON for in-portal (no-reload) navigation.

    The parent portal is its own public mini-app (not the staff shell), so it
    has a dedicated standalone page. Flash messages (e.g. a payment result on
    the redirect back from Paystack) are folded into the payload on a full load
    so the React app can surface them."""
    from utils.spa import wants_json
    from flask import jsonify, get_flashed_messages
    if wants_json():
        return jsonify(payload)
    payload = {**payload, 'flashes': [{'category': c, 'message': m}
               for c, m in get_flashed_messages(with_categories=True)]}
    return render_template('parent/app.html', parent_json=payload)


def _report_payload(report, affective_traits, rating_labels):
    """Serialise the report-card dict for the React portal."""
    if not report:
        return None
    ts = report.get('term_summary')
    aff = getattr(ts, 'affective_map', None) or {} if ts else {}
    return {
        'assessment_types': [{'id': at.id, 'label': at.short_name or at.name}
                             for at in report['assessment_types']],
        'subjects': [{'name': row['subject'].name,
                      'assessments': {str(at.id): row['assessments'].get(at.id)
                                      for at in report['assessment_types']},
                      'total': row['total'], 'grade': row['grade'], 'remark': row['remark']}
                     for row in report['subjects']],
        'average': report['average'], 'overall_grade': report['overall_grade'],
        'position': (ts.position_in_class if ts else None),
        'teacher_comment': (ts.teacher_comment if ts else None),
        'principal_comment': (ts.principal_comment if ts else None),
        'affective': [{'label': label, 'rating': aff.get(key),
                       'rating_label': rating_labels.get(aff.get(key), '')}
                      for key, label in affective_traits if aff.get(key)],
    }


def parent_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get(PKEY):
            return redirect(url_for('parent.login'))
        # Idle timeout for the parent session (mirrors the staff one).
        import time
        from config import Config
        mins = getattr(Config, 'SESSION_IDLE_MINUTES', 0)
        now = int(time.time())
        last = session.get('parent_seen')
        session['parent_seen'] = now
        if mins and last and (now - last) > mins * 60:
            for k in (PKEY, AUTHKEY, 'parent_seen'):
                session.pop(k, None)
            flash('Your session timed out. Please sign in again.', 'warning')
            return redirect(url_for('parent.login'))
        return f(*args, **kwargs)
    return wrapper


def _current_student():
    sid = session.get(PKEY)
    return db.session.get(Student, sid) if sid else None


def _siblings(student):
    """Active students who share a parent phone number with this child."""
    phones = {c.phone_number for c in student.parent_contacts.all() if c.phone_number}
    if not phones:
        return [student]
    from models import ParentContact
    ids = {pc.student_id for pc in ParentContact.query.filter(
        ParentContact.phone_number.in_(phones)).all()}
    ids.add(student.id)
    sibs = (Student.query.filter(Student.id.in_(ids), Student.is_active == True)
            .order_by(Student.surname, Student.first_name).all())
    return sibs or [student]


@parent_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get(PKEY):
        return redirect(url_for('parent.home'))
    if request.method == 'POST':
        # Throttle credential guessing by client IP.
        rkey = f"parent_login:{request.remote_addr or 'unknown'}"
        if login_limiter.is_rate_limited(rkey, max_attempts=10, window_minutes=15):
            wait = login_limiter.get_remaining_time(rkey, 15) // 60 + 1
            flash(f'Too many attempts. Please try again in about {wait} minute(s).', 'error')
            return redirect(url_for('parent.login'))
        sid = (request.form.get('student_id') or '').strip()
        pw = request.form.get('password') or ''
        student = Student.query.filter_by(student_id=sid).first()
        if student and student.is_active and student.check_portal_password(pw):
            login_limiter.clear_attempts(rkey)
            session[PKEY] = student.id
            session[AUTHKEY] = student.id
            session.permanent = True
            return redirect(url_for('parent.home'))
        login_limiter.record_attempt(rkey)
        flash('Invalid Student ID or password.', 'error')
        return redirect(url_for('parent.login'))
    return render_template('parent/login.html')


@parent_bp.route('/logout')
def logout():
    for k in (PKEY, AUTHKEY, 'parent_seen'):
        session.pop(k, None)
    flash('You have been signed out.', 'info')
    return redirect(url_for('parent.login'))


@parent_bp.route('/child/<int:student_id>')
@parent_required
def switch_child(student_id):
    """Switch the viewed child (only among the signed-in family's children)."""
    auth = db.session.get(Student, session.get(AUTHKEY))
    if auth and student_id in {s.id for s in _siblings(auth)}:
        session[PKEY] = student_id
    else:
        flash('That child is not linked to your account.', 'error')
    return redirect(url_for('parent.home'))


@parent_bp.route('/')
@parent_required
def home():
    student = _current_student()
    if not student:
        session.pop(PKEY, None)
        return redirect(url_for('parent.login'))

    from utils.report_card import active_traits, RATING_LABELS
    term_id = request.args.get('term_id', type=int)
    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None
    terms = Term.query.order_by(Term.id.desc()).all()
    term = db.session.get(Term, term_id) if term_id else None

    bill = student_bill(student.id, term_id) if term_id else None
    enrollment, report = build_report_card(student.id, term_id) if term_id else (None, None)
    # Results are visible to parents only when the term is RELEASED (published) by
    # staff and finalised (positions computed).
    results_ready = (bool(report and report.get('term_summary'))
                     and bool(term and term.results_published))

    attendance = None
    if enrollment:
        week_ids = [w.id for w in Week.query.filter_by(term_id=term_id).all()]
        attendance = _attendance_pct(enrollment.id, week_ids)

    announcements = [a for a in Announcement.query.filter(
        Announcement.audience.in_(['All', 'Parents'])).order_by(
        Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(10).all()
        if a.is_active][:5]

    auth = db.session.get(Student, session.get(AUTHKEY)) or student
    siblings = _siblings(auth)
    aff_traits = active_traits()
    return _render({
        'page': 'home',
        'student': {'full_name': student.full_name, 'student_id': student.student_id,
                    'class_name': (enrollment.class_arm_assignment.display_name
                                   if enrollment else None)},
        'terms': [{'id': t.id, 'name': t.name} for t in terms],
        'term_id': term_id,
        'bill': ({'balance': bill['balance'], 'payable': bill['payable'], 'paid': bill['paid']}
                 if bill else None),
        'pay_enabled': payments.is_configured(),
        'attendance': attendance,
        'report': _report_payload(report if results_ready else None, aff_traits, RATING_LABELS),
        'results_ready': results_ready,
        'announcements': [{'title': a.title, 'body': a.body, 'is_pinned': bool(a.is_pinned)}
                          for a in announcements],
        'siblings': [{'id': s.id, 'full_name': s.full_name,
                      'switch_url': url_for('parent.switch_child', student_id=s.id),
                      'is_current': s.id == student.id} for s in siblings],
        'urls': {
            'self': url_for('parent.home'),
            'logout': url_for('parent.logout'),
            'pay': url_for('parent.pay'),
            'report_pdf': url_for('parent.report_pdf', term_id=term_id),
            'staff_login': url_for('auth.login'),
        },
    })


def _record_online_payment(student_id, term_id, amount, reference):
    """Idempotently record a verified online payment. Returns the FeePayment."""
    if not (student_id and term_id and reference):
        return None
    existing = FeePayment.query.filter_by(reference=reference).first()
    if existing:
        return existing
    student = db.session.get(Student, student_id)
    if not student:
        return None
    pay = FeePayment(
        student_id=student.id, term_id=term_id, branch_id=student.branch_id,
        amount=amount, method='Online', reference=reference,
        receipt_no=next_receipt_no(), received_by='Online (Paystack)')
    db.session.add(pay)
    db.session.commit()
    return pay


@parent_bp.route('/report.pdf')
@parent_required
def report_pdf():
    """Download the child's report card (only when released + finalised)."""
    from flask import send_file
    from models import SchoolSettings
    from utils.report_pdf import report_card_pdf
    from utils.report_card import active_traits, RATING_LABELS
    student = _current_student()
    if not student:
        return redirect(url_for('parent.login'))
    term_id = request.args.get('term_id', type=int) or (
        get_active_term().id if get_active_term() else None)
    term = db.session.get(Term, term_id) if term_id else None
    _, report = build_report_card(student.id, term_id) if term_id else (None, None)
    if not (report and report.get('term_summary') and term and term.results_published):
        flash('Your child\'s results are not available for download yet.', 'error')
        return redirect(url_for('parent.home', term_id=term_id))
    buf = report_card_pdf(student, report, term,
                          SchoolSettings.get('school_name', 'School'),
                          active_traits(), RATING_LABELS)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f'{student.student_id}_report.pdf')


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
        callback_url=url_for('parent.pay_callback', _external=True),
        metadata={'student_id': student.id, 'term_id': term_id})
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

    if FeePayment.query.filter_by(reference=reference).first():
        session.pop('pay_ref', None)
        flash('Payment already recorded. Thank you.', 'success')
        return redirect(url_for('parent.home', term_id=pending.get('term_id')))

    res = payments.verify(reference)
    if not (res.get('ok') and res.get('success')):
        flash(res.get('error') or 'Payment was not completed.', 'error')
        return redirect(url_for('parent.home', term_id=pending.get('term_id')))

    amount = res.get('amount_naira') or pending['amount']
    _record_online_payment(pending['student_id'], pending['term_id'], amount, reference)
    session.pop('pay_ref', None)
    flash(f'Payment of ₦{amount:,.0f} received. Thank you!', 'success')
    return redirect(url_for('parent.home', term_id=pending['term_id']))


@parent_bp.route('/pay/webhook', methods=['POST'])
def pay_webhook():
    """Paystack server-to-server webhook — the reliable record path (the browser
    redirect callback can be dropped). Verifies the HMAC signature, then records
    a successful charge from its metadata (idempotent by reference)."""
    import hmac
    import hashlib
    from config import Config
    secret = (Config.PAYSTACK_SECRET_KEY or '').encode()
    signature = request.headers.get('x-paystack-signature', '')
    body = request.get_data()
    if not secret or not signature:
        return ('', 400)
    expected = hmac.new(secret, body, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return ('', 400)

    event = request.get_json(silent=True) or {}
    if event.get('event') == 'charge.success':
        data = event.get('data') or {}
        meta = data.get('metadata') or {}
        try:
            student_id = int(meta.get('student_id'))
            term_id = int(meta.get('term_id'))
        except (TypeError, ValueError):
            student_id = term_id = None
        amount = (data.get('amount', 0) or 0) / 100.0
        if data.get('status') == 'success':
            _record_online_payment(student_id, term_id, amount, data.get('reference'))
    return ('', 200)
