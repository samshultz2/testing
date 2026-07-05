"""main blueprint — misc routes (split from the former routes/main.py)."""
from routes.main import *  # noqa: F401,F403  (blueprint, models, helpers)
from utils.search import like_term, ilike_contains


@main_bp.route('/share')
@login_required
def share_app():
    """A shareable panel: the app's current public URL + a QR code, so teachers
    can scan and open the demo on their own phones (no shared Wi-Fi needed)."""
    # Behind the Cloudflare tunnel (TRUST_PROXY/ProxyFix) this is the external
    # https URL; locally it's the LAN address. Either way it's what visitors use.
    url = request.url_root.rstrip('/') or request.host_url.rstrip('/')

    qr_svg = None
    try:
        import io as _io
        import qrcode
        import qrcode.image.svg as _svg
        buf = _io.BytesIO()
        qrcode.make(url, image_factory=_svg.SvgPathImage, box_size=12, border=2).save(buf)
        svg = buf.getvalue().decode('utf-8')
        # Drop the fixed mm size so it scales to its container.
        svg = re.sub(r'(<svg[^>]*?)\s+width="[^"]*"\s+height="[^"]*"', r'\1', svg, count=1)
        qr_svg = svg
    except Exception:
        qr_svg = None  # library missing — page still shows the URL

    return render_template('share.html', share_url=url, qr_svg=qr_svg)


@main_bp.route('/search')
@login_required
def global_search():
    """Search across the main entities and group the results."""
    q = (request.args.get('q') or '').strip()
    from utils.branch_scope import scope_query
    groups = []
    if len(q) >= 2:
        like = like_term(q)

        def add(title, icon, items):
            if items:
                groups.append({'title': title, 'icon': icon, 'rows': items})

        students = (_viewer_student_scope(Student.query.filter_by(is_active=True))
                    .filter(db.or_(Student.first_name.ilike(like, escape='\\'), Student.surname.ilike(like, escape='\\'),
                                   Student.student_id.ilike(like, escape='\\')))
                    .order_by(Student.surname).limit(12).all())
        add('Students', 'fa-user-graduate', [
            {'label': s.full_name, 'sub': s.student_id,
             'url': url_for('main.view_student', student_id=s.id)} for s in students])

        try:
            from models import StaffMember
            staff = (scope_query(StaffMember.query.filter_by(is_active=True), StaffMember)
                     .filter(db.or_(StaffMember.first_name.ilike(like, escape='\\'), StaffMember.surname.ilike(like, escape='\\'),
                                    StaffMember.staff_id.ilike(like, escape='\\'), StaffMember.phone.ilike(like, escape='\\')))
                     .limit(10).all())
            add('Staff', 'fa-id-badge', [
                {'label': s.full_name, 'sub': s.designation or s.staff_id,
                 'url': url_for('hr.staff_detail', staff_id=s.id)} for s in staff])
        except Exception:
            pass

        try:
            from models import Applicant
            apps = (scope_query(Applicant.query, Applicant)
                    .filter(db.or_(Applicant.first_name.ilike(like, escape='\\'),
                    Applicant.surname.ilike(like, escape='\\'), Applicant.application_no.ilike(like, escape='\\')))
                    .limit(10).all())
            add('Applicants', 'fa-clipboard-user', [
                {'label': a.full_name, 'sub': f'{a.application_no} · {a.status}',
                 'url': url_for('admissions.applicant_detail', applicant_id=a.id)} for a in apps])
        except Exception:
            pass

        try:
            from models import Book
            books = (scope_query(Book.query.filter_by(is_active=True), Book)
                     .filter(db.or_(Book.title.ilike(like, escape='\\'), Book.author.ilike(like, escape='\\'), Book.isbn.ilike(like, escape='\\')))
                     .limit(10).all())
            add('Library books', 'fa-book', [
                {'label': b.title, 'sub': b.author or '', 'url': url_for('library.books', q=b.title)}
                for b in books])
        except Exception:
            pass

        try:
            from models import FeePayment
            pays = (scope_query(FeePayment.query.filter(FeePayment.receipt_no.ilike(like, escape='\\')), FeePayment)
                    .options(joinedload(FeePayment.student)).limit(8).all())
            add('Fee receipts', 'fa-receipt', [
                {'label': p.receipt_no, 'sub': (p.student.full_name if p.student else ''),
                 'url': url_for('finance.receipt', payment_id=p.id)} for p in pays])
        except Exception:
            pass

        try:
            from models import CBTExam
            exams = scope_query(CBTExam.query.filter(CBTExam.title.ilike(like, escape='\\')), CBTExam).limit(8).all()
            add('CBT exams', 'fa-laptop-code', [
                {'label': e.title, 'sub': (e.subject.name if e.subject else ''),
                 'url': url_for('cbt.exam_detail', exam_id=e.id)} for e in exams])
        except Exception:
            pass

    return render_template('search.html', q=q, groups=groups,
                           count=sum(len(g['rows']) for g in groups))


