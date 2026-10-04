"""generator_bp — rules routes (split from the former routes/generator.py)."""
from routes.generator import *  # noqa: F401,F403


@generator_bp.route('/rules')
@login_required
def rules_config():
    from utils.generator_times import day_end_time, clock_params
    from utils.timeutil import get_time_format
    level = get_current_level()
    rules = {r.rule_type: r.value for r in GenTimetableRule.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()}
    end_time = day_end_time(rules, int(rules.get('periods_per_day', 8)),
                            int(rules.get('break_after_period', 5)))
    sh, sm, _, _ = clock_params(rules)          # normalized HH:MM for the <input type="time">
    day_start_hhmm = f"{sh:02d}:{sm:02d}"
    # Day-separation is opt-in per subject, picked right here instead of
    # visiting each subject's own rules page: a subject is "on" only if its
    # GenSubjectConfig row explicitly says day_separation_exempt=False.
    # No row at all (never touched) means exempt -- off by default.
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()) \
        .order_by(GenSubject.name).all()
    day_separation_subject_ids = {
        sc.subject_id for sc in GenSubjectConfig.query.filter_by(
            branch_id=gen_bid(), school_level=level, day_separation_exempt=False).all()
    }
    # Per-class exceptions to the subject-level choice above — e.g. a subject
    # that's on for most classes but should be off for one specific class.
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()) \
        .order_by(GenClassConfig.class_name).all()
    class_override_rows = (
        GenClassSubjectConfig.query.join(GenClassConfig)
        .filter(GenClassConfig.branch_id == gen_bid(), GenClassConfig.school_level == level,
               GenClassSubjectConfig.day_separation_exempt.isnot(None))
        .all()
    )
    day_separation_class_overrides = [{
        'class_config_id': ov.class_config_id, 'class_name': ov.class_config.class_name,
        'subject_id': ov.subject_id, 'subject_name': ov.subject.name,
        'exempt': ov.day_separation_exempt,
    } for ov in class_override_rows]
    day_separation_class_overrides.sort(key=lambda r: (r['subject_name'], r['class_name']))
    return render_template('generator/rules_config.html', rules=rules, level=level,
                           end_time=end_time, day_start_hhmm=day_start_hhmm,
                           time_format=get_time_format(), subjects=subjects,
                           day_separation_subject_ids=day_separation_subject_ids,
                           classes=classes, day_separation_class_overrides=day_separation_class_overrides)


