"""generator_bp — unified per-subject rules editor.

One screen to configure everything about how a subject behaves in the timetable,
instead of hunting across three pages (global subject grid, per-class grid, and
the whole-timetable rules page). It reads/writes the SAME models the generator
already uses (GenSubjectConfig for the defaults, GenClassSubjectConfig for the
per-class overrides, GenTimetableRule for the shared back-to-back limit) — so the
generated timetable is identical, just far easier to set up.
"""
from routes.generator import *  # noqa: F401,F403


def _max_consecutive(level):
    r = GenTimetableRule.query.filter_by(rule_type='max_consecutive', school_level=level, branch_id=gen_bid()).first()
    return int(r.value) if r and str(r.value).isdigit() else 3


@generator_bp.route('/subject/<int:subject_id>/rules')
@login_required
def subject_rules(subject_id):
    subject = gen_owned_or_404(GenSubject, subject_id)
    level = subject.school_level
    cfg = GenSubjectConfig.query.filter_by(subject_id=subject_id, school_level=level).first()
    classes = (GenClassConfig.query.filter_by(is_active=True, school_level=level,
                                              branch_id=subject.branch_id)
               .order_by(GenClassConfig.class_name).all())
    overrides = {c.class_config_id: c for c in GenClassSubjectConfig.query.filter_by(
        subject_id=subject_id, is_active=True).all()}

    default_periods = cfg.periods_per_week if cfg else 4
    class_rows = []
    for cc in classes:
        ov = overrides.get(cc.id)
        class_rows.append({
            'cc': cc, 'arms': cc.arm_list, 'has_override': ov is not None,
            'enabled': (ov.is_enabled if ov else True),
            'periods': (ov.periods_per_week if ov else default_periods),
            'double': (ov.needs_double_period if ov else (cfg.needs_double_period if cfg else False)),
            'double_count': (ov.double_period_count if ov else (cfg.double_period_count if cfg else 0)),
        })
    return render_template('generator/subject_rules.html',
                           subject=subject, cfg=cfg, level=level, class_rows=class_rows,
                           default_periods=default_periods,
                           max_consecutive=_max_consecutive(level))


@generator_bp.route('/subject/<int:subject_id>/rules/save', methods=['POST'])
@login_required
def save_subject_rules(subject_id):
    subject = gen_owned_or_404(GenSubject, subject_id)
    level = subject.school_level
    f = request.form
    try:
        # 1) Defaults (apply to every class unless a class overrides below)
        d_periods = f.get('periods', type=int) or 4
        d_double = f.get('double') == 'on'
        d_double_count = f.get('double_count', type=int) or 0
        data = {
            'periods_per_week': d_periods,
            'needs_double_period': d_double,
            'double_period_count': d_double_count if d_double else 0,
            'preferred_time': f.get('preferred', 'any'),
            'not_first_period': f.get('not_first') == 'on',
            'not_last_period': f.get('not_last') == 'on',
            'is_active': True,
        }
        cfg = GenSubjectConfig.query.filter_by(subject_id=subject_id, school_level=level).first()
        if cfg:
            for k, v in data.items():
                setattr(cfg, k, v)
        else:
            db.session.add(GenSubjectConfig(subject_id=subject_id, school_level=level, branch_id=subject.branch_id, **data))

        # 2) Per-class rows: "use default" removes the override; else upsert it.
        for cid in f.getlist('class_id[]'):
            cid = int(cid)
            existing = GenClassSubjectConfig.query.filter_by(
                class_config_id=cid, subject_id=subject_id).first()
            if f.get(f'default_{cid}') == 'on':
                if existing:
                    db.session.delete(existing)         # inherit the defaults again
                continue
            enabled = f.get(f'enabled_{cid}') == 'on'
            periods = f.get(f'periods_{cid}', type=int) or d_periods
            c_double = f.get(f'double_{cid}') == 'on'
            c_double_count = f.get(f'double_count_{cid}', type=int) or 0
            if existing:
                existing.is_enabled = enabled
                existing.periods_per_week = periods
                existing.needs_double_period = c_double
                existing.double_period_count = c_double_count if c_double else 0
                existing.is_active = True
            else:
                db.session.add(GenClassSubjectConfig(
                    class_config_id=cid, subject_id=subject_id, is_enabled=enabled,
                    periods_per_week=periods, needs_double_period=c_double,
                    double_period_count=c_double_count if c_double else 0, is_active=True))

        # 3) The shared back-to-back limit (whole timetable) — edited here for
        #    convenience; same effect as the Rules page.
        mc = f.get('max_consecutive', type=int)
        if mc:
            rule = GenTimetableRule.query.filter_by(
                rule_type='max_consecutive', school_level=level, branch_id=gen_bid()).first()
            if rule:
                rule.value = str(mc); rule.is_active = True
            else:
                db.session.add(GenTimetableRule(rule_type='max_consecutive',
                                                value=str(mc), school_level=level, is_active=True, branch_id=gen_bid()))

        db.session.commit()
        flash(f'Saved all rules for {subject.name}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {e}', 'error')
    return redirect(url_for('generator.subject_rules', subject_id=subject_id))
