"""generator_bp — subjects routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/subjects')
@login_required
def subjects_config():
    level = get_current_level()
    # Get subjects for this level only
    all_subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    configs = {c.subject_id: c for c in GenSubjectConfig.query.filter_by(school_level=level, branch_id=gen_bid()).all()}
    subjects_data = []
    for i, subject in enumerate(all_subjects):
        subjects_data.append({
            'subject': subject,
            'config': configs.get(subject.id),
            'color': SUBJECT_COLORS[i % len(SUBJECT_COLORS)]
        })
    rooms = GenRoom.query.filter_by(is_active=True, branch_id=gen_bid()).all()
    return render_template('generator/subjects_config.html',
        subjects_data=subjects_data,
        categories=['core', 'science', 'arts', 'commercial', 'vocational'],
        rooms=rooms,
        level=level
    )


@generator_bp.route('/subjects/add', methods=['GET', 'POST'])
@login_required
def add_gen_subject():
    """Add a new subject for timetable generation"""
    level = get_current_level()
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash('Subject name is required.', 'error')
                return redirect(url_for('generator.add_gen_subject'))
            
            # Check if already exists for this level
            if GenSubject.query.filter_by(name=name, school_level=level, is_active=True, branch_id=gen_bid()).first():
                flash(f'Subject "{name}" already exists for {level.upper()}.', 'error')
                return redirect(url_for('generator.add_gen_subject'))
            
            subject = GenSubject(
                name=name,
                branch_id=gen_bid(),
                short_name=request.form.get('short_name', '').strip() or None,
                school_level=level,
                category=request.form.get('category', 'core')
            )
            db.session.add(subject)
            db.session.commit()
            flash(f'Subject "{name}" added!', 'success')
            return redirect(url_for('generator.subjects_config'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('generator/add_subject.html', level=level)


@generator_bp.route('/subjects/sync', methods=['POST'])
@login_required
def sync_gen_subjects():
    """One-way, non-destructive import of academic subjects into this level's
    timetable subjects. Creates any GenSubject that doesn't already exist (by
    name, mirroring add_gen_subject's dedupe); never deletes or edits existing
    gen subjects, their periods, streams, or teacher assignments."""
    level = get_current_level()
    # Map academic categories to the generator's category vocabulary.
    cat_map = {'science': 'science', 'arts': 'arts',
               'commercial': 'commercial', 'general': 'core'}
    try:
        academic = Subject.query.filter_by(is_active=True).order_by(Subject.name).all()
        # Existing gen subject names for this level (case-insensitive).
        existing = {s.name.strip().lower() for s in GenSubject.query.filter_by(
            school_level=level, is_active=True, branch_id=gen_bid()).all()}
        created = 0
        for subj in academic:
            name = (subj.name or '').strip()
            if not name or name.lower() in existing:
                continue
            db.session.add(GenSubject(
                name=name,
                branch_id=gen_bid(),
                short_name=(subj.short_name or '').strip() or None,
                school_level=level,
                category=cat_map.get((subj.category or '').strip().lower(), 'core')
            ))
            existing.add(name.lower())
            created += 1
        db.session.commit()
        if created:
            flash(f'Imported {created} subject(s) from academic subjects into '
                  f'{level.upper()}. Set their periods and teachers to include '
                  f'them in generation.', 'success')
        else:
            flash(f'All academic subjects are already present in {level.upper()}.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.subjects_config'))


@generator_bp.route('/subjects/<int:subject_id>/delete', methods=['POST'])
@login_required
def delete_gen_subject(subject_id):
    """Delete a subject"""
    subject = gen_owned_or_404(GenSubject, subject_id)
    try:
        subject.is_active = False
        # Also deactivate related configs
        GenSubjectConfig.query.filter_by(subject_id=subject_id).update({'is_active': False})
        db.session.commit()
        flash(f'Subject "{subject.name}" removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.subjects_config'))


@generator_bp.route('/subjects/<int:subject_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_gen_subject(subject_id):
    """Edit a subject"""
    subject = gen_owned_or_404(GenSubject, subject_id)
    level = subject.school_level
    
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            if not name:
                flash('Subject name is required.', 'error')
                return redirect(url_for('generator.edit_gen_subject', subject_id=subject_id))
            
            # Check if name already exists for another subject at this level
            existing = GenSubject.query.filter(
                GenSubject.name == name,
                GenSubject.school_level == level,
                GenSubject.branch_id == gen_bid(),
                GenSubject.id != subject_id,
                GenSubject.is_active == True
            ).first()
            if existing:
                flash(f'Subject "{name}" already exists for {level.upper()}.', 'error')
                return redirect(url_for('generator.edit_gen_subject', subject_id=subject_id))
            
            subject.name = name
            subject.short_name = request.form.get('short_name', '').strip() or None
            subject.category = request.form.get('category', 'core')
            db.session.commit()
            flash(f'Subject "{name}" updated!', 'success')
            return redirect(url_for('generator.subjects_config'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    return render_template('generator/edit_subject.html', subject=subject, level=level)


@generator_bp.route('/subjects/save', methods=['POST'])
@login_required
def save_subjects_config():
    level = get_current_level()
    try:
        for subject_id in request.form.getlist('subject_id[]'):
            subject_id = int(subject_id)
            periods = request.form.get(f'periods_{subject_id}', type=int) or 4
            needs_double = request.form.get(f'double_{subject_id}') == 'on'
            double_count = request.form.get(f'double_count_{subject_id}', type=int) or 0
            
            config = GenSubjectConfig.query.filter_by(subject_id=subject_id, school_level=level, branch_id=gen_bid()).first()
            data = {
                'periods_per_week': periods,
                'needs_double_period': needs_double,
                'double_period_count': double_count if needs_double else 0,
                'preferred_time': request.form.get(f'preferred_{subject_id}', 'any'),
                'category': request.form.get(f'category_{subject_id}', 'core'),
                'not_first_period': request.form.get(f'not_first_{subject_id}') == 'on',
                'not_last_period': request.form.get(f'not_last_{subject_id}') == 'on',
                'is_active': True
            }
            if config:
                for k, v in data.items():
                    setattr(config, k, v)
            else:
                db.session.add(GenSubjectConfig(subject_id=subject_id, school_level=level, branch_id=gen_bid(), **data))
        db.session.commit()
        flash('Subject configurations saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.subjects_config'))


@generator_bp.route('/class-subjects')
@login_required
def class_subjects_list():
    """List classes for per-class subject configuration"""
    level = get_current_level()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()
    return render_template('generator/class_subjects_list.html', classes=classes, level=level)


@generator_bp.route('/class-subjects/<int:class_id>')
@login_required
def class_subjects_config(class_id):
    """Configure subject periods for a specific class"""
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    level = class_config.school_level
    
    # Get all subjects for this level with global defaults
    all_subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    global_configs = {c.subject_id: c for c in GenSubjectConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
    
    # Get class-specific overrides
    class_configs = {c.subject_id: c for c in GenClassSubjectConfig.query.filter_by(
        class_config_id=class_id, is_active=True
    ).all()}
    
    # Build subjects data with effective values
    subjects_data = []
    for subject in all_subjects:
        global_cfg = global_configs.get(subject.id)
        class_cfg = class_configs.get(subject.id)
        
        # Determine category
        category = global_cfg.category if global_cfg else 'core'
        
        # Class config overrides global
        if class_cfg:
            periods = class_cfg.periods_per_week
            needs_double = class_cfg.needs_double_period
            double_count = class_cfg.double_period_count
            is_enabled = class_cfg.is_enabled
            has_override = True
        elif global_cfg:
            periods = global_cfg.periods_per_week
            needs_double = global_cfg.needs_double_period
            double_count = global_cfg.double_period_count
            is_enabled = True  # Default enabled if global config exists
            has_override = False
        else:
            periods = 4
            needs_double = False
            double_count = 0
            is_enabled = True  # Default enabled
            has_override = False
        
        subjects_data.append({
            'subject': subject,
            'periods': periods,
            'needs_double': needs_double,
            'double_count': double_count,
            'is_enabled': is_enabled,
            'has_override': has_override,
            'category': category
        })
    
    return render_template('generator/class_subjects_config.html',
        class_config=class_config,
        subjects_data=subjects_data
    )


@generator_bp.route('/class-subjects/<int:class_id>/save', methods=['POST'])
@login_required
def save_class_subjects_config(class_id):
    """Save per-class subject configuration"""
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    
    try:
        for subject_id in request.form.getlist('subject_id[]'):
            subject_id = int(subject_id)
            is_enabled = request.form.get(f'enabled_{subject_id}') == 'on'
            periods = request.form.get(f'periods_{subject_id}', type=int) or 4
            needs_double = request.form.get(f'double_{subject_id}') == 'on'
            double_count = request.form.get(f'double_count_{subject_id}', type=int) or 0
            
            existing = GenClassSubjectConfig.query.filter_by(
                class_config_id=class_id, subject_id=subject_id
            ).first()
            
            if existing:
                existing.is_enabled = is_enabled
                existing.periods_per_week = periods
                existing.needs_double_period = needs_double
                existing.double_period_count = double_count if needs_double else 0
                existing.is_active = True
            else:
                db.session.add(GenClassSubjectConfig(
                    class_config_id=class_id,
                    subject_id=subject_id,
                    is_enabled=is_enabled,
                    periods_per_week=periods,
                    needs_double_period=needs_double,
                    double_period_count=double_count if needs_double else 0
                ))
        
        db.session.commit()
        flash(f'Subject configuration for {class_config.class_name} saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('generator.class_subjects_config', class_id=class_id))


@generator_bp.route('/classes/<int:class_id>/stream-subjects')
@login_required
def class_stream_subjects(class_id):
    """Configure subject periods for each stream in this class"""
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    
    if not class_config.has_streams:
        flash('This class does not use streams.', 'warning')
        return redirect(url_for('generator.edit_class_config', class_id=class_id))
    
    # Get streams used by this class
    stream_ids = set()
    for cas in GenClassArmStream.query.filter_by(class_config_id=class_id).all():
        if cas.stream_id:
            stream_ids.add(cas.stream_id)
    
    streams_data = []
    for stream_id in stream_ids:
        stream = GenStream.query.get(stream_id)
        if not stream:
            continue
        
        # Get subjects in this stream
        stream_subjects = GenStreamSubject.query.filter_by(stream_id=stream_id).all()
        
        # Get class-stream configs
        class_stream_configs = {
            css.subject_id: css 
            for css in GenClassStreamSubject.query.filter_by(
                class_config_id=class_id, stream_id=stream_id
            ).all()
        }
        
        subjects = []
        total_periods = 0
        for ss in stream_subjects:
            cfg = GenSubjectConfig.query.filter_by(subject_id=ss.subject_id).first()
            class_stream_cfg = class_stream_configs.get(ss.subject_id)
            
            # Priority: class-stream > stream > global
            if class_stream_cfg:
                periods = class_stream_cfg.periods_per_week
                needs_double = class_stream_cfg.needs_double_period
                double_count = class_stream_cfg.double_period_count
                is_enabled = class_stream_cfg.is_enabled
            elif ss.periods_per_week is not None:
                periods = ss.periods_per_week
                needs_double = ss.needs_double_period or False
                double_count = ss.double_period_count
                is_enabled = True
            elif cfg:
                periods = cfg.periods_per_week
                needs_double = cfg.needs_double_period
                double_count = cfg.double_period_count
                is_enabled = True
            else:
                periods = 2
                needs_double = False
                double_count = 0
                is_enabled = True

            if is_enabled:
                total_periods += periods

            subjects.append({
                'id': ss.subject_id,
                'name': ss.subject.name if ss.subject else f'[Subject {ss.subject_id}]',
                'periods': periods,
                'needs_double': needs_double,
                'double_count': double_count or 0,
                'is_enabled': is_enabled,
                'global_periods': cfg.periods_per_week if cfg else 2,
                'stream_periods': ss.periods_per_week
            })
        
        streams_data.append({
            'stream': stream,
            'subjects': subjects,
            'total_periods': total_periods
        })
    
    # Weekly capacity = periods/day × 5 days, for THIS class's level (JSS or SSS
    # can differ). Drives the "x/N periods" budget shown per stream.
    level = class_config.school_level or 'sss'
    ppd_rule = GenTimetableRule.query.filter_by(
        rule_type='periods_per_day', school_level=level, is_active=True, branch_id=gen_bid()).first()
    try:
        periods_per_day = int(ppd_rule.value) if ppd_rule and ppd_rule.value else 8
    except (TypeError, ValueError):
        periods_per_day = 8
    weekly_capacity = periods_per_day * 5

    return render_template('generator/class_stream_subjects.html',
        class_config=class_config,
        streams_data=streams_data,
        weekly_capacity=weekly_capacity
    )


@generator_bp.route('/classes/<int:class_id>/stream-subjects/save', methods=['POST'])
@login_required
def save_class_stream_subjects(class_id):
    """Save class-stream subject configuration"""
    class_config = gen_owned_or_404(GenClassConfig, class_id)
    
    try:
        stream_id = int(request.form.get('stream_id'))
        subject_ids = [int(x) for x in request.form.getlist('subject_ids[]') if x]
        
        for subject_id in subject_ids:
            periods = int(request.form.get(f'periods_{subject_id}', 2))
            needs_double = request.form.get(f'double_{subject_id}') == '1'
            is_enabled = request.form.get(f'enabled_{subject_id}') == '1'

            existing = GenClassStreamSubject.query.filter_by(
                class_config_id=class_id,
                stream_id=stream_id,
                subject_id=subject_id
            ).first()

            # How many double periods per week — taken from THIS page's own count
            # box (default 1 when ticked without a number), clamped so 2×doubles
            # never exceeds the subject's weekly periods.
            double_count = 0
            if needs_double:
                dc = request.form.get(f'double_count_{subject_id}', type=int) or 1
                double_count = max(1, min(dc, periods // 2) if periods else dc)
            
            if existing:
                existing.periods_per_week = periods
                existing.needs_double_period = needs_double
                existing.double_period_count = double_count
                existing.is_enabled = is_enabled
            else:
                db.session.add(GenClassStreamSubject(
                    class_config_id=class_id,
                    stream_id=stream_id,
                    subject_id=subject_id,
                    periods_per_week=periods,
                    needs_double_period=needs_double,
                    double_period_count=double_count,
                    is_enabled=is_enabled
                ))
        
        db.session.commit()
        stream = GenStream.query.get(stream_id)
        flash(f'Saved {stream.name} subjects for {class_config.class_name}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('generator.class_stream_subjects', class_id=class_id))
