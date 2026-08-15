"""generator_bp — structure routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/rooms')
@login_required
def rooms_list():
    rooms = GenRoom.query.filter_by(is_active=True, branch_id=gen_bid()).order_by(GenRoom.name).all()
    return render_template('generator/rooms.html', rooms=rooms)


@generator_bp.route('/rooms/add', methods=['GET', 'POST'])
@login_required
def add_room():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash('Room name is required.', 'error')
                return redirect(url_for('generator.add_room'))
            db.session.add(GenRoom(
                name=name,
                branch_id=gen_bid(),
                short_name=request.form.get('short_name', '').strip() or None,
                room_type=request.form.get('room_type', 'classroom'),
                capacity=request.form.get('capacity', type=int)
            ))
            db.session.commit()
            flash(f'Room "{name}" added!', 'success')
            return redirect(url_for('generator.rooms_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    return render_template('generator/add_room.html')


@generator_bp.route('/rooms/<int:room_id>/delete', methods=['POST'])
@login_required
def delete_room(room_id):
    room = gen_owned_or_404(GenRoom, room_id)
    try:
        room.is_active = False
        db.session.commit()
        flash(f'Room "{room.name}" removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.rooms_list'))


@generator_bp.route('/streams')
@login_required
def streams_list():
    streams = GenStream.query.filter_by(is_active=True, branch_id=gen_bid()).order_by(GenStream.name).all()
    return render_template('generator/streams.html', streams=streams)


@generator_bp.route('/streams/add', methods=['GET', 'POST'])
@login_required
def add_stream():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash('Stream name is required.', 'error')
                return redirect(url_for('generator.add_stream'))
            if GenStream.query.filter_by(name=name, branch_id=gen_bid()).first():
                flash('Stream exists.', 'error')
                return redirect(url_for('generator.add_stream'))
            stream = GenStream(
                name=name,
                branch_id=gen_bid(),
                short_name=request.form.get('short_name', '').strip() or None,
                description=request.form.get('description', '').strip() or None
            )
            db.session.add(stream)
            db.session.commit()
            flash(f'Stream "{name}" added!', 'success')
            return redirect(url_for('generator.edit_stream', stream_id=stream.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    return render_template('generator/add_stream.html')


@generator_bp.route('/streams/<int:stream_id>')
@login_required
def edit_stream(stream_id):
    stream = gen_owned_or_404(GenStream, stream_id)
    # Streams are SSS-only
    all_subjects = GenSubject.query.filter_by(is_active=True, school_level='sss', branch_id=gen_bid()).order_by(GenSubject.name).all()
    assigned = {ss.subject_id: ss for ss in stream.subjects}
    # Get global subject configs for default periods display
    global_configs = {cfg.subject_id: cfg for cfg in GenSubjectConfig.query.filter_by(is_active=True, school_level='sss', branch_id=gen_bid()).all()}
    return render_template('generator/edit_stream.html',
        stream=stream, all_subjects=all_subjects, assigned=assigned, global_configs=global_configs
    )


@generator_bp.route('/streams/<int:stream_id>/update', methods=['POST'])
@login_required
def update_stream(stream_id):
    stream = gen_owned_or_404(GenStream, stream_id)
    try:
        stream.name = request.form.get('name', '').strip()
        stream.short_name = request.form.get('short_name', '').strip() or None
        stream.description = request.form.get('description', '').strip() or None
        db.session.commit()
        flash('Stream updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_stream', stream_id=stream_id))


@generator_bp.route('/streams/<int:stream_id>/subjects', methods=['POST'])
@login_required
def update_stream_subjects(stream_id):
    stream = gen_owned_or_404(GenStream, stream_id)
    try:
        subject_ids = [int(x) for x in request.form.getlist('subject_ids[]') if x]
        compulsory_ids = [int(x) for x in request.form.getlist('compulsory_ids[]') if x]
        GenStreamSubject.query.filter_by(stream_id=stream_id).delete()
        for subject_id in subject_ids:
            # Get stream-specific periods (if set)
            periods_str = request.form.get(f'periods_{subject_id}', '').strip()
            periods = int(periods_str) if periods_str else None
            needs_double = request.form.get(f'double_{subject_id}') == '1'
            
            db.session.add(GenStreamSubject(
                stream_id=stream_id, 
                subject_id=subject_id,
                is_compulsory=subject_id in compulsory_ids,
                periods_per_week=periods,
                needs_double_period=needs_double if needs_double else None,
                double_period_count=1 if needs_double else None
            ))
        db.session.commit()
        flash(f'Updated subjects for {stream.name}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_stream', stream_id=stream_id))


@generator_bp.route('/streams/<int:stream_id>/delete', methods=['POST'])
@login_required
def delete_stream(stream_id):
    stream = gen_owned_or_404(GenStream, stream_id)
    try:
        stream.is_active = False
        db.session.commit()
        flash(f'Stream "{stream.name}" removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.streams_list'))


@generator_bp.route('/classes')
@login_required
def classes_config():
    level = get_current_level()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()
    streams = GenStream.query.filter_by(is_active=True, branch_id=gen_bid()).all()
    return render_template('generator/classes_config.html', classes=classes, streams=streams, level=level)


@generator_bp.route('/classes/add', methods=['GET', 'POST'])
@login_required
def add_class_config():
    level = get_current_level()
    if request.method == 'POST':
        try:
            class_name = request.form.get('class_name', '').strip()
            if not class_name:
                flash('Class name is required.', 'error')
                return redirect(url_for('generator.add_class_config'))
            if GenClassConfig.query.filter_by(class_name=class_name, school_level=level, is_active=True, branch_id=gen_bid()).first():
                flash('Class exists.', 'error')
                return redirect(url_for('generator.add_class_config'))
            has_streams = request.form.get('has_streams') == 'on'
            class_config = GenClassConfig(
                class_name=class_name,
                school_level=level,
                branch_id=gen_bid(),
                num_arms=request.form.get('num_arms', type=int) or 1,
                arm_names=request.form.get('arm_names', '').strip() or None,
                has_streams=has_streams
            )
            db.session.add(class_config)
            db.session.commit()
            flash(f'Class "{class_name}" added!', 'success')
            if has_streams:
                return redirect(url_for('generator.edit_class_config', class_id=class_config.id))
            return redirect(url_for('generator.classes_config'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    return render_template('generator/add_class_config.html', level=level)


@generator_bp.route('/classes/<int:class_id>')
@login_required
def edit_class_config(class_id):
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    streams = GenStream.query.filter_by(is_active=True, branch_id=gen_bid()).all()
    arm_streams = {cas.arm_name: cas for cas in class_config.arm_streams}
    return render_template('generator/edit_class_config.html',
        class_config=class_config, streams=streams, arm_streams=arm_streams, level=class_config.school_level
    )


@generator_bp.route('/classes/<int:class_id>/update', methods=['POST'])
@login_required
def update_class_config(class_id):
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    try:
        class_config.class_name = request.form.get('class_name', '').strip()
        class_config.num_arms = request.form.get('num_arms', type=int) or 1
        class_config.arm_names = request.form.get('arm_names', '').strip() or None
        class_config.has_streams = request.form.get('has_streams') == 'on'
        db.session.commit()
        flash('Class configuration updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_class_config', class_id=class_id))


@generator_bp.route('/classes/<int:class_id>/arm-streams', methods=['POST'])
@login_required
def update_arm_streams(class_id):
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    try:
        GenClassArmStream.query.filter_by(class_config_id=class_id).delete()
        for arm_name in class_config.arm_list:
            stream_id = request.form.get(f'stream_{arm_name}', type=int)
            if stream_id:
                db.session.add(GenClassArmStream(
                    class_config_id=class_id, arm_name=arm_name, stream_id=stream_id
                ))
        db.session.commit()
        flash('Arm-stream assignments updated!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.edit_class_config', class_id=class_id))


@generator_bp.route('/classes/<int:class_id>/delete', methods=['POST'])
@login_required
def delete_class_config(class_id):
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    try:
        class_config.is_active = False
        db.session.commit()
        flash(f'Class "{class_config.class_name}" removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.classes_config'))
