"""Timetable generator: when OR-Tools genuinely can't find a schedule and
none of the configurable rules are active, the failure message should name
the likely bottleneck (teachers running closest to their capacity) instead
of pointing at rules that were never on — a school hitting this after
multiplying a class's arms had no obvious next step otherwise."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenSubjectConfig, GenClassSubjectConfig, GenTimetableRule,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _build_contended_scenario(app, tag):
    """2 class levels x 5 arms each, with a dedicated teacher per
    (level, subject) covering every arm of that level (arm_name=None) at
    exactly their weekly cap — individually within every simple capacity
    check, but collectively too tightly packed for the solver to interleave.
    Mirrors multiplying a class's arm count without adding staff."""
    with app.app_context():
        bid = Branch.get_default().id

        db.session.add(GenTimetableRule(rule_type='periods_per_day', value='8',
                                        school_level='sss', is_active=True, branch_id=bid))
        db.session.add(GenTimetableRule(rule_type='break_after_period', value='4',
                                        school_level='sss', is_active=True, branch_id=bid))
        # Explicitly off, same as "disabled all rules" in the report this guards.
        db.session.add(GenTimetableRule(rule_type='day_separation_enabled', value='false',
                                        school_level='sss', is_active=True, branch_id=bid))
        db.session.add(GenTimetableRule(rule_type='first_period_no_repeat', value='false',
                                        school_level='sss', is_active=True, branch_id=bid))

        subject_names = ['Maths', 'English', 'Physics', 'Chem', 'Bio', 'Govt']
        subjects = []
        for sname in subject_names:
            s = GenSubject(branch_id=bid, name=f'{tag}{sname}', school_level='sss')
            db.session.add(s)
            subjects.append(s)
        db.session.flush()
        for s in subjects:
            db.session.add(GenSubjectConfig(branch_id=bid, subject_id=s.id, school_level='sss',
                                            periods_per_week=6))

        class_ids = []
        for level in ('SSS1', 'SSS2'):
            cc = GenClassConfig(branch_id=bid, class_name=f'{tag}{level}', school_level='sss',
                                num_arms=5, arm_names=','.join(f'{tag}Arm{i}' for i in range(5)))
            db.session.add(cc)
            db.session.flush()
            class_ids.append(cc.id)
            for s in subjects:
                db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=s.id,
                                                     is_enabled=True, is_active=True,
                                                     periods_per_week=6))
                # 5 arms * 6 periods/week = 30 = exactly this teacher's cap.
                t = GenTeacher(branch_id=bid, name=f'{tag}_{level}_{s.name}', school_level='sss',
                               max_periods_per_day=6, max_periods_per_week=30)
                db.session.add(t)
                db.session.flush()
                db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id,
                                                    subject_id=s.id, class_config_id=cc.id,
                                                    arm_name=None))
        db.session.commit()
        return class_ids


def test_infeasible_with_no_active_rules_names_the_bottleneck_teachers(app):
    class_ids = _build_contended_scenario(app, 'ZzIDG')
    try:
        c = _admin(app)
        r = c.post('/generator/generate/ortools', follow_redirects=True, data={
            '_csrf_token': 'a' * 64,
            'class_ids[]': [str(i) for i in class_ids],
            'time_limit': '30',
        })
        assert r.status_code == 200
        body = r.data.decode('utf-8', errors='replace')
        assert 'Generation failed' in body
        # The old generic message ("finer scheduling rules being too tight") is
        # actively misleading with nothing to relax — the new one must instead
        # name a concrete, checkable lead: which teachers are near their cap.
        assert 'bottleneck' in body
        assert 'ZzIDG_SSS1_ZzIDGMaths' in body or 'ZzIDG_SSS2_ZzIDGMaths' in body
        assert '30/30 periods/week' in body
        assert '5 class-arms' in body
    finally:
        # day_separation_enabled/first_period_no_repeat are branch+level-wide
        # toggles, not scoped to this test's own classes — leaving them
        # "false" would silently disable those features for every other
        # sss-level generator test that runs after this one in the shared
        # session-scoped test DB.
        with app.app_context():
            bid = Branch.get_default().id
            GenTimetableRule.query.filter(
                GenTimetableRule.rule_type.in_(
                    ['day_separation_enabled', 'first_period_no_repeat']),
                GenTimetableRule.school_level == 'sss',
                GenTimetableRule.branch_id == bid,
            ).delete(synchronize_session=False)
            db.session.commit()
