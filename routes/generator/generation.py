"""generator_bp — generation routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/assignments')
@login_required
def teacher_assignments():
    level = get_current_level()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()
    teachers = GenTeacher.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenTeacher.name).all()
    
    # Get subjects for this level
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    
    assignments_by_class = {}
    for cc in classes:
        assignments_by_class[cc.id] = GenTeacherAssignment.query.filter_by(
            class_config_id=cc.id, is_active=True
        ).all()
    return render_template('generator/teacher_assignments.html',
        classes=classes, teachers=teachers, subjects=subjects,
        assignments_by_class=assignments_by_class, level=level
    )


@generator_bp.route('/assignments/add', methods=['POST'])
@login_required
def add_teacher_assignment():
    try:
        teacher_id = request.form.get('teacher_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        class_config_id = request.form.get('class_config_id', type=int)
        arm_name = request.form.get('arm_name', '').strip() or None
        
        if not all([teacher_id, subject_id, class_config_id]):
            flash('Teacher, subject, and class are required.', 'error')
            return redirect(url_for('generator.teacher_assignments'))
        
        if GenTeacherAssignment.query.filter_by(
            teacher_id=teacher_id, subject_id=subject_id,
            class_config_id=class_config_id, arm_name=arm_name, is_active=True
        ).first():
            flash('Assignment exists.', 'warning')
            return redirect(url_for('generator.teacher_assignments'))
        
        db.session.add(GenTeacherAssignment(
            teacher_id=teacher_id, subject_id=subject_id,
            class_config_id=class_config_id, arm_name=arm_name, branch_id=gen_bid()
        ))
        db.session.commit()
        flash('Teacher assignment added!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.teacher_assignments'))


@generator_bp.route('/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_teacher_assignment(assignment_id):
    assignment = gen_owned_or_404(GenTeacherAssignment, assignment_id)
    try:
        assignment.is_active = False
        db.session.commit()
        flash('Assignment removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.teacher_assignments'))


@generator_bp.route('/generate')
@login_required
def generate_page():
    level = get_current_level()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
    
    # Validation
    issues = []
    if GenTeacher.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).count() == 0:
        issues.append({'type': 'error', 'msg': 'No teachers configured'})
    if GenSubjectConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).count() == 0:
        issues.append({'type': 'error', 'msg': 'No subjects configured'})
    if not classes:
        issues.append({'type': 'error', 'msg': 'No classes configured'})
    
    # Check for assignments
    assignment_count = GenTeacherAssignment.query.join(GenClassConfig).filter(
        GenTeacherAssignment.is_active == True,
        GenTeacherAssignment.branch_id == gen_bid(),
        GenClassConfig.school_level == level
    ).count()
    if assignment_count == 0:
        issues.append({'type': 'error', 'msg': 'No teacher assignments'})
    
    # Check subjects without teachers
    for config in GenSubjectConfig.query.filter_by(is_active=True, school_level=level, category='core', branch_id=gen_bid()).all():
        if not GenTeacherAssignment.query.join(GenClassConfig).filter(
            GenTeacherAssignment.subject_id == config.subject_id,
            GenTeacherAssignment.is_active == True,
            GenTeacherAssignment.branch_id == gen_bid(),
            GenClassConfig.school_level == level
        ).first():
            subj_name = config.subject.name if config.subject else f'Subject {config.subject_id}'
            issues.append({'type': 'warning', 'msg': f'{subj_name} has no teacher'})
    
    return render_template('generator/generate.html',
        classes=classes, rules=rules, issues=issues[:15], level=level,
        teachers_count=GenTeacher.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).count(),
        subjects_count=GenSubjectConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).count(),
        assignments_count=assignment_count
    )


@generator_bp.route('/generate/run', methods=['POST'])
@login_required
@timetable_generate_required
def run_generation():
    """Generate timetable using global scheduling approach"""
    # The chosen engine must come from the submitted form field, not from which URL
    # the client JS happened to post to. If JS didn't swap the form action (stale
    # service-worker cache, a JS error, CSP) the form posts here with method=ortools
    # selected — honour it server-side instead of silently running the fast method.
    if request.form.get('method') == 'ortools':
        return run_ortools_generation()
    level = get_current_level()
    try:
        class_ids = [int(x) for x in request.form.getlist('class_ids[]') if x]
        if not class_ids:
            flash('Select at least one class.', 'error')
            return redirect(url_for('generator.generate_page'))
        
        rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
        periods_per_day = int(rules.get('periods_per_day', 8))
        break_after = int(rules.get('break_after_period', 5))
        
        # Use global generation
        from routes.generator_global import run_global_generation
        
        result = run_global_generation(class_ids, periods_per_day, break_after, num_attempts=25)
        
        # Save results
        batch_id = str(uuid.uuid4())[:8]
        
        # NOTE: previous batches are intentionally kept (each generation is its
        # own saved batch under a new batch_id), so a timetable already in use is
        # never wiped by a regeneration and can always be re-applied.

        # Save new results
        for (class_name, arm), days in result['timetables'].items():
            for day, periods in days.items():
                for period, entry in periods.items():
                    if entry:
                        db.session.add(GenTimetableResult(
                            batch_id=batch_id,
                            branch_id=gen_bid(),
                            school_level=level,
                            class_name=class_name,
                            arm_name=arm,
                            day_of_week=day,
                            period_number=period,
                            subject_id=entry.get('subject_id'),
                            teacher_id=entry.get('teacher_id'),
                            is_double_period=entry.get('is_double', False)
                        ))
        
        db.session.commit()
        
        empty = result['empty_count']
        total = result['total_slots']
        filled_pct = ((total - empty) / total) * 100 if total > 0 else 0
        
        if empty > 0:
            flash(f'Generated {len(result["class_arms"])} timetables. {empty} empty slots ({filled_pct:.1f}% filled).', 'warning')
        else:
            flash(f'Successfully generated {len(result["class_arms"])} timetables with 100% slots filled!', 'success')
        
        return redirect(url_for('generator.view_results', batch_id=batch_id))
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('generator.generate_page'))


@generator_bp.route('/generate/ortools', methods=['POST'])
@login_required
@timetable_generate_required
def run_ortools_generation():
    """Generate timetable using OR-Tools constraint programming solver (optimal)"""
    try:
        class_ids = [int(x) for x in request.form.getlist('class_ids[]') if x]
        if not class_ids:
            flash('Select at least one class.', 'error')
            return redirect(url_for('generator.generate_page'))
        
        # Check if OR-Tools is available
        from routes.generator_ortools import check_ortools_available, generate_with_ortools, save_ortools_result
        
        if not check_ortools_available():
            flash('OR-Tools not installed. Run: pip install ortools --break-system-packages', 'error')
            return redirect(url_for('generator.generate_page'))
        
        rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
        periods_per_day = int(rules.get('periods_per_day', 8))
        
        # Get time limit from form, but clamp to the configured ceiling so a
        # solve can't outrun the gunicorn worker timeout and stall the app.
        from config import Config
        _cap = getattr(Config, 'SOLVER_MAX_SECONDS', 90)
        time_limit = max(5, min(int(request.form.get('time_limit', _cap)), _cap))
        
        # Run OR-Tools solver
        # Get break_after from rules
        break_after = int(rules.get('break_after_period', 5))
        
        # Run OR-Tools solver
        result = generate_with_ortools(class_ids, periods_per_day, time_limit, break_after)
        
        if not result['success']:
            flash(f'Generation failed: {result["message"]}', 'error')
            return redirect(url_for('generator.generate_page'))
        
        # Save results
        batch_id = save_ortools_result(result)
        
        empty = result['empty_count']
        assigned = result['assigned_count']
        total = result['total_requirements']
        total_slots = len(result['class_arms']) * 40
        filled_pct = ((total_slots - empty) / total_slots) * 100 if total_slots > 0 else 0
        
        if empty > 0:
            flash(f'OR-Tools: Assigned {assigned}/{total} requirements. {empty} empty slots ({filled_pct:.1f}% filled).', 'warning')
        else:
            flash(f'OR-Tools: Perfect! Assigned all {assigned} requirements with 100% slots filled!', 'success')
        
        return redirect(url_for('generator.view_results', batch_id=batch_id))
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('generator.generate_page'))


@generator_bp.route('/results')
@login_required
def results_list():
    level = get_current_level()
    batches = db.session.query(
        GenTimetableResult.batch_id,
        db.func.min(GenTimetableResult.generated_at).label('generated_at'),
        db.func.count(db.distinct(GenTimetableResult.class_name + GenTimetableResult.arm_name)).label('class_count')
    ).filter(GenTimetableResult.school_level == level, GenTimetableResult.branch_id == gen_bid()).group_by(GenTimetableResult.batch_id).order_by(db.desc('generated_at')).all()
    from models import ActiveTimetableBatch
    from utils.branch_scope import viewing_branch_id
    from utils.access_control import can_generate_timetable
    active_batch_id = ActiveTimetableBatch.active_batch_id(viewing_branch_id(), level)
    return render_template('generator/results_list.html', batches=batches, level=level,
                           active_batch_id=active_batch_id, can_publish=can_generate_timetable())


@generator_bp.route('/results/<batch_id>')
@login_required
def view_results(batch_id):
    level = get_current_level()
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, school_level=level, branch_id=gen_bid()).all()
    if not results:
        flash('No results found.', 'error')
        return redirect(url_for('generator.results_list'))
    
    timetables = {}
    for r in results:
        key = f"{r.class_name}_{r.arm_name}"
        if key not in timetables:
            timetables[key] = {'class_name': r.class_name, 'arm_name': r.arm_name, 'grid': {d: {} for d in range(5)}}
        timetables[key]['grid'][r.day_of_week][r.period_number] = r
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
    
    return render_template('generator/view_results.html',
        batch_id=batch_id, timetables=dict(sorted(timetables.items())),
        periods_per_day=int(rules.get('periods_per_day', 8)),
        break_after_period=int(rules.get('break_after_period', 4)),
        days=DAYS_OF_WEEK, level=level
    )


@generator_bp.route('/results/<batch_id>/apply', methods=['POST'])
@timetable_generate_required
def apply_results(batch_id):
    """Publish a generated batch into the per-class timetables for the active term."""
    applied, msg, cat = _apply_batch(batch_id)
    flash(msg, cat)
    return redirect(url_for('generator.view_results', batch_id=batch_id))


@generator_bp.route('/results/<batch_id>/set-in-use', methods=['POST'])
@timetable_generate_required
def set_in_use(batch_id):
    """Publish a batch live AND mark it the timetable currently 'in use' for this
    branch + school level (one in-use batch per branch/level)."""
    from models import ActiveTimetableBatch
    from utils.branch_scope import viewing_branch_id
    from utils.access_control import get_current_user
    applied, msg, cat = _apply_batch(batch_id)
    if applied:
        user = get_current_user()
        ActiveTimetableBatch.set_active(viewing_branch_id(), get_current_level(),
                                        batch_id, user.id if user else None)
        db.session.commit()
    flash(msg, cat)
    return redirect(url_for('generator.results_list'))


@generator_bp.route('/results/<batch_id>/edit/<class_name>/<arm_name>')
@login_required
def edit_timetable(batch_id, class_name, arm_name):
    level = get_current_level()
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, class_name=class_name, arm_name=arm_name, school_level=level, branch_id=gen_bid()).all()
    grid = {d: {} for d in range(5)}
    for r in results:
        grid[r.day_of_week][r.period_number] = r
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
    
    # Get subjects for this level
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    
    teachers = GenTeacher.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenTeacher.name).all()
    
    return render_template('generator/edit_timetable.html',
        batch_id=batch_id, class_name=class_name, arm_name=arm_name, grid=grid,
        periods_per_day=int(rules.get('periods_per_day', 8)),
        break_after_period=int(rules.get('break_after_period', 4)),
        days=DAYS_OF_WEEK, subjects=subjects, teachers=teachers, level=level
    )


@generator_bp.route('/results/<batch_id>/edit/<class_name>/<arm_name>/save', methods=['POST'])
@login_required
def save_timetable_edit(batch_id, class_name, arm_name):
    level = get_current_level()
    try:
        rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
        periods_per_day = int(rules.get('periods_per_day', 8))
        break_after = int(rules.get('break_after_period', 4))
        
        for day in range(5):
            for period in range(1, periods_per_day + 1):
                if period == break_after:
                    continue
                
                subject_id = request.form.get(f'subject_{day}_{period}', type=int)
                teacher_id = request.form.get(f'teacher_{day}_{period}', type=int)
                is_locked = request.form.get(f'locked_{day}_{period}') == 'on'
                
                existing = GenTimetableResult.query.filter_by(
                    batch_id=batch_id, class_name=class_name, arm_name=arm_name,
                    day_of_week=day, period_number=period, school_level=level, branch_id=gen_bid()
                ).first()
                
                if subject_id:
                    if existing:
                        existing.subject_id = subject_id
                        existing.teacher_id = teacher_id
                        existing.is_locked = is_locked
                    else:
                        db.session.add(GenTimetableResult(
                            batch_id=batch_id, branch_id=gen_bid(), class_name=class_name, arm_name=arm_name,
                            day_of_week=day, period_number=period, school_level=level,
                            subject_id=subject_id, teacher_id=teacher_id, is_locked=is_locked
                        ))
                elif existing:
                    db.session.delete(existing)
        
        db.session.commit()
        flash('Timetable updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.view_results', batch_id=batch_id))


@generator_bp.route('/results/<batch_id>/delete', methods=['POST'])
@login_required
def delete_results(batch_id):
    try:
        GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).delete()
        db.session.commit()
        flash('Deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.results_list'))


@generator_bp.route('/reports')
@login_required
def reports_index():
    latest = GenTimetableResult.query.filter_by(branch_id=gen_bid()).order_by(GenTimetableResult.generated_at.desc()).first()
    return render_template('generator/reports_index.html', latest_batch=latest)


@generator_bp.route('/reports/period-count/<batch_id>')
@login_required
def period_count_report(batch_id):
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    counts = {}
    for r in results:
        key = f"{r.class_name} {r.arm_name}"
        if key not in counts:
            counts[key] = {}
        if r.subject_id:
            counts[key][r.subject_id] = counts[key].get(r.subject_id, 0) + 1
    
    level = get_current_level()
    configs = {c.subject_id: c for c in GenSubjectConfig.query.filter_by(school_level=level, branch_id=gen_bid()).all()}
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    
    return render_template('generator/report_period_count.html',
        batch_id=batch_id, counts=counts, configs=configs, subjects=subjects
    )


@generator_bp.route('/reports/teacher-workload/<batch_id>')
@login_required
def teacher_workload_report(batch_id):
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    workload = {}
    for r in results:
        if r.teacher_id:
            if r.teacher_id not in workload:
                workload[r.teacher_id] = {
                    'teacher': r.teacher, 'total': 0,
                    'per_day': {d: 0 for d in range(5)}, 'classes': set()
                }
            workload[r.teacher_id]['total'] += 1
            workload[r.teacher_id]['per_day'][r.day_of_week] += 1
            workload[r.teacher_id]['classes'].add(f"{r.class_name} {r.arm_name}")
    
    return render_template('generator/report_teacher_workload.html',
        batch_id=batch_id, workload=workload, days=DAYS_OF_WEEK
    )


@generator_bp.route('/reports/clashes/<batch_id>')
@login_required
def clash_report(batch_id):
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    teacher_slots = {}
    for r in results:
        if r.teacher_id:
            if r.teacher_id not in teacher_slots:
                teacher_slots[r.teacher_id] = {}
            key = (r.day_of_week, r.period_number)
            if key not in teacher_slots[r.teacher_id]:
                teacher_slots[r.teacher_id][key] = []
            teacher_slots[r.teacher_id][key].append({
                'class': f"{r.class_name} {r.arm_name}",
                'subject': r.subject.name if r.subject else '-'
            })
    
    clashes = []
    for tid, slots in teacher_slots.items():
        teacher = GenTeacher.query.get(tid)
        for (day, period), entries in slots.items():
            if len(entries) > 1:
                clashes.append({
                    'teacher': teacher, 'day': DAYS_OF_WEEK[day],
                    'period': period, 'entries': entries
                })
    
    return render_template('generator/report_clashes.html', batch_id=batch_id, clashes=clashes)


@generator_bp.route('/reports/unassigned/<batch_id>')
@login_required
def unassigned_report(batch_id):
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    break_after = int(rules.get('break_after_period', 4))
    
    results = GenTimetableResult.query.filter_by(batch_id=batch_id, branch_id=gen_bid()).all()
    class_arms = set((r.class_name, r.arm_name) for r in results)
    
    empty = []
    for cn, an in class_arms:
        filled = {(r.day_of_week, r.period_number) for r in results if r.class_name == cn and r.arm_name == an}
        for day in range(5):
            for period in range(1, periods_per_day + 1):
                if period != break_after and (day, period) not in filled:
                    empty.append({'class': cn, 'arm': an, 'day': DAYS_OF_WEEK[day], 'period': period})
    
    return render_template('generator/report_unassigned.html', batch_id=batch_id, empty_slots=empty)


@generator_bp.route('/teacher-timetable')
@generator_bp.route('/teacher-timetable')
@login_required
def teacher_timetable():
    """View individual teacher's timetable with workload breakdown"""
    from collections import defaultdict
    
    teacher_id = request.args.get('teacher_id', type=int)
    batch_id = request.args.get('batch_id')
    
    teachers = GenTeacher.query.filter_by(is_active=True, branch_id=gen_bid()).order_by(GenTeacher.name).all()
    
    if not batch_id:
        latest = GenTimetableResult.query.filter_by(branch_id=gen_bid()).order_by(GenTimetableResult.generated_at.desc()).first()
        if latest:
            batch_id = latest.batch_id
    
    batches = db.session.query(
        GenTimetableResult.batch_id,
        db.func.min(GenTimetableResult.generated_at).label('generated_at')
    ).filter(GenTimetableResult.branch_id == gen_bid()).group_by(GenTimetableResult.batch_id).order_by(db.desc('generated_at')).all()
    
    teacher_grid = None
    selected_teacher = None
    total_periods = 0
    breakdown = {
        'by_subject': {},
        'by_class': {},
        'by_class_arm': {},
        'by_day': {},
        'by_stream': {},
        'details': []
    }
    
    if teacher_id and batch_id:
        selected_teacher = GenTeacher.query.get(teacher_id)
        results = GenTimetableResult.query.filter_by(batch_id=batch_id, teacher_id=teacher_id, branch_id=gen_bid()).all()
        
        rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
        teacher_grid = {d: {} for d in range(5)}
        
        # For breakdown statistics
        by_subject = defaultdict(int)
        by_class = defaultdict(int)
        by_class_arm = defaultdict(int)
        by_day = defaultdict(int)
        by_stream = defaultdict(int)
        class_arm_subject_periods = defaultdict(int)
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        
        for r in results:
            teacher_grid[r.day_of_week][r.period_number] = r
            total_periods += 1
            
            subject_name = r.subject.name if r.subject else 'Unknown'
            class_name = r.class_name
            arm_name = r.arm_name
            class_arm = f"{class_name} {arm_name}"
            
            # Count by different categories
            by_subject[subject_name] += 1
            by_class[class_name] += 1
            by_class_arm[class_arm] += 1
            by_day[day_names[r.day_of_week]] += 1
            
            # Track for detailed breakdown
            class_arm_subject_periods[(class_name, arm_name, subject_name)] += 1
            
            # Get stream for this class-arm
            class_config = GenClassConfig.query.filter_by(class_name=class_name, branch_id=gen_bid()).first()
            if class_config and class_config.has_streams:
                arm_stream = GenClassArmStream.query.filter_by(
                    class_config_id=class_config.id, 
                    arm_name=arm_name
                ).first()
                if arm_stream and arm_stream.stream:
                    by_stream[arm_stream.stream.name] += 1
        
        # Build detailed breakdown list
        for (class_name, arm_name, subject_name), periods in sorted(class_arm_subject_periods.items()):
            stream_name = '-'
            class_config = GenClassConfig.query.filter_by(class_name=class_name, branch_id=gen_bid()).first()
            if class_config and class_config.has_streams:
                arm_stream = GenClassArmStream.query.filter_by(
                    class_config_id=class_config.id, 
                    arm_name=arm_name
                ).first()
                if arm_stream and arm_stream.stream:
                    stream_name = arm_stream.stream.name
            
            breakdown['details'].append({
                'class': class_name,
                'arm': arm_name,
                'subject': subject_name,
                'stream': stream_name,
                'periods': periods
            })
        
        # Convert to regular dicts
        breakdown['by_subject'] = dict(by_subject)
        breakdown['by_class'] = dict(by_class)
        breakdown['by_class_arm'] = dict(by_class_arm)
        breakdown['by_day'] = dict(by_day)
        breakdown['by_stream'] = dict(by_stream)
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
    
    return render_template('generator/teacher_timetable.html',
        teachers=teachers, teacher_id=teacher_id, selected_teacher=selected_teacher,
        batches=batches, batch_id=batch_id, teacher_grid=teacher_grid,
        total_periods=total_periods,
        breakdown=breakdown,
        periods_per_day=int(rules.get('periods_per_day', 8)),
        break_after_period=int(rules.get('break_after_period', 4)),
        days=DAYS_OF_WEEK
    )


