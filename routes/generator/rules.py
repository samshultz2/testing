"""generator_bp — rules routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/rules')
@login_required
def rules_config():
    from utils.generator_times import day_end_time, clock_params
    level = get_current_level()
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
    end_time = day_end_time(rules, int(rules.get('periods_per_day', 8)),
                            int(rules.get('break_after_period', 5)))
    sh, sm, _, _ = clock_params(rules)          # normalized HH:MM for the <input type="time">
    day_start_hhmm = f"{sh:02d}:{sm:02d}"
    return render_template('generator/rules_config.html', rules=rules, level=level,
                           end_time=end_time, day_start_hhmm=day_start_hhmm)


@generator_bp.route('/rules/save', methods=['POST'])
@login_required
def save_rules():
    level = get_current_level()
    try:
        rules_to_save = [
            ('periods_per_day', request.form.get('periods_per_day', '8')),
            ('break_after_period', request.form.get('break_after_period', '5')),
            # School-day clock (per level: JSS and SSS can start/end differently).
            ('day_start', request.form.get('day_start', '8:20').strip() or '8:20'),
            ('period_minutes', request.form.get('period_minutes', '40').strip() or '40'),
            ('break_minutes', request.form.get('break_minutes', '30').strip() or '30'),
            ('no_repeat_same_day', 'true' if request.form.get('no_repeat_same_day') == 'on' else 'false'),
            ('max_consecutive', request.form.get('max_consecutive', '3')),
            ('distribute_evenly', 'true' if request.form.get('distribute_evenly') == 'on' else 'false'),
        ]
        
        for rule_type, value in rules_to_save:
            # Find existing rule for this level or create new
            existing = GenTimetableRule.query.filter_by(rule_type=rule_type, school_level=level, branch_id=gen_bid()).first()
            if existing:
                existing.value = value
                existing.is_active = True
            else:
                db.session.add(GenTimetableRule(rule_type=rule_type, value=value, school_level=level, is_active=True, branch_id=gen_bid()))
        
        db.session.commit()
        flash('Rules saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.rules_config'))


@generator_bp.route('/settings')
@login_required
def generator_settings():
    from models import AcademicSession, Term
    # Draw the academic-year and term choices from what the school already has.
    sessions = [s.name for s in AcademicSession.query
                .order_by(AcademicSession.is_active.desc(), AcademicSession.name.desc()).all()
                if s.name]
    terms = [t[0] for t in db.session.query(Term.name)
             .filter(Term.name.isnot(None), Term.name != '')
             .group_by(Term.name).order_by(db.func.min(Term.term_number)).all()]

    # Saved value, else the active session/term as a sensible default.
    active_session = AcademicSession.query.filter_by(is_active=True).first()
    active_term = Term.query.filter_by(is_active=True).first()
    academic_year = GenSettings.get('academic_year', '') or (active_session.name if active_session else '')
    term_name = GenSettings.get('term_name', '') or (active_term.name if active_term else '')

    # Never drop a previously-saved custom value that isn't in the current lists.
    if academic_year and academic_year not in sessions:
        sessions.insert(0, academic_year)
    if term_name and term_name not in terms:
        terms.insert(0, term_name)

    return render_template('generator/settings.html',
        school_name=GenSettings.get('school_name', ''),
        school_address=GenSettings.get('school_address', ''),
        academic_year=academic_year, term_name=term_name,
        sessions=sessions, terms=terms
    )


@generator_bp.route('/settings/save', methods=['POST'])
@login_required
def save_generator_settings():
    try:
        for key in ['school_name', 'school_address', 'academic_year', 'term_name']:
            GenSettings.set(key, request.form.get(key, ''))
        flash('Settings saved!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.generator_settings'))


@generator_bp.route('/clash-rules')
@login_required
def clash_rules_list():
    """List all subject clash rules"""
    from models import GenSubjectClashRule, GenCombinedClassRule
    
    clash_rules = GenSubjectClashRule.query.filter_by(branch_id=gen_bid()).order_by(GenSubjectClashRule.id).all()
    combined_rules = GenCombinedClassRule.query.filter_by(branch_id=gen_bid()).order_by(GenCombinedClassRule.id).all()
    
    return render_template('generator/clash_rules.html',
        clash_rules=clash_rules,
        combined_rules=combined_rules
    )


@generator_bp.route('/clash-rules/add', methods=['GET', 'POST'])
@login_required
def add_clash_rule():
    """Add a new subject clash rule"""
    from models import GenSubjectClashRule, GenClassConfig
    
    if request.method == 'POST':
        try:
            rule = GenSubjectClashRule(
                branch_id=gen_bid(),
                name=request.form.get('name', '').strip(),
                description=request.form.get('description', '').strip() or None,
                source_subject_id=int(request.form.get('source_subject_id')),
                source_class_name=request.form.get('source_class_name'),
                source_arm_name=request.form.get('source_arm_name') or None,
                target_subject_id=int(request.form.get('target_subject_id')),
                target_class_name=request.form.get('target_class_name') or None,
                target_arm_name=request.form.get('target_arm_name') or None,
                is_active=True
            )
            db.session.add(rule)
            db.session.commit()
            flash('Subject clash rule added successfully', 'success')
            return redirect(url_for('generator.clash_rules_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding rule: {str(e)}', 'error')
    
    level = get_current_level()
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()
    
    return render_template('generator/add_clash_rule.html',
        subjects=subjects,
        classes=classes
    )


@generator_bp.route('/clash-rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_clash_rule(rule_id):
    """Toggle a clash rule active/inactive"""
    from models import GenSubjectClashRule
    
    rule = gen_owned_or_404(GenSubjectClashRule, rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    
    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/clash-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_clash_rule(rule_id):
    """Delete a clash rule"""
    from models import GenSubjectClashRule
    
    rule = gen_owned_or_404(GenSubjectClashRule, rule_id)
    db.session.delete(rule)
    db.session.commit()
    
    flash('Rule deleted', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/combined-rules/add', methods=['GET', 'POST'])
@login_required
def add_combined_rule():
    """Add a new combined class rule"""
    from models import GenCombinedClassRule, GenClassConfig
    
    if request.method == 'POST':
        try:
            rule = GenCombinedClassRule(
                branch_id=gen_bid(),
                name=request.form.get('name', '').strip(),
                description=request.form.get('description', '').strip() or None,
                shadow_subject_id=int(request.form.get('shadow_subject_id')),
                shadow_class_name=request.form.get('shadow_class_name'),
                shadow_arm_name=request.form.get('shadow_arm_name') or None,
                teacher_subject_id=int(request.form.get('teacher_subject_id')),
                teacher_class_name=request.form.get('teacher_class_name'),
                teacher_arm_name=request.form.get('teacher_arm_name') or None,
                is_active=True
            )
            db.session.add(rule)
            db.session.commit()
            flash('Combined class rule added successfully', 'success')
            return redirect(url_for('generator.clash_rules_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding rule: {str(e)}', 'error')
    
    level = get_current_level()
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()
    
    return render_template('generator/add_combined_rule.html',
        subjects=subjects,
        classes=classes
    )


@generator_bp.route('/combined-rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_combined_rule(rule_id):
    """Toggle a combined rule active/inactive"""
    from models import GenCombinedClassRule
    
    rule = gen_owned_or_404(GenCombinedClassRule, rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    
    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/combined-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_combined_rule(rule_id):
    """Delete a combined rule"""
    from models import GenCombinedClassRule
    
    rule = gen_owned_or_404(GenCombinedClassRule, rule_id)
    db.session.delete(rule)
    db.session.commit()
    
    flash('Rule deleted', 'success')
    return redirect(url_for('generator.clash_rules_list'))
