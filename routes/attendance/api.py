"""attendance blueprint — api routes (split from the former routes/attendance.py)."""
from routes.attendance import *  # noqa: F401,F403


@attendance_bp.route('/api/summary/<int:assignment_id>/<date_str>')
@login_required
def api_daily_summary(assignment_id, date_str):
    """API endpoint for daily attendance summary"""
    require_branch_access(db.get_or_404(ClassArmAssignment, assignment_id).branch_id)
    if not can_view_attendance(assignment_id):   # teachers: their form class only
        return jsonify({'error': 'forbidden'}), 403
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        summary = get_daily_attendance_summary(assignment_id, target_date)
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@attendance_bp.route('/api/check-attendance')
@login_required
def api_check_attendance():
    """Check if attendance exists for a date/assignment"""
    assignment_id = request.args.get('assignment_id', type=int)
    target_date = request.args.get('date')
    
    if not assignment_id or not target_date:
        return jsonify({'exists': False})
    if not can_view_attendance(assignment_id):   # teachers: their form class only
        return jsonify({'error': 'forbidden'}), 403

    target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
    
    # Check if any attendance records exist
    exists = Attendance.query.join(StudentEnrollment).filter(
        StudentEnrollment.class_arm_assignment_id == assignment_id,
        Attendance.date == target_date
    ).first() is not None
    
    return jsonify({'exists': exists})


@attendance_bp.route('/api/school-days/<int:week_id>')
@login_required
def api_school_days(week_id):
    """Get school days for a week"""
    week = db.get_or_404(Week, week_id)
    holidays = Holiday.query.filter_by(term_id=week.term_id).all()
    holiday_dates = set(h.date for h in holidays)
    
    school_days = []
    current = week.start_date
    while current <= week.end_date:
        if current.weekday() < 5 and current not in holiday_dates:
            school_days.append({
                'date': current.isoformat(),
                'day_name': current.strftime('%A')
            })
        current += timedelta(days=1)
    
    return jsonify(school_days)


@attendance_bp.route('/app')
@login_required
def attendance_app():
    """The attendance mini-SPA. Self-loads its data from /api/context; the
    classic server-rendered pages remain available as a fallback.

    Anyone with attendance-module access may open it (read-only reports);
    the marking screens are additionally gated by can_mark_attendance, both in
    the UI (tabs hidden) and on every write endpoint."""
    if not can_access_module('attendance'):
        flash('You do not have access to attendance.', 'error')
        return redirect(url_for('main.dashboard'))
    return render_template('attendance/app.html')


@attendance_bp.route('/react')
@login_required
def attendance_react_redirect():
    """Legacy pilot URL — kept working; canonical path is /attendance/app."""
    return redirect(url_for('attendance.attendance_app', **request.args.to_dict()))


@attendance_bp.route('/api/roster')
@login_required
def api_roster():
    """Roster + existing marks for a class arm on a date (JSON).

    Branch-scoped and permission-checked; the React pilot caches this in
    IndexedDB so the register opens offline.
    """
    assignment_id = request.args.get('assignment_id', type=int)
    if not assignment_id:
        return jsonify({'error': 'assignment_id required'}), 400
    caa = db.get_or_404(ClassArmAssignment, assignment_id)
    require_branch_access(caa.branch_id)
    if not (can_mark_attendance(assignment_id) and can_access_class(assignment_id)):
        return jsonify({'error': 'forbidden'}), 403

    ds = request.args.get('date')
    try:
        target = datetime.strptime(ds, '%Y-%m-%d').date() if ds else date.today()
    except Exception:
        target = date.today()

    holidays = Holiday.query.filter_by(term_id=caa.term_id).all()
    week = _week_for_date(caa.term_id, target)
    hol = next((h for h in holidays if h.date == target), None)
    enrollments = (StudentEnrollment.query
                   .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                   .join(Student).order_by(*roster_order()).all())
    existing = {a.enrollment_id: a for a in Attendance.query.filter(
        Attendance.enrollment_id.in_([e.id for e in enrollments] or [-1]),
        Attendance.date == target).all()}
    students = [{
        'enrollment_id': e.id,
        'student_id': e.student.student_id,
        'name': e.student.full_name,
        'gender': e.student.gender,
        'morning_present': existing[e.id].morning_present if e.id in existing else True,
        'afternoon_present': existing[e.id].afternoon_present if e.id in existing else True,
    } for e in enrollments]
    return jsonify({
        'assignment_id': assignment_id,
        'class_name': caa.display_name,
        'date': target.isoformat(),
        'week_id': week.id if week else None,
        'school_day': is_school_day(target, holidays),
        'weekend': target.weekday() >= 5,
        'holiday': {'reason': hol.reason, 'type': hol.holiday_type} if hol else None,
        'students': students,
    })


