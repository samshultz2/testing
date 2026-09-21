"""Timetable generator: day-separation rules keep a subject off two named
days of the week together, for one class(-arm) — e.g. SSS1 Rose's Physics
can be on Monday or Friday, never both in the same week."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenSubjectConfig, GenClassSubjectConfig, GenDaySeparationRule, GenTimetableResult,
    GenTeacherAvailability, GenTimetableRule,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _post(c, url, follow_redirects=False, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data, follow_redirects=follow_redirects)


def _build_class(app, tag, periods_per_week=3):
    """One class, one arm, one subject with a dedicated teacher — the exact
    SSS1 Rose + Physics scenario from the feature request. `tag` keeps names
    unique across tests sharing one session-scoped DB. Returns
    (class_config_id, subject_id)."""
    with app.app_context():
        bid = Branch.get_default().id

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzSSS1{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzRose{tag}')
        subj = GenSubject(branch_id=bid, name=f'ZzPhysics{tag}', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()

        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=subj.id, school_level='sss',
                                        periods_per_week=periods_per_week))
        # Non-streamed class: a subject only counts toward it via an explicit
        # per-class enable row (global GenSubjectConfig alone isn't enough).
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True,
                                             periods_per_week=periods_per_week))

        teacher = GenTeacher(branch_id=bid, name=f'Zz Physics Teacher{tag}', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzRose{tag}'))
        db.session.commit()
        return cc.id, subj.id


def test_day_separation_rule_model_and_routes(app):
    cc_id, subj_id = _build_class(app, 'A')
    c = _admin(app)

    r = _post(c, '/generator/day-separation-rules/add', name='ZzPhysicsMonFri',
             subject_id=subj_id, class_name='ZzSSS1A', arm_name='ZzRoseA',
             day_a='0', day_b='4')
    assert r.status_code in (302, 200)

    with app.app_context():
        rule = GenDaySeparationRule.query.filter_by(name='ZzPhysicsMonFri').first()
        assert rule is not None
        assert rule.is_active
        assert rule.class_name == 'ZzSSS1A' and rule.arm_name == 'ZzRoseA'
        assert rule.day_a == 0 and rule.day_b == 4
        assert rule.day_a_name == 'Monday' and rule.day_b_name == 'Friday'
        rule_id = rule.id

    listing = c.get('/generator/clash-rules')
    assert listing.status_code == 200
    assert b'ZzPhysicsMonFri' in listing.data
    assert b'Monday' in listing.data and b'Friday' in listing.data

    r2 = _post(c, f'/generator/day-separation-rules/{rule_id}/toggle')
    assert r2.status_code in (302, 200)
    with app.app_context():
        assert GenDaySeparationRule.query.get(rule_id).is_active is False

    r3 = _post(c, f'/generator/day-separation-rules/{rule_id}/delete')
    assert r3.status_code in (302, 200)
    with app.app_context():
        assert GenDaySeparationRule.query.get(rule_id) is None


def test_add_rule_rejects_same_day_twice(app):
    cc_id, subj_id = _build_class(app, 'B')
    c = _admin(app)
    r = _post(c, '/generator/day-separation-rules/add', name='ZzBadRule',
             subject_id=subj_id, class_name='ZzSSS1B', arm_name='ZzRoseB',
             day_a='2', day_b='2')
    assert r.status_code in (302, 200)
    with app.app_context():
        assert GenDaySeparationRule.query.filter_by(name='ZzBadRule').first() is None


def test_add_rule_arm_optional_means_every_arm(app):
    cc_id, subj_id = _build_class(app, 'C')
    c = _admin(app)
    r = _post(c, '/generator/day-separation-rules/add', name='ZzAllArmsRule',
             subject_id=subj_id, class_name='ZzSSS1C', arm_name='',
             day_a='1', day_b='3')
    assert r.status_code in (302, 200)
    with app.app_context():
        rule = GenDaySeparationRule.query.filter_by(name='ZzAllArmsRule').first()
        assert rule is not None and rule.arm_name is None


def test_solver_never_places_subject_on_both_separated_days(app):
    """The actual feature request: with 3 periods/week (well under the 5-day
    week), the solver must never land Physics on both Monday and Friday —
    only one of the two, or neither, is allowed each week."""
    cc_id, subj_id = _build_class(app, 'D', periods_per_week=3)

    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenDaySeparationRule(
            branch_id=bid, name='ZzMonFriD', subject_id=subj_id,
            class_name='ZzSSS1D', arm_name='ZzRoseD', day_a=0, day_b=4, is_active=True))
        db.session.commit()

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6')
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id, arm_name='ZzRoseD') \
            .order_by(GenTimetableResult.batch_id.desc()).all()
        assert rows, 'no timetable rows saved — generation likely failed; check flash message'
        batch_id = rows[0].batch_id
        batch_rows = [row for row in rows if row.batch_id == batch_id]
        assert len(batch_rows) == 3

        days_used = {row.day_of_week for row in batch_rows}
        assert not ({0, 4} <= days_used), (
            f'Physics should never land on both Monday (0) and Friday (4) in the same '
            f'week, got days {sorted(days_used)}')


def test_solver_respects_inactive_rule_by_ignoring_it(app):
    """A deactivated rule shouldn't constrain the solver at all — this just
    confirms toggling off actually stops it being read (no assertion on the
    resulting days, since without the rule Mon+Fri together is fine)."""
    cc_id, subj_id = _build_class(app, 'E', periods_per_week=3)

    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenDaySeparationRule(
            branch_id=bid, name='ZzInactiveRuleE', subject_id=subj_id,
            class_name='ZzSSS1E', arm_name='ZzRoseE', day_a=0, day_b=4, is_active=False))
        db.session.commit()

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6')
    assert r.status_code == 302

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id, arm_name='ZzRoseE').all()
        assert rows, 'no timetable rows saved — generation likely failed; check flash message'


def test_generation_cleanly_reports_infeasible_rule_instead_of_crashing(app):
    """A subject needing a period on EVERY school day (5/week) can never
    honour a Monday/Friday separation — that's structurally impossible, and
    the pre-solve diagnostic should say so by name instead of the request
    hanging or crashing."""
    cc_id, subj_id = _build_class(app, 'F', periods_per_week=5)

    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenDaySeparationRule(
            branch_id=bid, name='ZzImpossibleRuleF', subject_id=subj_id,
            class_name='ZzSSS1F', arm_name='ZzRoseF', day_a=0, day_b=4, is_active=True))
        db.session.commit()

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'ZzImpossibleRuleF' in body
    assert 'Monday' in body and 'Friday' in body

    with app.app_context():
        # Nothing got saved for this doomed batch — the diagnostic caught it
        # before any solve (and thus before any result rows) happened.
        assert GenTimetableResult.query.filter_by(subject_id=subj_id, arm_name='ZzRoseF').count() == 0


def _build_double_period_class(app, tag, teacher_days=None):
    """One class/arm/subject needing a single double period (2 periods,
    same day) each week. `teacher_days`, if given, restricts the teacher to
    only those day-of-week indices (0=Monday..4=Friday) — used to force the
    solver into a specific corner of the week. Returns (class_config_id,
    subject_id)."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZDbl{tag}', school_level='sss', num_arms=1,
                            arm_names=f'ZDblArm{tag}')
        subj = GenSubject(branch_id=bid, name=f'ZDblChem{tag}', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()
        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=subj.id, school_level='sss',
                                        periods_per_week=2, needs_double_period=True, double_period_count=1))
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id, is_enabled=True,
                                             is_active=True, periods_per_week=2,
                                             needs_double_period=True, double_period_count=1))
        teacher = GenTeacher(branch_id=bid, name=f'ZDblTeacher{tag}', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZDblArm{tag}'))
        if teacher_days is not None:
            # `periods_per_day` posted to /generate/ortools is actually
            # ignored — the route reads it from GenTimetableRule instead
            # (defaulting to 8) — so match that instead of the posted value.
            rule = GenTimetableRule.query.filter_by(rule_type='periods_per_day', is_active=True).first()
            actual_periods_per_day = int(rule.value) if rule and str(rule.value).isdigit() else 8
            for day in range(5):
                for period in range(1, actual_periods_per_day + 1):
                    if day not in teacher_days:
                        db.session.add(GenTeacherAvailability(teacher_id=teacher.id, day_of_week=day,
                                                              period_number=period, is_available=False))
        db.session.commit()
        return cc.id, subj.id


def test_double_period_may_land_on_a_separated_day_alone(app):
    """A double period (2 periods, same day) on ONE of the two separated
    days must NOT itself count as violating the rule — that would wrongly
    treat "2 periods on day A" the same as "on both day A and day B". Force
    the teacher to only be available on Monday (one of the default Mon/Fri
    separated days) so the double period MUST land there; generation should
    still succeed."""
    cc_id, subj_id = _build_double_period_class(app, 'G', teacher_days={0})

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        assert len(rows) == 2, (
            f'expected the double period to be placed on the only available day '
            f'(Monday), got {len(rows)} rows: check the flash message on failure')
        assert {row.day_of_week for row in rows} == {0}


def test_default_policy_still_forbids_both_separated_days_with_a_double(app):
    """The flip side: a double-period subject whose teacher is ONLY available
    on the two separated days (Monday and Friday) together needs both of
    them to fit its 2 periods — the day-separation default must still block
    that, same as for single periods."""
    cc_id, subj_id = _build_double_period_class(app, 'H', teacher_days={0, 4})

    with app.app_context():
        # Make it truly need both days: a 2nd, non-doubled period that can
        # only go on the other separated day (teacher's only other slot).
        bid = Branch.get_default().id
        cfg = GenSubjectConfig.query.filter_by(subject_id=subj_id, school_level='sss').first()
        cfg.periods_per_week = 3   # double (2, one day) + 1 single (must be the other day)
        cc = GenClassConfig.query.filter_by(class_name='ZDblH', branch_id=bid).first()
        ov = GenClassSubjectConfig.query.filter_by(class_config_id=cc.id, subject_id=subj_id).first()
        ov.periods_per_week = 3
        db.session.commit()

    c = _admin(app)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        # Genuinely impossible (needs both Monday and Friday, which the rule
        # forbids together) — must fail cleanly, not silently place partial
        # or invalid rows.
        assert not rows, (
            f'expected generation to fail cleanly (both separated days are '
            f'needed and forbidden together), but got {len(rows)} saved rows')

