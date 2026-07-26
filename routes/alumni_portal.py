"""Alumni (graduate) self-service portal — Phase 3.

A separate, public-facing login (no admin/staff session). A graduate signs in with
their Admission No. plus EITHER their student-portal password OR a verification
code from a document the school issued them. Once in they can:

  * view and download the documents the school issued them (non-revoked);
  * keep their career / higher-education / contact profile up to date;
  * request a document (a transcript, testimonial, …) for the school to fulfil;
  * read a summary of their academic record.

Tenant-aware: like the rest of the app the request is already routed to the right
school database by subdomain before this blueprint runs.
"""
from functools import wraps

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash, send_file, abort)

from models import (db, Student, GraduateDocument, AlumniProfile, DocumentRequest,
                    GRADUATE_DOC_TYPES)
from utils.security import login_limiter

alumni_bp = Blueprint('alumni', __name__, url_prefix='/alumni')

ALUMNI_KEY = 'alumni_student_id'


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------
def _current():
    sid = session.get(ALUMNI_KEY)
    s = db.session.get(Student, sid) if sid else None
    if s and s.is_active and s.is_graduated:
        return s
    return None


def alumni_login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not _current():
            session.pop(ALUMNI_KEY, None)
            return redirect(url_for('alumni.login'))
        return f(*a, **k)
    return wrapper


def _authenticate(student_id, credential):
    """Return the graduate if the credential is a valid portal password OR a valid,
    non-revoked verification code belonging to them. None otherwise."""
    student = Student.query.filter_by(
        student_id=(student_id or '').strip(), is_active=True, is_graduated=True).first()
    if not student:
        return None
    cred = (credential or '').strip()
    if not cred:
        return None
    try:
        if student.check_portal_password(cred):
            return student
    except Exception:
        pass
    # a verification code identifies exactly one document; require it to be theirs
    doc = GraduateDocument.query.filter_by(
        student_id=student.id, verification_code=cred.upper(), revoked=False).first()
    if doc:
        return student
    return None


def _profile(student):
    prof = AlumniProfile.query.filter_by(student_id=student.id).first()
    if prof is None:
        prof = AlumniProfile(student_id=student.id)
        db.session.add(prof)
        db.session.commit()
    return prof


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@alumni_bp.route('/login', methods=['GET', 'POST'])
def login():
    if _current():
        return redirect(url_for('alumni.home'))
    if request.method == 'POST':
        student_id = (request.form.get('student_id') or '').strip()
        credential = request.form.get('credential') or ''
        rkey = f"alumni_login:{request.remote_addr or 'unknown'}"
        akey = f"alumni_login_acct:{student_id.lower()}" if student_id else rkey
        if (login_limiter.is_rate_limited(rkey, max_attempts=15, window_minutes=15)
                or login_limiter.is_rate_limited(akey, max_attempts=10, window_minutes=15)):
            wait = login_limiter.get_remaining_time(rkey, 15) // 60 + 1
            flash(f'Too many attempts. Try again in about {wait} minute(s).', 'error')
            return render_template('alumni/login.html')
        student = _authenticate(student_id, credential)
        if student:
            login_limiter.clear_attempts(rkey)
            login_limiter.clear_attempts(akey)
            session.clear()                       # prevent session fixation
            session[ALUMNI_KEY] = student.id
            from utils.csrf import rotate_csrf_token
            rotate_csrf_token()
            return redirect(url_for('alumni.home'))
        login_limiter.record_attempt(rkey)
        login_limiter.record_attempt(akey)
        flash('Invalid admission number or credential. '
              'Use your portal password or a verification code from one of your documents.', 'error')
    return render_template('alumni/login.html')


@alumni_bp.route('/logout')
def logout():
    session.pop(ALUMNI_KEY, None)
    return redirect(url_for('alumni.login'))


@alumni_bp.route('/')
@alumni_login_required
def home():
    student = _current()
    prof = _profile(student)
    docs = (GraduateDocument.query
            .filter_by(student_id=student.id, revoked=False)
            .order_by(GraduateDocument.created_at.desc()).all())
    reqs = (DocumentRequest.query
            .filter_by(student_id=student.id)
            .order_by(DocumentRequest.requested_at.desc()).limit(30).all())
    from utils.graduate_record import build_record
    record = build_record(student)
    grad_session = student.graduation_session.name if student.graduation_session else None
    return render_template(
        'alumni/home.html', student=student, prof=prof, docs=docs, reqs=reqs,
        record=record, grad_session=grad_session,
        doc_types=GRADUATE_DOC_TYPES, editable=AlumniProfile.EDITABLE)


@alumni_bp.route('/profile', methods=['POST'])
@alumni_login_required
def save_profile():
    student = _current()
    prof = _profile(student)
    for f in AlumniProfile.EDITABLE:
        setattr(prof, f, (request.form.get(f) or '').strip() or None)
    prof.willing_to_mentor = bool(request.form.get('willing_to_mentor'))
    prof.updated_by = 'self'
    db.session.commit()
    flash('Your profile has been updated.', 'success')
    return redirect(url_for('alumni.home') + '#profile')


@alumni_bp.route('/document/<doc_type>')
@alumni_login_required
def document(doc_type):
    """Download a document the school ALREADY issued to this alumnus. Alumni can
    only re-download issued, non-revoked documents — they can't self-issue."""
    student = _current()
    doc = GraduateDocument.query.filter_by(
        student_id=student.id, doc_type=doc_type, revoked=False).first()
    if not doc:
        abort(404)
    from utils import graduate_docs
    from utils.production import secure_external_url
    verify_url = secure_external_url('graduate_verify.verify', code=doc.verification_code)
    buf, fname = graduate_docs.render(student, doc, verify_url)
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=fname)


@alumni_bp.route('/request', methods=['POST'])
@alumni_login_required
def request_document():
    student = _current()
    doc_type = (request.form.get('doc_type') or '').strip()
    if doc_type not in GRADUATE_DOC_TYPES:
        flash('Please choose a valid document type.', 'error')
        return redirect(url_for('alumni.home') + '#request')
    # one open request per document type keeps the admin inbox sane
    existing = DocumentRequest.query.filter_by(
        student_id=student.id, doc_type=doc_type, status='pending').first()
    if existing:
        flash('You already have a pending request for that document.', 'error')
        return redirect(url_for('alumni.home') + '#request')
    db.session.add(DocumentRequest(
        student_id=student.id, doc_type=doc_type, status='pending',
        note=(request.form.get('note') or '').strip()[:500] or None))
    db.session.commit()
    flash('Your request has been sent to the school.', 'success')
    return redirect(url_for('alumni.home') + '#request')