@attendance_bp.route('/api/mark', methods=['POST'])
@login_required
def api_mark():
    """Record attendance from JSON — the React pilot's offline outbox flushes
    here. Idempotent upsert (mark_attendance_bulk), branch-scoped + CSRF."""
    from utils.calculations import mark_attendance_bulk
    data = request.get_json(silent=True) or {}
    assignment_id = data.get('assignment_id')
    caa = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    if not caa:
        return jsonify({'error': 'invalid assignment'}), 400
    require_branch_access(caa.branch_id)
    if not can_mark_attendance(assignment_id):
        return jsonify({'error': 'forbidden'}), 403
    try:
        target = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except Exception:
        return jsonify({'error': 'bad date'}), 400
    week = _week_for_date(caa.term_id, target)
    if not week:
        return jsonify({'error': 'no school week for that date'}), 400
    # Holidays/weekends are not school days — reject so the daily register
    # matches the week grid (which already excludes them).
    holidays = Holiday.query.filter_by(term_id=caa.term_id).all()
    if not is_school_day(target, holidays):
        hol = next((h for h in holidays if h.date == target), None)
        reason = hol.reason if hol else 'weekend'
        return jsonify({'error': f'not a school day ({reason})'}), 400

    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=assignment_id, is_active=True).all()
    enroll_ids = [e.id for e in enrollments]
    valid = set(enroll_ids)

    # Dual mode: morning + afternoon marked together (independent ticks), so a
    # student can be present in the morning and absent in the afternoon. The
    # React register sends `am`/`pm` present-lists in one save.
    if data.get('mode') == 'dual':
        am_ids = {int(x) for x in data.get('am', []) if int(x) in valid}
        pm_ids = {int(x) for x in data.get('pm', []) if int(x) in valid}
        try:
            for en in enrollments:
                att = Attendance.query.filter_by(enrollment_id=en.id, date=target).first()
                if att is None:
                    att = Attendance(enrollment_id=en.id, date=target, week_id=week.id)
                    db.session.add(att)
                att.week_id = week.id
                att.morning_present = en.id in am_ids
                att.afternoon_present = en.id in pm_ids
                att.marked_by = 'React'
            db.session.commit()
            from utils.calculations import _invalidate_analytics_for_week
            _invalidate_analytics_for_week(week.id)
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
        return jsonify({'ok': True, 'count': len(enrollments), 'date': target.isoformat(),
                        'session_type': 'dual'})

    session_type = 'afternoon' if data.get('session_type') == 'afternoon' else 'morning'
    auto_copy = bool(data.get('auto_copy', session_type == 'morning'))
    present = [int(x) for x in data.get('present', []) if int(x) in valid]
    try:
        count = mark_attendance_bulk(
            enroll_ids, target, week.id, session_type, present, marked_by='React',
            auto_copy_to_afternoon=auto_copy if session_type == 'morning' else False)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True, 'count': count, 'date': target.isoformat(),
                    'session_type': session_type})


