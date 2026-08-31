"""generator_bp — api routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/')
@login_required
def index():
    """Timetable generator - Level selector"""
    from flask import session
    
    # Get counts for each level
    jss_teachers = GenTeacher.query.filter_by(is_active=True, school_level='jss').count()
    sss_teachers = GenTeacher.query.filter_by(is_active=True, school_level='sss').count()
    
    # Count actual subjects (GenSubject table)
    jss_subjects = GenSubject.query.filter_by(is_active=True, school_level='jss').count()
    sss_subjects = GenSubject.query.filter_by(is_active=True, school_level='sss').count()
    
    # Class counts
    jss_class_ids = [c.id for c in GenClassConfig.query.filter_by(is_active=True, school_level='jss').all()]
    sss_class_ids = [c.id for c in GenClassConfig.query.filter_by(is_active=True, school_level='sss').all()]
    
    jss_classes = len(jss_class_ids)
    sss_classes = len(sss_class_ids)
    
    jss_assignments = GenTeacherAssignment.query.join(GenClassConfig).filter(
        GenTeacherAssignment.is_active == True,
        GenClassConfig.school_level == 'jss'
    ).count()
    sss_assignments = GenTeacherAssignment.query.join(GenClassConfig).filter(
        GenTeacherAssignment.is_active == True,
        GenClassConfig.school_level == 'sss'
    ).count()
    
    # Get latest timetables for each level
    jss_latest = GenTimetableResult.query.filter_by(school_level='jss').order_by(GenTimetableResult.generated_at.desc()).first()
    sss_latest = GenTimetableResult.query.filter_by(school_level='sss').order_by(GenTimetableResult.generated_at.desc()).first()
    
    return render_template('generator/index.html',
        jss_stats={
            'teachers': jss_teachers,
            'subjects': jss_subjects,
            'classes': jss_classes,
            'assignments': jss_assignments,
            'latest': jss_latest,
            'ready': jss_teachers > 0 and jss_subjects > 0 and jss_classes > 0
        },
        sss_stats={
            'teachers': sss_teachers,
            'subjects': sss_subjects,
            'classes': sss_classes,
            'assignments': sss_assignments,
            'latest': sss_latest,
            'ready': sss_teachers > 0 and sss_subjects > 0 and sss_classes > 0
        }
    )


@generator_bp.route('/setup')
@login_required
def setup_guide():
    """Guided checklist for the timetable-generation process (mirrors term setup).
    Shows each step's status and a link, for the currently selected level."""
    from models import TimetableSlot
    level = get_current_level()

    teachers = GenTeacher.query.filter_by(is_active=True, school_level=level).count()
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level).count()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level).count()
    try:
        streams = GenStream.query.filter_by(school_level=level).count()
    except Exception:
        streams = GenStream.query.count()
    assignments = GenTeacherAssignment.query.join(GenClassConfig).filter(
        GenTeacherAssignment.is_active == True,
        GenClassConfig.school_level == level).count()
    rules = GenTimetableRule.query.filter_by(is_active=True, school_level=level).count()
    periods = TimetableSlot.query.filter_by(is_active=True, is_break=False).count()
    latest = (GenTimetableResult.query.filter_by(school_level=level)
              .order_by(GenTimetableResult.generated_at.desc()).first())

    steps = [
        {'title': 'Add teachers', 'done': teachers > 0,
         'detail': f'{teachers} teacher(s)',
         'url': url_for('generator.teachers_list'), 'cta': 'Teachers'},
        {'title': 'Add subjects', 'done': subjects > 0,
         'detail': f'{subjects} subject(s) — keep names matching your academic subjects',
         'url': url_for('generator.subjects_config'), 'cta': 'Subjects'},
        {'title': 'Configure classes & arms', 'done': classes > 0,
         'detail': f'{classes} class(es)',
         'url': url_for('generator.classes_config'), 'cta': 'Classes'},
        {'title': 'Streams (Arts/Science groupings)', 'optional': True, 'done': True,
         'detail': f'{streams} stream(s) (optional)',
         'url': url_for('generator.streams_list'), 'cta': 'Streams'},
        {'title': 'Assign teachers to class subjects', 'done': assignments > 0,
         'detail': f'{assignments} assignment(s)',
         'url': url_for('generator.teacher_assignments'), 'cta': 'Assignments'},
        {'title': 'Generation rules', 'optional': True, 'done': True,
         'detail': f'{rules} custom rule(s) (sensible defaults otherwise)',
         'url': url_for('generator.rules_config'), 'cta': 'Rules'},
        {'title': 'Class periods configured', 'done': periods > 0,
         'detail': (f'{periods} teaching period(s) — required before applying to '
                    f'class timetables'),
         'url': url_for('settings.timetable_slots'), 'cta': 'Periods'},
        {'title': 'Generate the timetable', 'done': latest is not None,
         'detail': ('Last generated ' + latest.generated_at.strftime('%d %b %Y')
                    if latest else 'Not generated yet'),
         'url': url_for('generator.generate_page'), 'cta': 'Generate'},
        {'title': 'Review & apply to class timetables', 'optional': True,
         'done': latest is not None,
         'detail': 'Open a result, review it, then "Apply to Class Timetables"',
         'url': url_for('generator.results_list'), 'cta': 'Results'},
    ]
    done = sum(1 for s in steps if s['done'] and not s.get('optional'))
    required = sum(1 for s in steps if not s.get('optional'))
    return render_template('generator/setup.html', steps=steps, done=done,
                           required=required, level=level)