@generator_bp.route('/rules/save', methods=['POST'])
@login_required
def save_rules():
    level = get_current_level()
    try:
        if (request.form.get('day_separation_enabled') == 'on'
                and request.form.get('day_separation_day_a', '0') == request.form.get('day_separation_day_b', '4')):
            raise ValueError('Day A and Day B must be different days for the day-separation rule.')
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
            ('first_period_no_repeat', 'true' if request.form.get('first_period_no_repeat') == 'on' else 'false'),
            ('day_separation_enabled', 'true' if request.form.get('day_separation_enabled') == 'on' else 'false'),
            ('day_separation_day_a', request.form.get('day_separation_day_a', '0')),
            ('day_separation_day_b', request.form.get('day_separation_day_b', '4')),
            ('day_separation_auto_probe',
             'true' if request.form.get('day_separation_auto_probe') == 'on' else 'false'),
        ]
        
        for rule_type, value in rules_to_save:
            # Find existing rule for this level or create new
            existing = GenTimetableRule.query.filter_by(rule_type=rule_type, school_level=level, branch_id=gen_bid()).first()
            if existing:
                existing.value = value
                existing.is_active = True
            else:
                db.session.add(GenTimetableRule(rule_type=rule_type, value=value, school_level=level, is_active=True, branch_id=gen_bid()))

        # Which subjects day-separation applies to, picked right here instead
        # of visiting each subject's own rules page. Every subject at this
        # level gets an explicit GenSubjectConfig.day_separation_exempt value
        # on every save (not just the ones checked), so a subject's state is
        # never ambiguous after this form has been submitted once.
        selected_subject_ids = {int(sid) for sid in request.form.getlist('day_separation_subjects[]') if sid.isdigit()}
        subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).all()
        configs = {sc.subject_id: sc for sc in GenSubjectConfig.query.filter_by(
            school_level=level, branch_id=gen_bid()).all()}
        for subject in subjects:
            exempt = subject.id not in selected_subject_ids
            cfg = configs.get(subject.id)
            if cfg:
                cfg.day_separation_exempt = exempt
            else:
                db.session.add(GenSubjectConfig(subject_id=subject.id, school_level=level,
                                                branch_id=gen_bid(), day_separation_exempt=exempt))

        db.session.commit()
        flash('Rules saved!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
    return redirect(url_for('generator.rules_config'))


@generator_bp.route('/rules/day-separation-class-override', methods=['POST'])
@login_required
def set_day_separation_class_override():
    """One class's exception to the day-separation subject picker above --
    e.g. Mathematics is on for every class except SSS1 Gold. 'inherit'
    clears the exception (back to whatever the subject-level choice says)."""
    level = get_current_level()
    try:
        subject_id = request.form.get('subject_id', type=int)
        class_id = request.form.get('class_id', type=int)
        choice = request.form.get('choice')
        if choice not in ('include', 'exempt', 'inherit'):
            raise ValueError('Pick Apply, Exempt, or Inherit default.')
        subject = GenSubject.query.filter_by(id=subject_id, school_level=level, branch_id=gen_bid()).first()
        cc = GenClassConfig.query.filter_by(id=class_id, school_level=level, branch_id=gen_bid()).first()
        if not subject or not cc:
            raise ValueError('Subject or class not found.')

        value = {'include': False, 'exempt': True, 'inherit': None}[choice]
        row = GenClassSubjectConfig.query.filter_by(class_config_id=class_id, subject_id=subject_id).first()
        if row:
            row.day_separation_exempt = value
        elif value is not None:
            db.session.add(GenClassSubjectConfig(class_config_id=class_id, subject_id=subject_id,
                                                  day_separation_exempt=value))
        # else: no row and nothing to inherit away from -- nothing to do.
        db.session.commit()
        flash(f'Day-separation exception saved for {subject.name} / {cc.class_name}.', 'success')
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
    from models import (GenSubjectClashRule, GenCombinedClassRule, GenCoScheduleRule,
                        GenDaySeparationRule, GenPeriodPlacementRule)

    clash_rules = GenSubjectClashRule.query.filter_by(branch_id=gen_bid()).order_by(GenSubjectClashRule.id).all()
    combined_rules = GenCombinedClassRule.query.filter_by(branch_id=gen_bid()).order_by(GenCombinedClassRule.id).all()
    coschedule_rules = GenCoScheduleRule.query.filter_by(branch_id=gen_bid()).order_by(GenCoScheduleRule.id).all()
    day_separation_rules = GenDaySeparationRule.query.filter_by(branch_id=gen_bid()).order_by(GenDaySeparationRule.id).all()
    period_placement_rules = GenPeriodPlacementRule.query.filter_by(branch_id=gen_bid()).order_by(GenPeriodPlacementRule.id).all()

    return render_template('generator/clash_rules.html',
        clash_rules=clash_rules,
        combined_rules=combined_rules,
        coschedule_rules=coschedule_rules,
        day_separation_rules=day_separation_rules,
        period_placement_rules=period_placement_rules
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


@generator_bp.route('/coschedule-rules/add', methods=['GET', 'POST'])
@login_required
def add_coschedule_rule():
    """Add a new co-schedule rule (force 2 or more class/arm/subject slots
    into the same time slot every time)"""
    from models import GenCoScheduleRule, GenCoScheduleRuleMember, GenClassConfig

    if request.method == 'POST':
        try:
            subject_ids = request.form.getlist('member_subject_id[]')
            class_names = request.form.getlist('member_class_name[]')
            arm_names = request.form.getlist('member_arm_name[]')
            if not (len(subject_ids) == len(class_names) == len(arm_names)):
                raise ValueError('Malformed member rows submitted.')

            members = []
            seen_arms = set()
            for subj_id, cname, aname in zip(subject_ids, class_names, arm_names):
                subj_id, cname, aname = (subj_id or '').strip(), (cname or '').strip(), (aname or '').strip()
                if not subj_id and not cname and not aname:
                    continue  # blank trailing row from the repeatable UI
                if not subj_id or not cname or not aname:
                    raise ValueError('Every member needs a subject, class, and arm.')
                if (cname, aname) in seen_arms:
                    raise ValueError(f'{cname} {aname} was added more than once — each arm can only appear once per group.')
                seen_arms.add((cname, aname))
                members.append((int(subj_id), cname, aname))

            if len(members) < 2:
                raise ValueError('A co-schedule group needs at least 2 members — a specific '
                                 'arm/subject on each side that should always land in the same slot.')

            rule = GenCoScheduleRule(
                branch_id=gen_bid(),
                name=request.form.get('name', '').strip(),
                description=request.form.get('description', '').strip() or None,
                is_active=True
            )
            db.session.add(rule)
            db.session.flush()
            for subj_id, cname, aname in members:
                db.session.add(GenCoScheduleRuleMember(
                    rule_id=rule.id, subject_id=subj_id, class_name=cname, arm_name=aname))
            db.session.commit()
            flash('Co-schedule rule added successfully', 'success')
            return redirect(url_for('generator.clash_rules_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding rule: {str(e)}', 'error')

    level = get_current_level()
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()

    return render_template('generator/add_coschedule_rule.html',
        subjects=subjects,
        classes=classes
    )


@generator_bp.route('/coschedule-rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_coschedule_rule(rule_id):
    """Toggle a co-schedule rule active/inactive"""
    from models import GenCoScheduleRule

    rule = gen_owned_or_404(GenCoScheduleRule, rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()

    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/coschedule-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_coschedule_rule(rule_id):
    """Delete a co-schedule rule"""
    from models import GenCoScheduleRule

    rule = gen_owned_or_404(GenCoScheduleRule, rule_id)
    db.session.delete(rule)
    db.session.commit()

    flash('Rule deleted', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/day-separation-rules/add', methods=['GET', 'POST'])
@login_required
def add_day_separation_rule():
    """Add a new day-separation rule (keep a subject off two named days
    together for a class, e.g. SSS1 Rose's Physics can be on Monday or
    Friday, never both in the same week)."""
    from models import GenDaySeparationRule, GenClassConfig
    from models.models.generator import DAY_NAMES

    if request.method == 'POST':
        try:
            day_a = int(request.form.get('day_a'))
            day_b = int(request.form.get('day_b'))
            if day_a == day_b:
                raise ValueError('Pick two different days — a subject can\'t be '
                                 'separated from itself on the same day.')
            if not (0 <= day_a < len(DAY_NAMES)) or not (0 <= day_b < len(DAY_NAMES)):
                raise ValueError('Invalid day selection.')
            rule = GenDaySeparationRule(
                branch_id=gen_bid(),
                name=request.form.get('name', '').strip(),
                description=request.form.get('description', '').strip() or None,
                subject_id=int(request.form.get('subject_id')),
                class_name=request.form.get('class_name'),
                arm_name=request.form.get('arm_name') or None,
                day_a=day_a, day_b=day_b,
                is_active=True
            )
            if not rule.name:
                raise ValueError('Rule name is required.')
            db.session.add(rule)
            db.session.commit()
            flash('Day-separation rule added successfully', 'success')
            return redirect(url_for('generator.clash_rules_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding rule: {str(e)}', 'error')

    level = get_current_level()
    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()

    return render_template('generator/add_day_separation_rule.html',
        subjects=subjects,
        classes=classes,
        day_names=DAY_NAMES
    )


@generator_bp.route('/day-separation-rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_day_separation_rule(rule_id):
    """Toggle a day-separation rule active/inactive"""
    from models import GenDaySeparationRule

    rule = gen_owned_or_404(GenDaySeparationRule, rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()

    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/day-separation-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_day_separation_rule(rule_id):
    """Delete a day-separation rule"""
    from models import GenDaySeparationRule

    rule = gen_owned_or_404(GenDaySeparationRule, rule_id)
    db.session.delete(rule)
    db.session.commit()

    flash('Rule deleted', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/period-placement-rules/add', methods=['GET', 'POST'])
@login_required
def add_period_placement_rule():
    """Add a new period-placement rule for a class/arm: pin a subject to one
    exact period, keep it out of the first/last period, restrict it to
    morning/afternoon only, or confine it to a range of periods."""
    from models import GenPeriodPlacementRule, GenClassConfig, GenTimetableRule
    from models.models.generator import PERIOD_PLACEMENT_RULE_TYPES

    level = get_current_level()
    ppd_rule = GenTimetableRule.query.filter_by(
        rule_type='periods_per_day', school_level=level, is_active=True, branch_id=gen_bid()).first()
    try:
        max_periods = int(ppd_rule.value) if ppd_rule and ppd_rule.value else 8
    except (TypeError, ValueError):
        max_periods = 8

    if request.method == 'POST':
        try:
            rule_type = request.form.get('rule_type', '').strip()
            if rule_type not in PERIOD_PLACEMENT_RULE_TYPES:
                raise ValueError('Select a valid rule type.')

            period_value = None
            range_end = None
            if rule_type == 'fixed':
                period_value = int(request.form.get('period_value'))
                if not (1 <= period_value <= max_periods):
                    raise ValueError(f'Period must be between 1 and {max_periods}.')
            elif rule_type == 'range':
                period_value = int(request.form.get('period_value'))
                range_end = int(request.form.get('range_end'))
                if not (1 <= period_value <= max_periods) or not (1 <= range_end <= max_periods):
                    raise ValueError(f'Both periods must be between 1 and {max_periods}.')
                if period_value > range_end:
                    raise ValueError('The range start must not be after the range end.')

            rule = GenPeriodPlacementRule(
                branch_id=gen_bid(),
                name=request.form.get('name', '').strip(),
                description=request.form.get('description', '').strip() or None,
                subject_id=int(request.form.get('subject_id')),
                class_name=request.form.get('class_name'),
                arm_name=request.form.get('arm_name') or None,
                rule_type=rule_type,
                period_value=period_value,
                range_end=range_end,
                is_active=True
            )
            if not rule.name:
                raise ValueError('Rule name is required.')
            db.session.add(rule)
            db.session.commit()
            flash('Period-placement rule added successfully', 'success')
            return redirect(url_for('generator.clash_rules_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding rule: {str(e)}', 'error')

    subjects = GenSubject.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenSubject.name).all()
    classes = GenClassConfig.query.filter_by(is_active=True, school_level=level, branch_id=gen_bid()).order_by(GenClassConfig.class_name).all()

    return render_template('generator/add_period_placement_rule.html',
        subjects=subjects,
        classes=classes,
        max_periods=max_periods
    )


@generator_bp.route('/period-placement-rules/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_period_placement_rule(rule_id):
    """Toggle a period-placement rule active/inactive"""
    from models import GenPeriodPlacementRule

    rule = gen_owned_or_404(GenPeriodPlacementRule, rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()

    status = 'activated' if rule.is_active else 'deactivated'
    flash(f'Rule {status}', 'success')
    return redirect(url_for('generator.clash_rules_list'))


@generator_bp.route('/period-placement-rules/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_period_placement_rule(rule_id):
    """Delete a period-placement rule"""
    from models import GenPeriodPlacementRule

    rule = gen_owned_or_404(GenPeriodPlacementRule, rule_id)
    db.session.delete(rule)
    db.session.commit()

    flash('Rule deleted', 'success')
    return redirect(url_for('generator.clash_rules_list'))
