"""generator_bp — teachers routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/teachers')
@login_required
def teachers_list():
    level = get_current_level()
    teachers = GenTeacher.query.filter_by(is_active=True, school_level=level).order_by(GenTeacher.name).all()
    return render_template('generator/teachers.html', teachers=teachers, level=level)


@generator_bp.route('/teachers/add', methods=['GET', 'POST'])
@login_required
def add_teacher():
    level = get_current_level()
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash('Teacher name is required.', 'error')
                return redirect(url_for('generator.add_teacher'))
            
            teacher = GenTeacher(
                name=name,
                school_level=level,
                staff_id=request.form.get('staff_id', '').strip() or None,
                phone=request.form.get('phone', '').strip() or None,
                email=request.form.get('email', '').strip() or None,
                max_periods_per_day=request.form.get('max_periods_per_day', type=int) or 6,
                max_periods_per_week=request.form.get('max_periods_per_week', type=int) or 30,
                preferred_time=request.form.get('preferred_time', 'any'),
                is_part_time=request.form.get('is_part_time') == 'on',
                available_days=','.join(request.form.getlist('available_days[]')) or '0,1,2,3,4'
            )
            db.session.add(teacher)
            db.session.commit()
            flash(f'Teacher "{name}" added!', 'success')
            return redirect(url_for('generator.edit_teacher', teacher_id=teacher.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('generator/add_teacher.html', days=DAYS_OF_WEEK)


@generator_bp.route('/teachers/<int:teacher_id>')
@login_required
def edit_teacher(teacher_id):
    teacher = GenTeacher.query.get_or_404(teacher_id)
    level = teacher.school_level
    all_subjects = GenSubject.query.filter_by(is_active=True, school_level=level).order_by(GenSubject.name).all()
    assigned_ids = [ts.subject_id for ts in teacher.subjects]
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level).all()}
    periods_per_day = int(rules.get('periods_per_day', 8))
    
    # Get unavailable slots
    unavailable = set()
    for ua in teacher.availability.filter_by(is_available=False).all():
        unavailable.add(f"{ua.day_of_week}_{ua.period_number}")
    
    # Candidate login accounts to link this generator-teacher to, so the person
    # can view their personal timetable. Suggest the closest name match first.
    from models import User
    from utils.name_match import normalize_person_name
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()
    tkey = normalize_person_name(teacher.name)
    suggested_user_id = None
    if not teacher.user_id and tkey:
        for u in users:
            if normalize_person_name(u.full_name or u.username) == tkey:
                suggested_user_id = u.id
                break

    return render_template('generator/edit_teacher.html',
        teacher=teacher, all_subjects=all_subjects, assigned_ids=assigned_ids,
        days=DAYS_OF_WEEK, periods_per_day=periods_per_day, unavailable=unavailable,
        users=[{'id': u.id, 'label': (u.full_name or u.username)
                + (' · @' + u.username if u.full_name else '')} for u in users],
        suggested_user_id=suggested_user_id,
    )


@generator_bp.route('/teachers/<int:teacher_id>/update', methods=['POST'])
@login_required
def update_teacher(teacher_id):
    teacher = GenTeacher.query.get_or_404(teacher_id)
    try:
        teacher.name = request.form.get('name', '').strip()
        teacher.staff_id = request.form.get('staff_id', '').strip() or None
        teacher.phone = request.form.get('phone', '').strip() or None
        teacher.email = request.form.get('email', '').strip() or None
        teacher.max_periods_per_day = request.form.get('max_periods_per_day', type=int) or 6
        teacher.max_periods_per_week = request.form.get('max_periods_per_week', type=int) or 30
        teacher.preferred_time = request.form.get('preferred_time', 'any')
        teacher.is_part_time = request.form.get('is_part_time') == 'on'
        teacher.available_days = ','.join(request.form.getlist('available_days[]')) or '0,1,2,3,4'
        # Link to a login account (or clear the link). Validated so only a real,
        # active user id is stored.
        uid = request.form.get('user_id', type=int)
        if uid:
            from models import User
            teacher.user_id = uid if User.query.filter_by(id=uid, is_active=True).first() else None
        else:
            teacher.user_id = None
        db.session.commit()
        flash('Teacher updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_teacher', teacher_id=teacher_id))


@generator_bp.route('/teachers/<int:teacher_id>/subjects', methods=['POST'])
@login_required
def update_teacher_subjects(teacher_id):
    teacher = GenTeacher.query.get_or_404(teacher_id)
    try:
        subject_ids = [int(x) for x in request.form.getlist('subject_ids[]') if x]
        GenTeacherSubject.query.filter_by(teacher_id=teacher_id).delete()
        for subject_id in subject_ids:
            db.session.add(GenTeacherSubject(teacher_id=teacher_id, subject_id=subject_id))
        db.session.commit()
        flash(f'Updated subjects for {teacher.name}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_teacher', teacher_id=teacher_id))


@generator_bp.route('/teachers/<int:teacher_id>/availability', methods=['POST'])
@login_required
def update_teacher_availability(teacher_id):
    teacher = GenTeacher.query.get_or_404(teacher_id)
    try:
        GenTeacherAvailability.query.filter_by(teacher_id=teacher_id).delete()
        for slot in request.form.getlist('unavailable[]'):
            day, period = slot.split('_')
            db.session.add(GenTeacherAvailability(
                teacher_id=teacher_id, day_of_week=int(day),
                period_number=int(period), is_available=False
            ))
        db.session.commit()
        flash('Availability updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_teacher', teacher_id=teacher_id))


@generator_bp.route('/teachers/<int:teacher_id>/delete', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    teacher = GenTeacher.query.get_or_404(teacher_id)
    try:
        teacher.is_active = False
        db.session.commit()
        flash(f'Teacher "{teacher.name}" removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.teachers_list'))


@generator_bp.route('/teachers/import', methods=['GET', 'POST'])
@login_required
def import_teachers():
    if request.method == 'POST':
        try:
            import csv
            from io import StringIO
            file = request.files.get('file')
            if not file:
                flash('No file uploaded.', 'error')
                return redirect(url_for('generator.import_teachers'))
            from utils.uploads import ext_ok
            if not ext_ok(file.filename, {'.csv'}):
                flash('Please upload a .csv file.', 'error')
                return redirect(url_for('generator.import_teachers'))

            content = file.read().decode('utf-8', errors='replace')
            reader = csv.DictReader(StringIO(content))
            count = 0
            for row in reader:
                name = row.get('name', '').strip()
                if not name or GenTeacher.query.filter_by(name=name, is_active=True).first():
                    continue
                db.session.add(GenTeacher(
                    name=name,
                    staff_id=row.get('staff_id', '').strip() or None,
                    phone=row.get('phone', '').strip() or None,
                    email=row.get('email', '').strip() or None,
                    max_periods_per_day=int(row.get('max_per_day', 6) or 6),
                    max_periods_per_week=int(row.get('max_per_week', 30) or 30)
                ))
                count += 1
            db.session.commit()
            flash(f'Imported {count} teachers!', 'success')
            return redirect(url_for('generator.teachers_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    return render_template('generator/import_teachers.html')
