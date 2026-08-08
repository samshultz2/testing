"""attendance blueprint — marking routes (split from the former routes/attendance.py)."""
from routes.attendance import *  # noqa: F401,F403


@attendance_bp.route('/')
@login_required
def index():
    """Attendance main page"""
    # Get active term
    active_term = get_active_term()
    
    # Get all sessions and terms for selection
    sessions = AcademicSession.query.order_by(AcademicSession.name.desc()).all()
    
    return render_template('attendance/index.html',
        active_term=active_term,
        sessions=sessions
    )


@attendance_bp.route('/mark')
@login_required
def mark_attendance_page():
    """Page for marking daily attendance"""
    # Get parameters
    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    target_date = request.args.get('date')
    session_type = request.args.get('session', 'morning')
    
    # Check attendance permission
    if not can_mark_attendance():
        flash('You do not have permission to mark attendance.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Check class access if class is selected
    if assignment_id and not can_view_attendance(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('attendance.mark_attendance_page'))
    
    # Get active term if not specified
    if not term_id:
        active_term = get_active_term()
        if active_term:
            term_id = active_term.id
    
    # Get data for dropdowns
    terms = session_terms()
    
    assignments = []
    weeks = []
    holidays = []
    selected_term = None
    selected_assignment = None
    enrollments = []
    existing_attendance = {}
    current_week = None
    
    if term_id:
        selected_term = db.session.get(Term, term_id)
        all_assignments = ClassArmAssignment.query.filter_by(term_id=term_id).all()
        # Filter classes for teachers
        assignments = filter_classes_for_user(all_assignments, form_only=True)
        weeks = Week.query.filter_by(term_id=term_id).order_by(Week.week_number).all()
        holidays = Holiday.query.filter_by(term_id=term_id).all()

    # A form teacher lands on their own class without picking it.
    if not assignment_id:
        assignment_id = auto_select_assignment(assignments)

    if assignment_id:
        selected_assignment = db.session.get(ClassArmAssignment, assignment_id)
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).join(Student).order_by(*roster_order()).all()
    
    # Parse date
    if target_date:
        try:
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        except Exception:
            target_date = date.today()
    else:
        target_date = date.today()
    
    # Find which week this date belongs to
    if weeks:
        for week in weeks:
            if week.start_date <= target_date <= week.end_date:
                current_week = week
                break
    
    # Check if it's a school day, and if not, why (so the page can be specific).
    holiday_dates = set(h.date for h in holidays)
    is_valid_school_day = is_school_day(target_date, holidays)
    holiday_for_date = next((h for h in holidays if h.date == target_date), None)
    is_weekend = target_date.weekday() >= 5

    # Get existing attendance for this date — one batched query (was one per
    # enrollment: an N+1 that scaled with class size).
    if enrollments and target_date:
        rows = Attendance.query.filter(
            Attendance.enrollment_id.in_([e.id for e in enrollments]),
            Attendance.date == target_date,
        ).all()
        for att in rows:
            existing_attendance[att.enrollment_id] = {
                'morning': att.morning_present,
                'afternoon': att.afternoon_present,
            }
    
    return render_template('attendance/mark.html',
        terms=terms,
        selected_term=selected_term,
        assignments=assignments,
        selected_assignment=selected_assignment,
        enrollments=enrollments,
        target_date=target_date,
        session_type=session_type,
        existing_attendance=existing_attendance,
        current_week=current_week,
        is_valid_school_day=is_valid_school_day,
        holiday_for_date=holiday_for_date,
        is_weekend=is_weekend,
        holidays=holidays
    )