@attendance_bp.route('/api/context')
@login_required
def api_context():
    """Selector data for the attendance SPA (term, terms, accessible classes,
    weeks, holidays) — cacheable so the picker works offline. View access is
    enough to open it; `can_mark` tells the SPA whether to show marking tabs."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    req_term = request.args.get('term_id', type=int)
    term = (db.session.get(Term, req_term) if req_term else None) or get_active_term()
    terms = [{'id': t.id, 'name': t.full_name, 'active': bool(t.is_active)}
             for t in Term.query.join(AcademicSession)
             .order_by(AcademicSession.name.desc(), Term.term_number).all()]
    classes, weeks, holidays = [], [], []
    default_class, default_week = None, None
    if term:
        form_classes = filter_classes_for_user(
            ClassArmAssignment.query.filter_by(term_id=term.id).all(), form_only=True)
        classes = [{'id': a.id, 'name': a.display_name} for a in form_classes]
        week_rows = Week.query.filter_by(term_id=term.id).order_by(Week.week_number).all()
        weeks = [{'id': w.id, 'number': w.week_number,
                  'start': w.start_date.isoformat(), 'end': w.end_date.isoformat()}
                 for w in week_rows]
        holidays = [h.date.isoformat() for h in Holiday.query.filter_by(term_id=term.id).all()]
        # Pre-selection: a form teacher lands on their class; everyone on the
        # current week.
        default_class = auto_select_assignment(form_classes)
        cw = pick_current_week(week_rows)
        default_week = cw.id if cw else None
    return jsonify({
        'term': {'id': term.id, 'name': term.full_name} if term else None,
        'terms': terms, 'classes': classes, 'weeks': weeks, 'holidays': holidays,
        'today': date.today().isoformat(),
        'default_class': default_class,   # form teacher's class (SPA auto-selects)
        'default_week': default_week,     # current week (SPA auto-selects)
        'can_mark': can_mark_attendance(),   # gates the marking tabs in the SPA
    })


@attendance_bp.route('/api/week')
@login_required
def api_week():
    """Weekly grid (students × school-days) with existing AM/PM marks."""
    assignment_id = request.args.get('assignment_id', type=int)
    week_id = request.args.get('week_id', type=int)
    if not assignment_id:
        return jsonify({'error': 'assignment_id required'}), 400
    caa = db.get_or_404(ClassArmAssignment, assignment_id)
    require_branch_access(caa.branch_id)
    if not (can_mark_attendance(assignment_id) and can_access_class(assignment_id)):
        return jsonify({'error': 'forbidden'}), 403
    week = db.session.get(Week, week_id) if week_id else None
    if not week:
        return jsonify({'error': 'week_id required'}), 400
    holidays = Holiday.query.filter_by(term_id=week.term_id).all()
    days = _week_school_days(week, holidays)
    enrollments = (StudentEnrollment.query
                   .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                   .join(Student).order_by(*roster_order()).all())
    recs = {}
    for r in Attendance.query.filter(
            Attendance.enrollment_id.in_([e.id for e in enrollments] or [-1]),
            Attendance.date.in_(days)).all():
        recs.setdefault(r.enrollment_id, {})[r.date.isoformat()] = {
            'am': bool(r.morning_present), 'pm': bool(r.afternoon_present)}
    students = [{
        'enrollment_id': e.id, 'student_id': e.student.student_id, 'name': e.student.full_name,
        'gender': e.student.gender,
        'days': {d.isoformat(): recs.get(e.id, {}).get(d.isoformat(), {'am': True, 'pm': True})
                 for d in days},
    } for e in enrollments]
    return jsonify({
        'assignment_id': assignment_id, 'class_name': caa.display_name,
        'week_id': week.id, 'week_number': week.week_number,
        'days': [{'date': d.isoformat(), 'label': d.strftime('%a %d/%m')} for d in days],
        'students': students,
    })


@attendance_bp.route('/api/week/mark', methods=['POST'])
@login_required
def api_week_mark():
    """Idempotent bulk upsert for the weekly grid. Body: {assignment_id, week_id,
    marks:[{enrollment_id, date, am, pm}]}. The offline outbox flushes here."""
    data = request.get_json(silent=True) or {}
    caa = db.session.get(ClassArmAssignment, data.get('assignment_id'))
    week = db.session.get(Week, data.get('week_id'))
    if not caa or not week:
        return jsonify({'error': 'invalid assignment/week'}), 400
    require_branch_access(caa.branch_id)
    if not can_mark_attendance(caa.id):
        return jsonify({'error': 'forbidden'}), 403
    holidays = Holiday.query.filter_by(term_id=week.term_id).all()
    valid_days = {d.isoformat() for d in _week_school_days(week, holidays)}
    enroll_ids = {e.id for e in StudentEnrollment.query.filter_by(
        class_arm_assignment_id=caa.id, is_active=True).all()}
    existing = {(r.enrollment_id, r.date.isoformat()): r for r in Attendance.query.filter(
        Attendance.enrollment_id.in_(list(enroll_ids) or [-1]),
        Attendance.week_id == week.id).all()}
    saved = 0
    try:
        for m in data.get('marks', []):
            eid, iso = m.get('enrollment_id'), m.get('date')
            if eid not in enroll_ids or iso not in valid_days:
                continue
            rec = existing.get((eid, iso))
            if rec is None:
                rec = Attendance(enrollment_id=eid, week_id=week.id,
                                 date=datetime.strptime(iso, '%Y-%m-%d').date())
                db.session.add(rec)
                existing[(eid, iso)] = rec
            rec.week_id = week.id
            rec.morning_present = bool(m.get('am'))
            rec.afternoon_present = bool(m.get('pm'))
            rec.marked_by = 'React'
            saved += 1
        db.session.commit()
        from utils.calculations import _invalidate_analytics_for_week
        _invalidate_analytics_for_week(week.id)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True, 'saved': saved})


@attendance_bp.route('/api/copy-previous', methods=['POST'])
@login_required
def api_copy_previous():
    """Copy the previous school day's marks into `date`. Body: {assignment_id, date}."""
    data = request.get_json(silent=True) or {}
    caa = db.session.get(ClassArmAssignment, data.get('assignment_id'))
    if not caa:
        return jsonify({'error': 'invalid assignment'}), 400
    require_branch_access(caa.branch_id)
    if not can_mark_attendance(caa.id):
        return jsonify({'error': 'forbidden'}), 403
    try:
        target = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except Exception:
        return jsonify({'error': 'bad date'}), 400
    week = _week_for_date(caa.term_id, target)
    if not week:
        return jsonify({'error': 'date not in any school week'}), 400
    holiday_dates = {h.date for h in Holiday.query.filter_by(term_id=caa.term_id).all()}
    prev, n = target - timedelta(days=1), 0
    while n < 10 and (prev.weekday() >= 5 or prev in holiday_dates):
        prev -= timedelta(days=1); n += 1
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=caa.id, is_active=True).all()
    prevmap = {a.enrollment_id: a for a in Attendance.query.filter(
        Attendance.enrollment_id.in_([e.id for e in enrollments] or [-1]),
        Attendance.date == prev).all()}
    if not prevmap:
        return jsonify({'ok': True, 'copied': 0, 'from': prev.isoformat(),
                        'note': 'No attendance on the previous school day.'})
    copied = 0
    try:
        for e in enrollments:
            p = prevmap.get(e.id)
            if not p:
                continue
            rec = Attendance.query.filter_by(enrollment_id=e.id, date=target).first()
            if rec:
                rec.morning_present, rec.afternoon_present = p.morning_present, p.afternoon_present
            else:
                db.session.add(Attendance(
                    enrollment_id=e.id, week_id=week.id, date=target,
                    morning_present=p.morning_present, afternoon_present=p.afternoon_present,
                    marked_by='React'))
            copied += 1
        db.session.commit()
        from utils.calculations import _invalidate_analytics_for_week
        _invalidate_analytics_for_week(week.id)
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    return jsonify({'ok': True, 'copied': copied, 'from': prev.isoformat()})


