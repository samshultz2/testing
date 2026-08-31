"""main blueprint — branches routes (split from the former routes/main.py)."""
from routes.main import *  # noqa: F401,F403  (blueprint, models, helpers)


@main_bp.route('/set-branch')
@login_required
def set_view_branch():
    """Central users switch the branch they're viewing ('all' clears it)."""
    from utils.branch_scope import is_central, VIEW_KEY
    if is_central():
        raw = request.args.get('branch_id')
        if raw in (None, '', 'all'):
            session.pop(VIEW_KEY, None)
        else:
            try:
                session[VIEW_KEY] = int(raw)
            except (TypeError, ValueError):
                session.pop(VIEW_KEY, None)
    return safe_redirect(url_for('main.dashboard'))


@main_bp.route('/branch-overview')
@login_required
def branch_overview():
    """Cross-branch comparison for central users (Director of Studies etc.)."""
    from utils.branch_scope import is_central
    if not is_central():
        flash('That page is for central staff.', 'error')
        return redirect(url_for('main.dashboard'))

    from models import Branch, StaffMember, FeePayment, Sale, WAECResult, JAMBResult
    active_term = get_active_term()

    def _waec_benchmark(credit_subjects):
        """5+ credits including English & Mathematics — the standard WAEC pass."""
        has_eng = any('english' in s.lower() for s in credit_subjects)
        has_math = any('math' in s.lower() for s in credit_subjects)
        return len(credit_subjects) >= 5 and has_eng and has_math

    rows = []
    totals = {'students': 0, 'staff': 0, 'collected': 0.0, 'sales': 0.0,
              'waec': 0, 'waec_pass': 0}
    for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all():
        students = Student.query.filter_by(branch_id=b.id, is_active=True).count()
        staff = StaffMember.query.filter_by(branch_id=b.id, is_active=True).count()
        collected = 0.0
        if active_term:
            collected = (db.session.query(func.coalesce(func.sum(FeePayment.amount), 0.0))
                         .filter(FeePayment.branch_id == b.id,
                                 FeePayment.term_id == active_term.id).scalar()) or 0.0
        sales = (db.session.query(func.coalesce(func.sum(Sale.total), 0.0))
                 .filter(Sale.branch_id == b.id).scalar()) or 0.0
        # WAEC: candidates + how many met the 5-credit (incl Eng & Maths) benchmark.
        credits_by_student = {}
        for sid, subj, grade in (db.session.query(
                WAECResult.student_id, WAECResult.subject, WAECResult.grade)
                .join(Student, WAECResult.student_id == Student.id)
                .filter(Student.branch_id == b.id).all()):
            if WAECResult.is_pass(grade):
                credits_by_student.setdefault(sid, set()).add(subj)
        waec = (db.session.query(func.count(func.distinct(WAECResult.student_id)))
                .join(Student, WAECResult.student_id == Student.id)
                .filter(Student.branch_id == b.id).scalar()) or 0
        waec_pass = sum(1 for subs in credits_by_student.values() if _waec_benchmark(subs))
        jamb_avg = (db.session.query(func.avg(JAMBResult.total_score))
                    .join(Student, JAMBResult.student_id == Student.id)
                    .filter(Student.branch_id == b.id).scalar())
        jamb_avg = round(jamb_avg, 1) if jamb_avg else 0
        rows.append({'branch': b, 'students': students, 'staff': staff,
                     'collected': collected, 'sales': sales, 'waec': waec,
                     'waec_pass': waec_pass, 'jamb_avg': jamb_avg})
        totals['students'] += students
        totals['staff'] += staff
        totals['collected'] += collected
        totals['sales'] += sales
        totals['waec'] += waec
        totals['waec_pass'] += waec_pass
    return render_template('branch_overview.html', rows=rows, totals=totals,
                           active_term=active_term)


@main_bp.route('/view-session', methods=['POST'])
@admin_required
def set_view_session():
    """Admin 'time-travel': view a past session's data without changing the live
    session for anyone else. Stored per-user in the cookie session; choosing the
    live session (or none) clears it."""
    from models import AcademicSession
    sid = request.form.get('session_id', type=int)
    live = AcademicSession.query.filter_by(is_active=True).first()
    if not sid or (live and sid == live.id):
        session.pop('view_session_id', None)
        flash('Viewing the current session.', 'success')
    else:
        s = db.session.get(AcademicSession, sid)
        if s:
            session['view_session_id'] = sid
            flash(f'Now viewing {s.name} (read-only time-travel). Your view only — '
                  'others are unaffected.', 'info')
    # Drop any explicit ?year (and paging) from the page we came back to, so
    # session-scoped pages (external exams) re-default to the chosen session.
    return redirect(_strip_params(request.referrer, ('year', 'page')) or url_for('main.dashboard'))


def _strip_params(url, names):
    """Return ``url`` with the given query params removed (same-origin only)."""
    if not url:
        return None
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in names]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
    except Exception:
        return url