@generator_bp.route('/master-timetable')
@login_required
def master_timetable():
    batch_id = request.args.get('batch_id')
    selected_day = request.args.get('day', type=int, default=0)
    selected_period = request.args.get('period', type=int, default=1)
    
    if not batch_id:
        latest = GenTimetableResult.query.filter_by(branch_id=gen_bid()).order_by(GenTimetableResult.generated_at.desc()).first()
        if latest:
            batch_id = latest.batch_id
    
    batches = db.session.query(
        GenTimetableResult.batch_id,
        db.func.min(GenTimetableResult.generated_at).label('generated_at')
    ).filter(GenTimetableResult.branch_id == gen_bid()).group_by(GenTimetableResult.batch_id).order_by(db.desc('generated_at')).all()
    
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, branch_id=gen_bid()).all()}
    
    master_data = []
    if batch_id:
        results = GenTimetableResult.query.filter_by(
            batch_id=batch_id, day_of_week=selected_day, period_number=selected_period, branch_id=gen_bid()
        ).order_by(GenTimetableResult.class_name, GenTimetableResult.arm_name).all()
        
        for r in results:
            master_data.append({
                'class_name': r.class_name, 'arm_name': r.arm_name,
                'subject': r.subject.name if r.subject else '-',
                'teacher': r.teacher.name if r.teacher else '-'
            })
    
    return render_template('generator/master_timetable.html',
        batches=batches, batch_id=batch_id,
        selected_day=selected_day, selected_period=selected_period,
        periods_per_day=int(rules.get('periods_per_day', 8)),
        break_after_period=int(rules.get('break_after_period', 4)),
        days=DAYS_OF_WEEK, master_data=master_data
    )