@attendance_bp.route('/api/daily-summary')
@login_required
def api_report_daily():
    """Daily attendance summary for one class arm on a date (JSON, read-only)."""
    caa, err = _scoped_caa(request.args.get('assignment_id', type=int))
    if err:
        return err
    ds = request.args.get('date')
    try:
        target = datetime.strptime(ds, '%Y-%m-%d').date() if ds else date.today()
    except Exception:
        return jsonify({'error': 'bad date'}), 400
    holidays = Holiday.query.filter_by(term_id=caa.term_id).all()
    hol = next((h for h in holidays if h.date == target), None)
    summary = get_daily_attendance_summary(caa.id, target)
    return jsonify({
        'class_name': caa.display_name,
        'school_day': is_school_day(target, holidays),
        'weekend': target.weekday() >= 5,
        'holiday': {'reason': hol.reason, 'type': hol.holiday_type} if hol else None,
        **_jsonable(summary),
    })


@attendance_bp.route('/api/report/week-totals')
@login_required
def api_week_totals():
    """Per-day attendance totals for the whole school week containing a date, so
    the daily summary can show every day at a glance instead of one at a time."""
    caa, err = _scoped_caa(request.args.get('assignment_id', type=int))
    if err:
        return err
    ds = request.args.get('date')
    try:
        on = datetime.strptime(ds, '%Y-%m-%d').date() if ds else date.today()
    except Exception:
        return jsonify({'error': 'bad date'}), 400
    weeks = Week.query.filter_by(term_id=caa.term_id).order_by(Week.week_number).all()
    week = pick_current_week(weeks, on=on)
    days = []
    if week:
        holiday_dates = {h.date for h in Holiday.query.filter_by(term_id=caa.term_id).all()}
        today = date.today()
        d = week.start_date
        while d <= week.end_date:
            if d.weekday() < 5 and d not in holiday_dates and d <= today:
                s = get_daily_attendance_summary(caa.id, d)
                days.append({
                    'date': d.isoformat(),
                    'total': s['total_students'],
                    'am_present': s['morning_present'], 'am_absent': s['morning_absent'],
                    'pm_present': s['afternoon_present'], 'pm_absent': s['afternoon_absent'],
                })
            d += timedelta(days=1)
    return jsonify({'week_number': week.week_number if week else None, 'days': days})