@generator_bp.route('/level/<level>')
@login_required
def level_dashboard(level):
    """Dashboard for a specific level (JSS or SSS)"""
    if level not in ['jss', 'sss']:
        flash('Invalid level', 'error')
        return redirect(url_for('generator.index'))
    
    # Store current level in session
    from flask import session
    session['generator_level'] = level
    
    teachers_count = GenTeacher.query.filter_by(is_active=True, school_level=level).count()
    
    # Count actual subjects from GenSubject table
    subjects_count = GenSubject.query.filter_by(is_active=True, school_level=level).count()
    
    # Count configured subjects (for "ready to generate" check)
    configured_subjects = GenSubjectConfig.query.filter_by(is_active=True, school_level=level).count()
    
    classes_count = GenClassConfig.query.filter_by(is_active=True, school_level=level).count()
    streams_count = GenStream.query.filter_by(is_active=True).count() if level == 'sss' else 0
    rooms_count = GenRoom.query.filter_by(is_active=True).count()
    
    assignments_count = GenTeacherAssignment.query.join(GenClassConfig).filter(
        GenTeacherAssignment.is_active == True,
        GenClassConfig.school_level == level
    ).count()
    
    latest_batch = GenTimetableResult.query.filter_by(school_level=level).order_by(
        GenTimetableResult.generated_at.desc()
    ).first()
    
    # Ready to generate if we have teachers, subjects (configured), and classes
    ready_to_generate = (teachers_count > 0 and configured_subjects > 0 and classes_count > 0)
    
    return render_template('generator/level_dashboard.html',
        level=level,
        level_name='Junior Secondary (JSS)' if level == 'jss' else 'Senior Secondary (SSS)',
        teachers_count=teachers_count,
        subjects_count=subjects_count,
        configured_subjects=configured_subjects,
        streams_count=streams_count,
        classes_count=classes_count,
        rooms_count=rooms_count,
        assignments_count=assignments_count,
        ready_to_generate=ready_to_generate,
        latest_batch=latest_batch
    )


@generator_bp.route('/api/teacher/<int:teacher_id>/subjects')
@login_required
def api_teacher_subjects(teacher_id):
    teacher = GenTeacher.query.get_or_404(teacher_id)
    return jsonify([{'id': ts.subject_id, 'name': ts.subject.name} for ts in teacher.subjects])


@generator_bp.route('/api/class/<int:class_id>/arms')
@login_required
def api_class_arms(class_id):
    cc = GenClassConfig.query.get_or_404(class_id)
    return jsonify(cc.arm_list)


@generator_bp.route('/api/stream/<int:stream_id>/subjects')
@login_required
def api_stream_subjects(stream_id):
    stream = GenStream.query.get_or_404(stream_id)
    return jsonify([{'id': ss.subject_id, 'name': ss.subject.name, 'compulsory': ss.is_compulsory} for ss in stream.subjects])


@generator_bp.route('/api/swap', methods=['POST'])
@login_required
def api_swap_slots():
    try:
        data = request.get_json()
        batch_id = data['batch_id']
        class_name = data['class_name']
        arm_name = data['arm_name']
        slot1, slot2 = data['slot1'], data['slot2']
        
        e1 = GenTimetableResult.query.filter_by(
            batch_id=batch_id, class_name=class_name, arm_name=arm_name,
            day_of_week=slot1['day'], period_number=slot1['period']
        ).first()
        e2 = GenTimetableResult.query.filter_by(
            batch_id=batch_id, class_name=class_name, arm_name=arm_name,
            day_of_week=slot2['day'], period_number=slot2['period']
        ).first()
        
        if e1 and e2:
            e1.subject_id, e2.subject_id = e2.subject_id, e1.subject_id
            e1.teacher_id, e2.teacher_id = e2.teacher_id, e1.teacher_id
            db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@generator_bp.route('/setup/jss', methods=['GET', 'POST'])
