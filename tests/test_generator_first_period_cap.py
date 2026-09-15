"""Timetable generator: a subject with more than one period/week can open
the school day (period 1) on at most one day per week — once Geography has
taken SSS2 Lily's Monday P1, its other periods that week can't repeat as
another day's P1. Doesn't apply to subjects already fully banned from
period 1 by the existing not_first_period rule (nothing to cap)."""
from config import Config
from models import (
    db, Branch, GenClassConfig, GenSubject, GenClassSubjectConfig, GenTeacher,
    GenTeacherAssignment, GenTeacherAvailability, GenTimetableResult, GenTimetableRule,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data)


def _build_class_with_p1_only_teacher(app, tag, extra_available_period=None, periods_per_week=2):
    """One class-arm, one subject needing `periods_per_week` periods, taught
    by a teacher who is ONLY available at period 1, every day. If
    `extra_available_period` is given, it's also available but ONLY on
    Monday — a single extra slot, not one per day — so a 2-periods/week
    subject has exactly one non-period-1 option: it MUST use that one plus
    exactly one period-1 slot to be feasible at all, making "period 1 used
    exactly once" a forced, unambiguous signal rather than one of several
    equally valid solutions. Returns (class_config_id, subject_id)."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzSSS2{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzLily{tag}', has_streams=False)
        db.session.add(cc); db.session.flush()

        geo = GenSubject(branch_id=bid, name=f'ZzGeography{tag}', school_level='sss')
        db.session.add(geo); db.session.flush()

        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=geo.id, is_enabled=True,
            periods_per_week=periods_per_week))

        teacher = GenTeacher(branch_id=bid, name=f'Zz Geo Teacher{tag}', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()

        db.session.add(GenTeacherAssignment(
            branch_id=bid, teacher_id=teacher.id, subject_id=geo.id,
            class_config_id=cc.id, arm_name=f'ZzLily{tag}'))

        # run_ortools_generation() reads periods_per_day from the stored
        # GenTimetableRule config, not the request — it defaults to 8 when
        # unset, so block every period up to 8 regardless of what this test
        # later passes as a form field.
        for day in range(5):
            allowed_periods = {1}
            if extra_available_period and day == 0:
                allowed_periods.add(extra_available_period)
            for period in range(1, 9):
                if period not in allowed_periods:
                    db.session.add(GenTeacherAvailability(
                        teacher_id=teacher.id, day_of_week=day, period_number=period,
                        is_available=False))
        db.session.commit()
        return cc.id, geo.id


def test_first_period_repeat_is_infeasible_when_no_other_slot_exists(app):
    """The teacher can ONLY teach at period 1, and the subject needs 2
    periods/week. Without the first-period no-repeat cap, the solver would
    happily place both periods in two different days' period 1 (the only
    slots that satisfy teacher availability). With the cap, that's the only
    way to fit both periods and it's blocked — so this must be infeasible."""
    cc_id, geo_id = _build_class_with_p1_only_teacher(app, 'Q', periods_per_week=2)
    c = _admin(app)

    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='15', periods_per_day='6')
    assert r.status_code == 302

    with app.app_context():
        assert GenTimetableResult.query.filter_by(class_name='ZzSSS2Q').first() is None, \
            'expected generation to fail (no feasible placement), but results were saved'


def test_first_period_repeat_cap_holds_when_solution_exists(app):
    """Same setup, but the teacher also has period 3 open — so the subject's
    2 periods/week CAN be placed (period 1 once + period 3 once). Confirms
    the cap doesn't block a real solution, and that the result actually
    respects it (at most one of the subject's periods lands in period 1)."""
    cc_id, geo_id = _build_class_with_p1_only_teacher(app, 'R', extra_available_period=3,
                                                       periods_per_week=2)
    c = _admin(app)

    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='15', periods_per_day='6')
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2R', subject_id=geo_id).all()
        assert len(rows) == 2, 'expected the subject\'s 2 periods/week to be scheduled'
        first_period_count = sum(1 for row in rows if row.period_number == 1)
        assert first_period_count <= 1, (
            f'subject appeared in period 1 on {first_period_count} days — the '
            f'first-period no-repeat cap should limit this to at most 1')
        # And it must actually use period 1 once (period 3 is its only other
        # option), proving the cap isn't just coincidentally satisfied.
        assert first_period_count == 1
        assert any(row.period_number == 3 for row in rows)


def test_first_period_cap_skips_subjects_already_banned_from_period_one(app):
    """A subject marked not_first_period is already fully excluded from
    period 1 (existing Constraint 6) — the new cap should recognize that
    and not add a redundant/conflicting constraint for it."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name='ZzSSS2S', school_level='sss',
                            num_arms=1, arm_names='ZzLilyS', has_streams=False)
        db.session.add(cc); db.session.flush()

        from models import GenSubjectConfig
        maths = GenSubject(branch_id=bid, name='ZzMathsS', school_level='sss')
        db.session.add(maths); db.session.flush()
        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=maths.id, school_level='sss',
                                        periods_per_week=3, not_first_period=True))
        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=maths.id, is_enabled=True, periods_per_week=3))

        teacher = GenTeacher(branch_id=bid, name='Zz Maths TeacherS', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(
            branch_id=bid, teacher_id=teacher.id, subject_id=maths.id,
            class_config_id=cc.id, arm_name='ZzLilyS'))
        db.session.commit()
        cc_id = cc.id

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='15', periods_per_day='6')
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2S').all()
        assert len(rows) == 3
        assert all(row.period_number != 1 for row in rows)


def test_first_period_cap_is_togglable_off(app):
    """The exact scenario that's infeasible with the cap on (see
    test_first_period_repeat_is_infeasible_when_no_other_slot_exists) should
    succeed once the "first_period_no_repeat" rule is turned off — letting a
    school route around it without Claude/a developer's help."""
    cc_id, geo_id = _build_class_with_p1_only_teacher(app, 'T', periods_per_week=2)
    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenTimetableRule(
            branch_id=bid, rule_type='first_period_no_repeat', value='false',
            school_level='sss', is_active=True))
        db.session.commit()

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='15', periods_per_day='6')
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(class_name='ZzSSS2T', subject_id=geo_id).all()
        assert len(rows) == 2, 'expected generation to succeed once the cap is turned off'
        # With the cap off, both periods land in period 1 (the teacher's only
        # available slot) — confirming the toggle genuinely disabled the cap
        # rather than the solver happening to avoid the trap another way.
        assert all(row.period_number == 1 for row in rows)


def test_rules_config_saves_first_period_no_repeat_toggle(app):
    c = _admin(app)
    level = 'sss'
    with app.app_context():
        from utils.branch_scope import default_branch_id
        bid = default_branch_id()

    r = _post(c, '/generator/rules/save', first_period_no_repeat='')  # unchecked
    assert r.status_code == 302
    with app.app_context():
        rule = GenTimetableRule.query.filter_by(
            rule_type='first_period_no_repeat', school_level=level, branch_id=bid).first()
        assert rule is not None and rule.value == 'false'

    r2 = _post(c, '/generator/rules/save', first_period_no_repeat='on')
    assert r2.status_code == 302
    with app.app_context():
        rule2 = GenTimetableRule.query.filter_by(
            rule_type='first_period_no_repeat', school_level=level, branch_id=bid).first()
        assert rule2.value == 'true'