@attendance_bp.route('/api/report/weekly')
@login_required
def api_report_weekly():
    """Weekly attendance report (students × school-days + class totals)."""
    caa, err = _scoped_caa(request.args.get('assignment_id', type=int))
    if err:
        return err
    week = db.session.get(Week, request.args.get('week_id', type=int) or 0)
    if not week or week.term_id != caa.term_id:
        return jsonify({'error': 'week_id required'}), 400
    summary = get_weekly_attendance_summary(caa.id, week.id)
    if summary is None:
        return jsonify({'error': 'no data for week'}), 404
    return jsonify({'class_name': caa.display_name, **_jsonable(summary)})


@attendance_bp.route('/api/report/termly')
@login_required
def api_report_termly():
    """Termly attendance report (per-student weekly breakdown + class totals)."""
    caa, err = _scoped_caa(request.args.get('assignment_id', type=int))
    if err:
        return err
    summary = get_termly_attendance_summary(caa.id, caa.term_id)
    if summary is None:
        return jsonify({'error': 'no weeks defined for this term'}), 404
    # The summary embeds Week model objects under 'weeks'; replace with a
    # JSON-friendly shape before serialising.
    summary['weeks'] = [{'id': w.id, 'number': w.week_number} for w in summary['weeks']]
    return jsonify({'class_name': caa.display_name, **_jsonable(summary)})


