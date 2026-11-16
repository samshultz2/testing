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
    """Cross-branch comparison for central users (Director of Studies etc.).
    Every figure covers the same period so branches compare fairly: fees and
    sales for the active term, WAEC/JAMB for one exam year (this session's, or
    the one picked with ?year=)."""
    from utils.branch_scope import is_central
    if not is_central():
        flash('That page is for central staff.', 'error')
        return redirect(url_for('main.dashboard'))

    import datetime as _dt
    from models import Branch, StaffMember, FeePayment, Sale, WAECResult, JAMBResult
    from utils.helpers import exam_year_choices
    from utils.exam_subject_config import current_exam_year
    active_term = get_active_term()

    years_with = sorted({y for (y,) in db.session.query(WAECResult.exam_year).distinct()} |
                        {y for (y,) in db.session.query(JAMBResult.exam_year).distinct()}, reverse=True)
    cy = current_exam_year()
    year = request.args.get('year', type=int) or (cy if cy in years_with else (years_with[0] if years_with else cy))
    labels = dict(exam_year_choices())

    # Sales for the active term's dates (falls back to all time when unset).
    t_from = active_term.start_date if active_term else None
    t_to = active_term.end_date if active_term else None

    def _waec_benchmark(credit_subjects):
        """5+ credits including English & Mathematics — the standard WAEC pass."""
        has_eng = any('english' in s.lower() for s in credit_subjects)
        has_math = any('math' in s.lower() for s in credit_subjects)
        return len(credit_subjects) >= 5 and has_eng and has_math

    rows = []
    totals = {'students': 0, 'staff': 0, 'collected': 0.0, 'sales': 0.0,
              'waec': 0, 'waec_pass': 0, 'jamb': 0, 'jamb_sum': 0.0}
    for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all():
        students = Student.query.filter_by(branch_id=b.id, is_active=True).count()
        staff = StaffMember.query.filter_by(branch_id=b.id, is_active=True).count()
        collected = 0.0
        if active_term:
            collected = float((db.session.query(func.coalesce(func.sum(FeePayment.amount), 0.0))
                               .filter(FeePayment.branch_id == b.id,
                                       FeePayment.term_id == active_term.id).scalar()) or 0.0)
        sq = db.session.query(func.coalesce(func.sum(Sale.total), 0.0)).filter(Sale.branch_id == b.id)
        if t_from:
            sq = sq.filter(Sale.created_at >= _dt.datetime.combine(t_from, _dt.time.min))
        if t_to:
            sq = sq.filter(Sale.created_at <= _dt.datetime.combine(t_to, _dt.time.max))
        sales = float(sq.scalar() or 0.0)
        credits_by_student, cands = {}, set()
        if year:
            for sid, subj, grade in (db.session.query(
                    WAECResult.student_id, WAECResult.subject, WAECResult.grade)
                    .join(Student, WAECResult.student_id == Student.id)
                    .filter(Student.branch_id == b.id, WAECResult.exam_year == year).all()):
                cands.add(sid)
                if WAECResult.is_pass(grade):
                    credits_by_student.setdefault(sid, set()).add(subj)
        waec = len(cands)
        waec_pass = sum(1 for subs in credits_by_student.values() if _waec_benchmark(subs))
        jn, jsum = (db.session.query(func.count(JAMBResult.id), func.coalesce(func.sum(JAMBResult.total_score), 0))
                    .join(Student, JAMBResult.student_id == Student.id)
                    .filter(Student.branch_id == b.id, JAMBResult.exam_year == year).first()) if year else (0, 0)
        jn, jsum = int(jn or 0), float(jsum or 0)
        rows.append({'branch': b, 'students': students, 'staff': staff,
                     'ratio': round(students / staff, 1) if staff else None,
                     'collected': collected, 'sales': sales, 'waec': waec, 'waec_pass': waec_pass,
                     'waec_rate': round(waec_pass / waec * 100) if waec else None,
                     'jamb': jn, 'jamb_avg': round(jsum / jn, 1) if jn else None,
                     'view_url': url_for('main.set_view_branch', branch_id=b.id)})
        for k, v in (('students', students), ('staff', staff), ('collected', collected), ('sales', sales),
                     ('waec', waec), ('waec_pass', waec_pass), ('jamb', jn), ('jamb_sum', jsum)):
            totals[k] += v
    totals['waec_rate'] = round(totals['waec_pass'] / totals['waec'] * 100) if totals['waec'] else None
    totals['jamb_avg'] = round(totals['jamb_sum'] / totals['jamb'], 1) if totals['jamb'] else None
    totals['ratio'] = round(totals['students'] / totals['staff'], 1) if totals['staff'] else None
    return render_template('branch_overview.html', rows=rows, totals=totals,
                           active_term=active_term, year=year,
                           year_label=labels.get(year, str(year) if year else ''),
                           years=[(y, labels.get(y, str(y))) for y in years_with] if years_with else [],
                           sales_period=bool(t_from or t_to))


@main_bp.route('/view-session', methods=['POST'])
@admin_required
def set_view_session():
    """Admin 'time-travel': view a past session's data without changing the live
    session for anyone else. Stored per-user in the cookie session; choosing the
    live session (or none) clears it."""
    from models import AcademicSession
    sid = request.form.get('session_id', type=int)
    live = AcademicSession.query.filter_by(is_active=True).first()
    if request.form.get('back'):
        # "Back to current" shares the form with the session picker, whose own
        # session_id (the past one) would otherwise win.
        sid = live.id if live else None
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