@login_required
def setup_jss():
    """Quick setup for JSS1, JSS2, JSS3 classes"""
    if request.method == 'POST':
        try:
            arm_names = request.form.get('arm_names', '').strip()
            num_arms = len([a.strip() for a in arm_names.split(',') if a.strip()]) if arm_names else 1
            
            created = []
            for class_name in ['JSS1', 'JSS2', 'JSS3']:
                # Check if already exists for JSS level
                existing = GenClassConfig.query.filter_by(class_name=class_name, school_level='jss', is_active=True).first()
                if existing:
                    # Update existing
                    existing.num_arms = num_arms
                    existing.arm_names = arm_names or None
                    existing.has_streams = False  # JSS doesn't have streams
                else:
                    # Create new
                    class_config = GenClassConfig(
                        class_name=class_name,
                        school_level='jss',
                        num_arms=num_arms,
                        arm_names=arm_names or None,
                        has_streams=False
                    )
                    db.session.add(class_config)
                created.append(class_name)
            
            db.session.commit()
            
            # Set session to JSS level
            from flask import session
            session['generator_level'] = 'jss'
            
            flash(f'JSS classes configured: {", ".join(created)}', 'success')
            return redirect(url_for('generator.classes_config'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'error')
    
    # Get SSS arm names as default suggestion
    sss_class = GenClassConfig.query.filter(
        GenClassConfig.class_name.like('SSS%'),
        GenClassConfig.school_level == 'sss',
        GenClassConfig.is_active == True
    ).first()
    
    suggested_arms = sss_class.arm_names if sss_class else 'Iris,Rose,Lily,Tulip'
    
    return render_template('generator/setup_jss.html', suggested_arms=suggested_arms)


@generator_bp.route('/setup/copy-subjects', methods=['POST'])
@login_required
def copy_subject_config():
    """Copy subject configuration from one class level to another"""
    try:
        source_level = request.form.get('source_level')  # 'SSS' or 'JSS'
        target_level = request.form.get('target_level')  # 'JSS' or 'SSS'

        if not source_level or not target_level:
            flash('Select source and target levels.', 'error')
            return redirect(url_for('generator.classes_config'))

        # Whitelist the level prefixes — they are interpolated into a LIKE pattern,
        # so only known values may be used (no wildcard/free-text injection).
        _LEVELS = {'SSS', 'JSS', 'Primary', 'Nursery', 'KG', 'Basic'}
        if source_level not in _LEVELS or target_level not in _LEVELS:
            flash('Invalid class level.', 'error')
            return redirect(url_for('generator.classes_config'))
        
        # Get source classes
        source_classes = GenClassConfig.query.filter(
            GenClassConfig.class_name.like(f'{source_level}%'),
            GenClassConfig.is_active == True
        ).all()
        
        # Get target classes
        target_classes = GenClassConfig.query.filter(
            GenClassConfig.class_name.like(f'{target_level}%'),
            GenClassConfig.is_active == True
        ).all()
        
        if not source_classes or not target_classes:
            flash('No classes found for source or target level.', 'error')
            return redirect(url_for('generator.classes_config'))
        
        # Copy subject configs from first source class to all target classes
        source_id = source_classes[0].id
        source_configs = GenClassSubjectConfig.query.filter_by(
            class_config_id=source_id, is_active=True
        ).all()
        
        copied = 0
        for target_class in target_classes:
            for src_cfg in source_configs:
                # Check if exists
                existing = GenClassSubjectConfig.query.filter_by(
                    class_config_id=target_class.id,
                    subject_id=src_cfg.subject_id
                ).first()
                
                if existing:
                    existing.periods_per_week = src_cfg.periods_per_week
                    existing.needs_double_period = src_cfg.needs_double_period
                    existing.double_period_count = src_cfg.double_period_count
                    existing.is_enabled = src_cfg.is_enabled
                    existing.is_active = True
                else:
                    new_cfg = GenClassSubjectConfig(
                        class_config_id=target_class.id,
                        subject_id=src_cfg.subject_id,
                        periods_per_week=src_cfg.periods_per_week,
                        needs_double_period=src_cfg.needs_double_period,
                        double_period_count=src_cfg.double_period_count,
                        is_enabled=src_cfg.is_enabled,
                        is_active=True
                    )
                    db.session.add(new_cfg)
                copied += 1
        
        db.session.commit()
        flash(f'Copied {copied} subject configurations to {target_level} classes.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('generator.classes_config'))