@attendance_bp.route('/api/report/alerts')
@login_required
def api_report_alerts():
    """Students below an attendance threshold for a term, scoped to the classes
    the current user may access (JSON, read-only)."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    req_term = request.args.get('term_id', type=int)
    term = (db.session.get(Term, req_term) if req_term else None) or get_active_term()
    if not term:
        return jsonify({'error': 'no term'}), 400
    threshold = request.args.get('threshold', type=float)
    if threshold is None:
        threshold = 75.0

    # Only classes this user may see, within the term.
    classes = filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term.id).all(), form_only=True)
    class_by_id = {c.id: c for c in classes}

    weeks = Week.query.filter_by(term_id=term.id).all()
    week_ids = [w.id for w in weeks]
    holiday_dates = {h.date for h in Holiday.query.filter_by(term_id=term.id).all()}
    total_school_days = 0
    for week in weeks:
        current = week.start_date
        while current <= week.end_date:
            if current.weekday() < 5 and current not in holiday_dates:
                total_school_days += 1
            current += timedelta(days=1)
    total_times_opened = total_school_days * 2

    alerts = []
    if week_ids and total_times_opened > 0 and class_by_id:
        enrollments = (StudentEnrollment.query
                       .filter(StudentEnrollment.class_arm_assignment_id.in_(list(class_by_id)),
                               StudentEnrollment.is_active == True)  # noqa: E712
                       .all())
        present_by_enrollment = {}
        for a in Attendance.query.filter(
                Attendance.enrollment_id.in_([e.id for e in enrollments] or [-1]),
                Attendance.week_id.in_(week_ids)).all():
            present_by_enrollment[a.enrollment_id] = present_by_enrollment.get(a.enrollment_id, 0) \
                + (1 if a.morning_present else 0) + (1 if a.afternoon_present else 0)
        for e in enrollments:
            present = present_by_enrollment.get(e.id, 0)
            pct = round((present / total_times_opened) * 100, 2)
            if pct < threshold:
                alerts.append({
                    'id': e.student.id,
                    'student_id': e.student.student_id,
                    'student_name': e.student.full_name,
                    'class_name': class_by_id[e.class_arm_assignment_id].display_name,
                    'present': present,
                    'total': total_times_opened,
                    'percentage': pct,
                    'status': 'critical' if pct < 50 else 'warning',
                })
        alerts.sort(key=lambda x: x['percentage'])

    return jsonify({
        'term': {'id': term.id, 'name': term.full_name},
        'threshold': threshold,
        'total_times_opened': total_times_opened,
        'alerts': alerts,
    })


# ============================================================================
# STUDENT ATTENDANCE PROFILE (the definitive per-student attendance page)
# ============================================================================

def _can_view_student(student):
    """A viewer may open a student's attendance profile if they're an admin, or
    the student sits in a class the viewer may view (and shares their branch)."""
    from utils.access_control import is_admin
    if is_admin():
        return True
    from utils.branch_scope import can_access_branch
    if not can_access_branch(student.branch_id):
        return False
    for e in StudentEnrollment.query.filter_by(student_id=student.id).all():
        if can_view_attendance(e.class_arm_assignment_id):
            return True
    return False


@attendance_bp.route('/api/student/<int:student_id>')
@login_required
def api_student_profile(student_id):
    """Cross-term attendance profile for one student (JSON, read-only)."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'error': 'not found'}), 404
    if not _can_view_student(student):
        return jsonify({'error': 'forbidden'}), 403
    from utils.attendance_profile import build_student_profile
    data = build_student_profile(student_id, focus_term_id=request.args.get('term_id', type=int))
    if not data:
        return jsonify({'error': 'not found'}), 404
    from utils import attendance_notify as AN
    data['notifications'] = AN.student_notification_history(student_id)
    from utils import attendance_interventions as IV
    data['interventions'] = IV.student_interventions(student_id)
    data['active_term_id'] = (get_active_term().id if get_active_term() else None)
    return jsonify(data)