@attendance_bp.route('/mark/save', methods=['POST'])
@login_required
def save_attendance():
    """Save attendance for a session"""
    try:
        assignment_id = request.form.get('assignment_id', type=int)
        target_date = request.form.get('date')
        session_type = request.form.get('session_type')
        week_id = request.form.get('week_id', type=int)
        
        # Check access permission
        if not can_mark_attendance(assignment_id):
            flash('You do not have permission to mark attendance for this class.', 'error')
            return redirect(url_for('attendance.mark_attendance_page'))
        
        # Parse date
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

        # Reject future / out-of-term / non-school-day dates. The term comes from
        # the class assignment (authoritative), not the form.
        asg_for_date = db.session.get(ClassArmAssignment, assignment_id)
        date_err = _validate_attendance_date(
            target_date, asg_for_date.term_id if asg_for_date else None)
        if date_err:
            flash(date_err, 'error')
            return redirect(url_for('attendance.mark_attendance_page',
                term_id=request.form.get('term_id'), assignment_id=assignment_id,
                date=request.form.get('date')))

        # Get all enrollment IDs for this class
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).all()
        all_enrollment_ids = [e.id for e in enrollments]
        marked_by = _actor_name()
        # Audit register MODIFICATIONS (not routine first-time marking): a save
        # that overwrites already-recorded attendance, or any back-dated save —
        # both are the attendance-fraud vectors and need attribution.
        already_marked = bool(all_enrollment_ids) and (
            Attendance.query.filter(Attendance.enrollment_id.in_(all_enrollment_ids),
                                    Attendance.date == target_date).first() is not None)
        if target_date < date.today() or already_marked:
            from utils.audit import log_action
            kind = 'attendance.backdated' if target_date < date.today() else 'attendance.modified'
            log_action(kind, detail=f'class={assignment_id} date={target_date.isoformat()} '
                                    f'by={marked_by}')

        # Dual mode: separate Morning + Afternoon ticks on one save, so a student
        # can be present in the morning and absent in the afternoon (or vice versa).
        if request.form.get('mode') == 'dual':
            am_ids = {int(x) for x in request.form.getlist('am[]')}
            pm_ids = {int(x) for x in request.form.getlist('pm[]')}
            for en in enrollments:
                att = Attendance.query.filter_by(enrollment_id=en.id, date=target_date).first()
                if att is None:
                    att = Attendance(enrollment_id=en.id, date=target_date, week_id=week_id)
                    db.session.add(att)
                att.week_id = week_id
                att.morning_present = en.id in am_ids
                att.afternoon_present = en.id in pm_ids
                att.marked_by = marked_by
            db.session.commit()
            flash(f'Attendance saved for {len(enrollments)} students (Morning & Afternoon).', 'success')
            assignment = db.session.get(ClassArmAssignment, assignment_id)
            if assignment:
                from utils.notify import notify_attendance_marked
                notify_attendance_marked(
                    class_label=assignment.display_name,
                    date_label=target_date.strftime('%d %b %Y'), session_label='Full day',
                    present=len(am_ids & set(all_enrollment_ids)), total=len(all_enrollment_ids),
                    marked_by=marked_by,
                    url=url_for('attendance.daily_summary', assignment_id=assignment_id,
                                date=target_date.isoformat()))
            return redirect(url_for('attendance.mark_attendance_page',
                term_id=request.form.get('term_id'), assignment_id=assignment_id,
                date=request.form.get('date')))

        # Get IDs of students marked present (checked checkboxes)
        present_ids = [int(x) for x in request.form.getlist('present[]')]
        
        # Mark attendance
        # Check if auto-copy to afternoon is enabled (default True for morning)
        auto_copy = request.form.get('auto_copy_afternoon', 'on') == 'on'

        count = mark_attendance_bulk(
            all_enrollment_ids,
            target_date,
            week_id,
            session_type,
            present_ids,
            marked_by=marked_by,
            auto_copy_to_afternoon=auto_copy if session_type == 'morning' else False
        )

        if session_type == 'morning' and auto_copy:
            flash(f'Attendance saved for {count} students! (Morning & Afternoon)', 'success')
        else:
            flash(f'Attendance saved for {count} students!', 'success')

        # Bell admins that this class register was taken.
        assignment = db.session.get(ClassArmAssignment, assignment_id)
        if assignment:
            from utils.notify import notify_attendance_marked
            notify_attendance_marked(
                class_label=assignment.display_name,
                date_label=target_date.strftime('%d %b %Y'),
                session_label=(session_type or '').capitalize(),
                present=len(present_ids), total=len(all_enrollment_ids),
                marked_by=marked_by,
                url=url_for('attendance.daily_summary', assignment_id=assignment_id,
                            date=target_date.isoformat()))

    except Exception as e:
        db.session.rollback()
        flash(f'Error saving attendance: {str(e)}', 'error')
    
    return redirect(url_for('attendance.mark_attendance_page',
        term_id=request.form.get('term_id'),
        assignment_id=assignment_id,
        date=request.form.get('date'),
        session=session_type
    ))


