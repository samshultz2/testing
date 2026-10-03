"""Per-class exception to the day-separation subject picker (Rules page).
The subject-level choice (GenSubjectConfig.day_separation_exempt) decides a
subject's day-separation status across every class; GenClassSubjectConfig.
day_separation_exempt, when not NULL, overrides that choice for one class in
either direction -- e.g. a subject included school-wide but exempted for one
specific class, or vice versa. Configured from the Rules page itself via
/generator/rules/day-separation-class-override."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenSubjectConfig, GenClassSubjectConfig, GenTimetableRule, GenTimetableResult,
    GenTeacherAvailability,
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


def _scoped_to_branch(c, branch_id):
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def _build_needs_both_days_fixture(app, tag, subject_exempt_at_subject_level):
    """One branch, one subject (configured at the subject level per
    `subject_exempt_at_subject_level`), and one class/arm/teacher whose only
    available slots are the default separated days (Monday/Friday), needing
    both to fit periods_per_week=2. Returns (class_config_id, subject_id,
    branch_id)."""
    with app.app_context():
        b = Branch(name=f'ZzDaySepClassOv{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value='6',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value='3',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_enabled', value='true',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_day_a', value='0',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_day_b', value='4',
                             school_level='sss', is_active=True),
        ])

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzDSCls{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}')
        subj = GenSubject(branch_id=bid, name=f'ZzDSSubj{tag}', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()

        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=subj.id, school_level='sss',
                                        periods_per_week=2,
                                        day_separation_exempt=subject_exempt_at_subject_level))
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=2))

        teacher = GenTeacher(branch_id=bid, name=f'ZzDSTeacher{tag}', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzArm{tag}'))
        for day in range(5):
            if day in (0, 4):
                continue
            for period in range(1, 7):
                db.session.add(GenTeacherAvailability(teacher_id=teacher.id, day_of_week=day,
                                                      period_number=period, is_available=False))
        db.session.commit()
        return cc.id, subj.id, bid


def test_class_override_exempts_one_class_despite_subject_level_inclusion(app):
    """Subject is included school-wide (day_separation_exempt=False), but
    this one class has an explicit per-class override exempting it -- the
    class's need for both separated days must no longer be a problem."""
    cc_id, subj_id, bid = _build_needs_both_days_fixture(
        app, 'Exempt', subject_exempt_at_subject_level=False)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        row.day_separation_exempt = True
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        assert rows, 'per-class override should have exempted this class -- generation should succeed'
        assert len(rows) == 2
        assert {row.day_of_week for row in rows} == {0, 4}


def test_class_override_includes_one_class_despite_subject_level_exemption(app):
    """Subject is exempt school-wide, but this one class has an explicit
    per-class override including it -- the class's need for both separated
    days must now fail cleanly."""
    cc_id, subj_id, bid = _build_needs_both_days_fixture(
        app, 'Include', subject_exempt_at_subject_level=True)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        row.day_separation_exempt = False
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        assert not rows, (
            f'per-class override included this class -- generation should fail cleanly, '
            f'got {len(rows)} saved rows')


def test_clearing_override_falls_back_to_subject_level_default(app):
    """An 'inherit' override clears the per-class NULL back out -- the class
    then follows whatever the subject-level default says, same as if no
    override had ever been set."""
    cc_id, subj_id, bid = _build_needs_both_days_fixture(
        app, 'Clear', subject_exempt_at_subject_level=False)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        row.day_separation_exempt = True  # exempt this class for now
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/rules/day-separation-class-override',
             subject_id=subj_id, class_id=cc_id, choice='inherit')
    assert r.status_code in (302, 200)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        assert row.day_separation_exempt is None

    # Subject-level default is "included" -- needing both days must fail again.
    r2 = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
              time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r2.status_code == 200
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(subject_id=subj_id).all()
        assert not rows, 'clearing the override should fall back to the included subject-level default'


def test_route_creates_updates_and_clears_override_row(app):
    bid = None
    with app.app_context():
        b = Branch(name='ZzDaySepOvRoute', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        subj = GenSubject(branch_id=bid, name='ZzOvRouteSubj', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzOvRouteCls', school_level='sss',
                            num_arms=1, arm_names='ZzOvArm')
        db.session.add_all([subj, cc]); db.session.flush()
        subj_id, cc_id = subj.id, cc.id
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)

    # No row exists yet -- 'exempt' creates one.
    r = _post(c, '/generator/rules/day-separation-class-override',
             subject_id=subj_id, class_id=cc_id, choice='exempt')
    assert r.status_code in (302, 200)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        assert row is not None and row.day_separation_exempt is True

    # Flip it to 'include' -- updates the same row.
    r = _post(c, '/generator/rules/day-separation-class-override',
             subject_id=subj_id, class_id=cc_id, choice='include')
    assert r.status_code in (302, 200)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        assert row is not None and row.day_separation_exempt is False

    # 'inherit' clears it back to NULL (row stays, since periods_per_week etc.
    # may still live on it, but the override itself is gone).
    r = _post(c, '/generator/rules/day-separation-class-override',
             subject_id=subj_id, class_id=cc_id, choice='inherit')
    assert r.status_code in (302, 200)
    with app.app_context():
        row = GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=subj_id).first()
        assert row is not None and row.day_separation_exempt is None


def test_route_rejects_invalid_choice_and_unknown_ids(app):
    bid = None
    with app.app_context():
        b = Branch(name='ZzDaySepOvBad', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        subj = GenSubject(branch_id=bid, name='ZzOvBadSubj', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzOvBadCls', school_level='sss',
                            num_arms=1, arm_names='ZzOvBadArm')
        db.session.add_all([subj, cc]); db.session.flush()
        subj_id, cc_id = subj.id, cc.id
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)

    r = _post(c, '/generator/rules/day-separation-class-override',
             subject_id=subj_id, class_id=cc_id, choice='bogus', follow_redirects=True)
    assert r.status_code == 200
    assert b'Pick Apply, Exempt, or Inherit' in r.data or b'Error' in r.data

    r = _post(c, '/generator/rules/day-separation-class-override',
             subject_id=999999, class_id=cc_id, choice='exempt', follow_redirects=True)
    assert r.status_code == 200

    with app.app_context():
        assert GenClassSubjectConfig.query.filter_by(class_config_id=cc_id, subject_id=999999).count() == 0


def test_rules_page_lists_class_overrides(app):
    bid = None
    with app.app_context():
        b = Branch(name='ZzDaySepOvList', code=None)
        db.session.add(b); db.session.flush(); bid = b.id
        subj = GenSubject(branch_id=bid, name='ZzOvListSubj', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzOvListCls', school_level='sss',
                            num_arms=1, arm_names='ZzOvListArm')
        db.session.add_all([subj, cc]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             day_separation_exempt=True))
        db.session.commit()

    c = _scoped_to_branch(_admin(app), bid)
    body = c.get('/generator/rules').get_data(as_text=True)
    assert 'ZzOvListSubj' in body and 'ZzOvListCls' in body
    assert 'Exempt (off)' in body