@attendance_bp.route('/api/analytics')
@login_required
def api_analytics():
    """Attendance analytics for a term over the classes the viewer may see."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    req_term = request.args.get('term_id', type=int)
    term = (db.session.get(Term, req_term) if req_term else None) or get_active_term()
    if not term:
        return jsonify({'error': 'no term'}), 400
    accessible = filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term.id).all(), form_only=True)
    from utils.branch_scope import is_central
    from utils import attendance_analytics as AA
    data = AA.build(term, accessible, is_central=is_central(),
                    use_cache=(request.args.get('nocache') != '1'))
    return jsonify(data)


@attendance_bp.route('/api/notify/absentees', methods=['POST'])
@login_required
def api_notify_absentees():
    """Draft a Communication campaign to the parents of students absent (both
    sessions) on a date, for one class. Never auto-sends."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    from utils import automations
    if not automations.is_enabled('attendance_absent_parent'):
        return jsonify({'ok': False, 'error': 'Absent-today parent notices are turned off in the Automation Center.'}), 400
    data = request.get_json(silent=True) or {}
    caa = db.session.get(ClassArmAssignment, data.get('assignment_id'))
    if not caa:
        return jsonify({'error': 'invalid assignment'}), 400
    require_branch_access(caa.branch_id)
    if not can_mark_attendance(caa.id):
        return jsonify({'error': 'forbidden'}), 403
    try:
        target = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except Exception:
        return jsonify({'error': 'bad date'}), 400
    from utils import attendance_notify as AN
    term = db.session.get(Term, caa.term_id)
    msg = AN.draft_absentee_notice(term, target, [caa.id],
                                   channel=data.get('channel'), created_by=_actor_name())
    if not msg:
        return jsonify({'ok': False, 'error': 'No absentees with a reachable parent for that day.'}), 400
    from utils.audit import log_action
    log_action('attendance.notify_absentees', detail=f'{caa.display_name} {target.isoformat()} ({msg.recipient_count})')
    return jsonify({'ok': True, 'message': f'Drafted a notice to {msg.recipient_count} parent(s).',
                    'redirect': url_for('comms.message_detail', message_id=msg.id)})