@attendance_bp.route('/week')
@login_required
def week_grid():
    """Mark a whole week at once: a students × school-days grid (backlog-friendly)."""
    if not can_mark_attendance():
        flash('You do not have permission to mark attendance.', 'error')
        return redirect(url_for('main.dashboard'))

    term_id = request.args.get('term_id', type=int)
    assignment_id = request.args.get('assignment_id', type=int)
    week_id = request.args.get('week_id', type=int)
    split = request.args.get('sessions') == 'split'

    if not term_id:
        active = get_active_term()
        term_id = active.id if active else None

    terms = session_terms()
    selected_term = db.session.get(Term, term_id) if term_id else None
    assignments, weeks, holidays = [], [], []
    if term_id:
        assignments = filter_classes_for_user(
            ClassArmAssignment.query.filter_by(term_id=term_id).all(), form_only=True)
        weeks = Week.query.filter_by(term_id=term_id).order_by(Week.week_number).all()
        holidays = Holiday.query.filter_by(term_id=term_id).all()

    if assignment_id and not can_view_attendance(assignment_id):
        flash('You do not have access to this class.', 'error')
        return redirect(url_for('attendance.week_grid'))

    # Default to the form teacher's class and the current week.
    if not assignment_id:
        assignment_id = auto_select_assignment(assignments)
    selected_assignment = db.session.get(ClassArmAssignment, assignment_id) if assignment_id else None
    selected_week = db.session.get(Week, week_id) if week_id else pick_current_week(weeks)

    enrollments, school_days, existing = [], [], {}
    if selected_assignment and selected_week:
        enrollments = (StudentEnrollment.query
                       .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                       .join(Student).order_by(*roster_order()).all())
        school_days = _week_school_days(selected_week, holidays)
        if enrollments and school_days:
            recs = Attendance.query.filter(
                Attendance.enrollment_id.in_([e.id for e in enrollments]),
                Attendance.date.in_(school_days)).all()
            # existing[enrollment_id][iso_date] = (morning_present, afternoon_present)
            for r in recs:
                existing.setdefault(r.enrollment_id, {})[r.date.isoformat()] = (
                    bool(r.morning_present), bool(r.afternoon_present))

    return render_template('attendance/week.html',
        terms=terms, selected_term=selected_term, assignments=assignments,
        selected_assignment=selected_assignment, weeks=weeks, split=split,
        selected_week=selected_week, enrollments=enrollments,
        school_days=school_days, existing=existing)


@attendance_bp.route('/week/save', methods=['POST'])
@login_required
def week_save():
    """Batch-save a whole week's attendance from the grid (one transaction)."""
    assignment_id = request.form.get('assignment_id', type=int)
    week_id = request.form.get('week_id', type=int)
    term_id = request.form.get('term_id', type=int)
    if not can_mark_attendance(assignment_id):
        flash('You do not have permission to mark attendance for this class.', 'error')
        return redirect(url_for('attendance.week_grid'))

    week = db.session.get(Week, week_id)
    if not week:
        flash('Select a week first.', 'error')
        return redirect(url_for('attendance.week_grid', term_id=term_id, assignment_id=assignment_id))

    holidays = Holiday.query.filter_by(term_id=week.term_id).all()
    school_days = _week_school_days(week, holidays)
    enrollments = StudentEnrollment.query.filter_by(
        class_arm_assignment_id=assignment_id, is_active=True).all()
    day_isos = [d.isoformat() for d in school_days]

    # Existing records keyed by (enrollment_id, date) so we upsert.
    existing = {(r.enrollment_id, r.date): r for r in Attendance.query.filter(
        Attendance.enrollment_id.in_([e.id for e in enrollments]),
        Attendance.date.in_(school_days)).all()}

    marked_by = request.form.get('marked_by') or _actor_name()
    split = request.form.get('sessions') == 'split'   # AM/PM ticks vs whole-day
    saved = 0
    try:
        for e in enrollments:
            for d, iso in zip(school_days, day_isos):
                if split:
                    morning = request.form.get(f'am_{e.id}_{iso}') == 'on'
                    afternoon = request.form.get(f'pm_{e.id}_{iso}') == 'on'
                else:
                    morning = afternoon = request.form.get(f'p_{e.id}_{iso}') == 'on'
                rec = existing.get((e.id, d))
                if rec is None:
                    rec = Attendance(enrollment_id=e.id, week_id=week.id, date=d)
                    db.session.add(rec)
                rec.week_id = week.id
                rec.morning_present = morning
                rec.afternoon_present = afternoon
                rec.marked_by = marked_by
                saved += 1
        db.session.commit()
        from utils.attendance_alerts import check_absence_alerts
        check_absence_alerts([e.id for e in enrollments])   # bell admins on long absences
        flash(f'Saved attendance for {len(enrollments)} student(s) across '
              f'{len(school_days)} day(s) of {week.week_number and "Week %d" % week.week_number}.',
              'success')
        assignment = db.session.get(ClassArmAssignment, assignment_id)
        if assignment:
            from utils.notify import notify_attendance_marked
            notify_attendance_marked(
                class_label=assignment.display_name,
                date_label=(f'Week {week.week_number}' if week.week_number else ''),
                present=None, total=None, marked_by=marked_by,
                url=url_for('attendance.week_grid', term_id=term_id, assignment_id=assignment_id))
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving attendance: {str(e)}', 'error')

    return redirect(url_for('attendance.week_grid',
        term_id=term_id, assignment_id=assignment_id, week_id=week_id))