@main_bp.route('/set-theme', methods=['POST'])
@login_required
def set_theme():
    """Persist the current user's chosen UI theme (per-account + session)."""
    from utils.themes import normalize_theme
    theme = normalize_theme((request.form.get('theme') or '').strip())
    session['theme'] = theme
    try:
        from utils.access_control import get_current_user
        u = get_current_user()
        if u:
            u.theme = theme
            db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'ok': True, 'theme': theme})


@main_bp.route('/audit')
@central_admin_required
def audit_log():
    """View the audit trail of administrative actions (with filters)."""
    from models import AuditLog
    from datetime import datetime as _dt
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    action = (request.args.get('action') or '').strip()
    user = (request.args.get('user') or '').strip()
    from_s = request.args.get('from')
    to_s = request.args.get('to')

    query = AuditLog.query
    if q:
        like = like_term(q)
        query = query.filter(db.or_(AuditLog.action.ilike(like, escape='\\'),
                                    AuditLog.detail.ilike(like, escape='\\'),
                                    AuditLog.user.ilike(like, escape='\\'),
                                    AuditLog.target_label.ilike(like, escape='\\')))
    if action:
        query = query.filter(AuditLog.action == action)
    if user:
        query = query.filter(ilike_contains(AuditLog.user, user))
    try:
        if from_s:
            query = query.filter(AuditLog.created_at >= _dt.strptime(from_s, '%Y-%m-%d'))
        if to_s:
            d = _dt.strptime(to_s, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at < d.replace(hour=23, minute=59, second=59))
    except ValueError:
        pass

    logs = query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    actions = [a[0] for a in db.session.query(AuditLog.action).distinct().order_by(AuditLog.action).all()]
    from models import Branch
    branch_names = {b.id: b.name for b in Branch.query.all()}
    return render_template('audit.html', logs=logs, actions=actions, branch_names=branch_names,
        q=q, action=action, user=user, from_s=from_s or '', to_s=to_s or '')


@main_bp.route('/client-error', methods=['POST'])
def client_error():
    """Receive a client-side JS error report (from window.onerror / React error
    boundaries) so problems on users' devices surface in the Error Log. Rate
    limited and CSRF-exempt (it's diagnostic-only, no state change)."""
    from utils.error_tracking import record_error
    from utils.security import login_limiter
    key = 'clienterr:' + (request.remote_addr or 'x')
    if login_limiter.is_rate_limited(key, max_attempts=40, window_minutes=5):
        return ('', 204)
    login_limiter.record_attempt(key)
    data = request.get_json(silent=True) or {}
    record_error('client', (data.get('message') or 'JS error')[:500],
                 where=(data.get('url') or '')[:300],
                 user=session.get('username') or 'anonymous',
                 detail=((data.get('stack') or '') + '\nUA: ' +
                         (request.headers.get('User-Agent') or ''))[:6000])
    return ('', 204)


@main_bp.route('/api/notifications')
@login_required
def api_notifications():
    """Current user's notifications + unread count for the header bell."""
    from utils import notify as _n
    uid, role = _n.current_recipient()
    return jsonify({'count': _n.unread_count(uid, role),
                    'items': [x.to_dict() for x in _n.for_user(uid, role, limit=20)]})


@main_bp.route('/api/notifications/<int:nid>/read', methods=['POST'])
@login_required
def api_notification_read(nid):
    from utils import notify as _n
    uid, role = _n.current_recipient()
    _n.mark_read(uid, role, nid)
    return ('', 204)


@main_bp.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_notifications_read_all():
    from utils import notify as _n
    uid, role = _n.current_recipient()
    return jsonify({'cleared': _n.mark_all_read(uid, role)})


@main_bp.route('/error-log')
@central_admin_required
def error_log():
    """Recent server + client errors, newest first — so an admin can see at a
    glance what went wrong and where."""
    from utils.error_tracking import recent_errors
    return render_template('errors/recent.html', errors=recent_errors(200))