@attendance_bp.route('/api/notify/low', methods=['POST'])
@login_required
def api_notify_low():
    """Draft a Communication campaign to parents of students below the term
    attendance warning threshold, across the classes the user may access."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    from utils import automations
    if not automations.is_enabled('attendance_low_parent'):
        return jsonify({'ok': False, 'error': 'Low-attendance parent notices are turned off in the Automation Center.'}), 400
    data = request.get_json(silent=True) or {}
    term = (db.session.get(Term, data.get('term_id')) if data.get('term_id') else None) or get_active_term()
    if not term:
        return jsonify({'error': 'no term'}), 400
    accessible = filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term.id).all(), form_only=True)
    caa_ids = [c.id for c in accessible]
    from utils.attendance_profile import warning_threshold
    from utils import attendance_notify as AN
    msg = AN.draft_low_attendance_notice(term, caa_ids, warning_threshold(),
                                         channel=data.get('channel'), created_by=_actor_name())
    if not msg:
        return jsonify({'ok': False, 'error': 'No students below threshold with a reachable parent.'}), 400
    from utils.audit import log_action
    log_action('attendance.notify_low', detail=f'{term.name} ({msg.recipient_count})')
    return jsonify({'ok': True, 'message': f'Drafted a notice to {msg.recipient_count} parent(s).',
                    'redirect': url_for('comms.message_detail', message_id=msg.id)})


# ============================================================================
# INTERVENTION MANAGEMENT
# ============================================================================

def _intervention_or_403(iv_id):
    """Load an intervention the current user may act on (branch + class scope via
    the student's current-term class)."""
    from models import AttendanceIntervention
    iv = db.session.get(AttendanceIntervention, iv_id)
    if not iv:
        return None, (jsonify({'error': 'not found'}), 404)
    from utils.attendance_profile import build_student_profile  # noqa: F401 (ensure import ok)
    student = db.session.get(Student, iv.student_id)
    if not student or not _can_view_student(student):
        return None, (jsonify({'error': 'forbidden'}), 403)
    return iv, None


@attendance_bp.route('/api/interventions')
@login_required
def api_interventions():
    """Intervention dashboard for a term over the classes the user may view."""
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    req_term = request.args.get('term_id', type=int)
    term = (db.session.get(Term, req_term) if req_term else None) or get_active_term()
    if not term:
        return jsonify({'error': 'no term'}), 400
    accessible = filter_classes_for_user(
        ClassArmAssignment.query.filter_by(term_id=term.id).all(), form_only=True)
    from utils import attendance_interventions as IV
    return jsonify(IV.dashboard(term, [c.id for c in accessible]))


@attendance_bp.route('/api/interventions/open', methods=['POST'])
@login_required
def api_intervention_open():
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    student = db.session.get(Student, data.get('student_id'))
    if not student:
        return jsonify({'error': 'invalid student'}), 400
    if not _can_view_student(student):
        return jsonify({'error': 'forbidden'}), 403
    term = (db.session.get(Term, data.get('term_id')) if data.get('term_id') else None) or get_active_term()
    from utils import attendance_interventions as IV
    iv, created = IV.open_intervention(student.id, term,
                                       reason=(data.get('reason') or '').strip() or None,
                                       opened_by=_actor_name())
    if created:
        from utils.audit import log_action
        log_action('attendance.intervention_open', detail=student.full_name, target=iv)
    return jsonify({'ok': True, 'id': iv.id, 'created': created,
                    'message': 'Intervention opened.' if created else 'An open intervention already exists.'})


@attendance_bp.route('/api/interventions/<int:iv_id>/note', methods=['POST'])
@login_required
def api_intervention_note(iv_id):
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    iv, err = _intervention_or_403(iv_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    from utils import attendance_interventions as IV
    from models import InterventionNote
    kind = data.get('kind') if data.get('kind') in InterventionNote.KINDS else 'Note'
    nd = None
    if data.get('next_date'):
        try:
            nd = datetime.strptime(data['next_date'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            nd = None
    IV.add_note(iv, kind=kind, body=(data.get('body') or '').strip() or None,
                next_action=(data.get('next_action') or '').strip() or None,
                next_date=nd, author=_actor_name())
    return jsonify({'ok': True, 'message': 'Follow-up added.'})


@attendance_bp.route('/api/interventions/<int:iv_id>/status', methods=['POST'])
@login_required
def api_intervention_status(iv_id):
    if not can_access_module('attendance'):
        return jsonify({'error': 'forbidden'}), 403
    iv, err = _intervention_or_403(iv_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    from utils import attendance_interventions as IV
    if not IV.set_status(iv, data.get('status'), outcome=(data.get('outcome') or '').strip() or None):
        return jsonify({'ok': False, 'error': 'Invalid status.'}), 400
    from utils.audit import log_action
    log_action('attendance.intervention_status', detail=data.get('status'), target=iv)
    return jsonify({'ok': True, 'message': f'Intervention {(data.get("status") or "").lower()}.'})


@attendance_bp.route('/api/student-search')
@login_required
def api_student_search():
    """Type-ahead search for students the viewer may open a profile for."""
    if not can_access_module('attendance'):
        return jsonify([])
    from utils.access_control import is_admin
    from utils.search import like_term
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    like = like_term(q)
    query = Student.query.filter(Student.is_active == True,  # noqa: E712
                                 db.or_(Student.first_name.ilike(like, escape='\\'),
                                        Student.surname.ilike(like, escape='\\'),
                                        Student.student_id.ilike(like, escape='\\')))
    if not is_admin():
        # Restrict to students in classes the viewer may view.
        accessible = filter_classes_for_user(ClassArmAssignment.query.all(), form_only=True)
        caa_ids = [c.id for c in accessible]
        sub = (db.session.query(StudentEnrollment.student_id)
               .filter(StudentEnrollment.class_arm_assignment_id.in_(caa_ids or [-1])))
        query = query.filter(Student.id.in_(sub))
    else:
        from utils.branch_scope import scope_query
        query = scope_query(query, Student)
    rows = query.order_by(Student.surname, Student.first_name).limit(15).all()
    return jsonify([{'id': s.id, 'label': f'{s.full_name} ({s.student_id})',
                     'url': url_for('attendance.attendance_app') + f'?student_id={s.id}#/student'}
                    for s in rows])