@attendance_bp.route('/mark/all-present', methods=['POST'])
@login_required
def mark_all_present_route():
    """Mark all students as present for a session"""
    try:
        assignment_id = request.form.get('assignment_id', type=int)
        target_date = request.form.get('date')
        session_type = request.form.get('session_type')
        week_id = request.form.get('week_id', type=int)

        if not assignment_id or not can_mark_attendance(assignment_id):
            flash('You do not have permission to mark attendance for this class.', 'error')
            return redirect(url_for('attendance.mark_attendance_page'))

        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).all()
        enrollment_ids = [e.id for e in enrollments]
        
        count = mark_all_present(enrollment_ids, target_date, week_id, session_type)

        flash(f'All {count} students marked as present!', 'success')

        assignment = db.session.get(ClassArmAssignment, assignment_id)
        if assignment:
            from utils.notify import notify_attendance_marked
            notify_attendance_marked(
                class_label=assignment.display_name,
                date_label=target_date.strftime('%d %b %Y'),
                session_label=(session_type or '').capitalize(),
                present=count, total=len(enrollment_ids), marked_by=_actor_name(),
                url=url_for('attendance.daily_summary', assignment_id=assignment_id,
                            date=target_date.isoformat()))

    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('attendance.mark_attendance_page',
        term_id=request.form.get('term_id'),
        assignment_id=assignment_id,
        date=request.form.get('date'),
        session=session_type
    ))


@attendance_bp.route('/copy-previous', methods=['POST'])
@login_required
def copy_previous_attendance():
    """Copy attendance from previous school day"""
    try:
        assignment_id = request.form.get('assignment_id', type=int)
        target_date_str = request.form.get('date')
        term_id = request.form.get('term_id', type=int)

        if not assignment_id or not can_mark_attendance(assignment_id):
            flash('You do not have permission to mark attendance for this class.', 'error')
            return redirect(url_for('attendance.mark_attendance_page'))

        target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        
        # Find previous school day
        holidays = Holiday.query.filter_by(term_id=term_id).all()
        holiday_dates = set(h.date for h in holidays)
        
        prev_date = target_date - timedelta(days=1)
        attempts = 0
        while attempts < 10:
            if prev_date.weekday() < 5 and prev_date not in holiday_dates:
                break
            prev_date -= timedelta(days=1)
            attempts += 1
        
        if attempts >= 10:
            flash('Could not find a previous school day.', 'error')
            return redirect(url_for('attendance.mark_attendance_page',
                term_id=term_id, assignment_id=assignment_id, date=target_date_str))
        
        # Get previous day's attendance
        enrollments = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=assignment_id,
            is_active=True
        ).all()
        
        prev_attendance = {}
        for enrollment in enrollments:
            att = Attendance.query.filter_by(
                enrollment_id=enrollment.id,
                date=prev_date
            ).first()
            if att:
                prev_attendance[enrollment.id] = att
        
        if not prev_attendance:
            flash(f'No attendance found for {prev_date.strftime("%d %b %Y")}.', 'warning')
            return redirect(url_for('attendance.mark_attendance_page',
                term_id=term_id, assignment_id=assignment_id, date=target_date_str))
        
        # Get or find week for target date
        week = Week.query.filter(
            Week.term_id == term_id,
            Week.start_date <= target_date,
            Week.end_date >= target_date
        ).first()
        
        if not week:
            flash('Target date is not within any defined week.', 'error')
            return redirect(url_for('attendance.mark_attendance_page',
                term_id=term_id, assignment_id=assignment_id, date=target_date_str))
        
        # Copy attendance
        copied = 0
        for enrollment in enrollments:
            prev = prev_attendance.get(enrollment.id)
            if prev:
                existing = Attendance.query.filter_by(
                    enrollment_id=enrollment.id,
                    date=target_date
                ).first()
                
                if existing:
                    existing.morning_present = prev.morning_present
                    existing.afternoon_present = prev.afternoon_present
                else:
                    new_att = Attendance(
                        enrollment_id=enrollment.id,
                        week_id=week.id,
                        date=target_date,
                        morning_present=prev.morning_present,
                        afternoon_present=prev.afternoon_present
                    )
                    db.session.add(new_att)
                copied += 1
        
        db.session.commit()
        flash(f'Copied attendance from {prev_date.strftime("%d %b")} for {copied} students!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('attendance.mark_attendance_page',
        term_id=term_id, assignment_id=assignment_id, date=target_date_str))
