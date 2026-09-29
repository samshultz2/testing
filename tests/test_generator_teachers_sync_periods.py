"""Timetable generator: /generator/teachers "Sync from Assignments" -- set a
selected teacher's max periods/week to their REAL workload computed from
/generator/assignments (periods/week per stream for classes with streams,
per arm for classes without), not a manually-typed number."""
from config import Config
from models import (db, Branch, GenTeacher, GenTimetableRule, GenSubject, GenClassConfig,
                     GenClassSubjectConfig, GenTeacherAssignment, GenStream, GenStreamSubject,
                     GenClassArmStream)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _seed_teacher(app, tag, max_week=30, max_day=6, available_days='0,1,2,3,4'):
    with app.app_context():
        bid = Branch.get_default().id
        t = GenTeacher(branch_id=bid, name=f'Zz SyncTeacher{tag}', school_level='sss',
                       max_periods_per_day=max_day, max_periods_per_week=max_week,
                       available_days=available_days)
        db.session.add(t); db.session.commit()
        return t.id


def _seed_periods_per_day_rule(app, value=10):
    with app.app_context():
        bid = Branch.get_default().id
        db.session.add(GenTimetableRule(branch_id=bid, rule_type='periods_per_day',
                                        value=str(value), school_level='sss'))
        db.session.commit()


def test_teachers_page_has_sync_controls(app):
    _seed_teacher(app, 'UI')
    c = _admin(app)
    r = c.get('/generator/teachers')
    body = r.get_data(as_text=True)
    assert 'bulk_sync_teacher_periods' in body or 'bulkSyncForm' in body
    assert 'Sync from Assignments' in body
    assert '/generator/assignments' in body


def test_sync_no_streams_class_specific_arm(app):
    """No streams: one arm assigned -> periods/week comes straight from the
    class-subject config, counted once (one arm)."""
    _seed_periods_per_day_rule(app, value=10)
    tid = _seed_teacher(app, 'A', max_week=99, max_day=99)
    with app.app_context():
        bid = Branch.get_default().id
        subj = GenSubject(branch_id=bid, name='ZzSyncMaths', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzSyncSSS1', school_level='sss',
                            num_arms=2, arm_names='Gold,Silver', has_streams=False)
        db.session.add_all([subj, cc]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, periods_per_week=5))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=tid, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name='Gold'))
        db.session.commit()

    c = _admin(app)
    r = c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid)],
    })
    assert r.status_code == 200
    assert 'Synced' in r.get_data(as_text=True)
    with app.app_context():
        t = db.session.get(GenTeacher, tid)
        assert t.max_periods_per_week == 5


def test_sync_no_streams_class_all_arms_multiplies_by_arm_count(app):
    """No streams, arm_name=None ("all arms"): the teacher takes each of the
    class's arms as its own session, so periods/week is the per-arm amount
    TIMES the number of arms -- exactly 'periods per arm of class' from the
    request."""
    _seed_periods_per_day_rule(app, value=20)
    tid = _seed_teacher(app, 'B', max_week=99, max_day=99)
    with app.app_context():
        bid = Branch.get_default().id
        subj = GenSubject(branch_id=bid, name='ZzSyncEnglish', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzSyncSSS2', school_level='sss',
                            num_arms=3, arm_names='Red,Blue,Green', has_streams=False)
        db.session.add_all([subj, cc]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, periods_per_week=4))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=tid, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=None))
        db.session.commit()

    c = _admin(app)
    c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid)],
    })
    with app.app_context():
        assert db.session.get(GenTeacher, tid).max_periods_per_week == 12   # 4 periods x 3 arms


def test_sync_with_streams_sums_each_arms_own_stream_periods(app):
    """Has streams, arm_name=None: two arms in two different streams, each
    stream giving Chemistry a DIFFERENT periods/week -- total is the sum of
    each arm's own stream figure, not a single shared number."""
    _seed_periods_per_day_rule(app, value=20)
    tid = _seed_teacher(app, 'C', max_week=99, max_day=99)
    with app.app_context():
        bid = Branch.get_default().id
        subj = GenSubject(branch_id=bid, name='ZzSyncChemistry', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzSyncSSS3', school_level='sss',
                            num_arms=2, arm_names='Science,Arts', has_streams=True)
        sci = GenStream(branch_id=bid, name='ZzSyncScienceStream', school_level='sss')
        arts = GenStream(branch_id=bid, name='ZzSyncArtsStream', school_level='sss')
        db.session.add_all([subj, cc, sci, arts]); db.session.flush()
        db.session.add_all([
            GenClassArmStream(class_config_id=cc.id, arm_name='Science', stream_id=sci.id),
            GenClassArmStream(class_config_id=cc.id, arm_name='Arts', stream_id=arts.id),
            GenStreamSubject(stream_id=sci.id, subject_id=subj.id, periods_per_week=6),
            GenStreamSubject(stream_id=arts.id, subject_id=subj.id, periods_per_week=2),
        ])
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=tid, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=None))
        db.session.commit()

    c = _admin(app)
    c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid)],
    })
    with app.app_context():
        assert db.session.get(GenTeacher, tid).max_periods_per_week == 8   # 6 (Science) + 2 (Arts)


def test_sync_sums_across_multiple_assignments_and_recalculates_day(app):
    """Two separate assignments for the same teacher (different subjects) add
    up, and max periods/day is recalculated from the new week total the same
    way the manual bulk-increase does."""
    _seed_periods_per_day_rule(app, value=10)
    tid = _seed_teacher(app, 'D', max_week=99, max_day=99, available_days='0,1,2,3,4')
    with app.app_context():
        bid = Branch.get_default().id
        s1 = GenSubject(branch_id=bid, name='ZzSyncPhysics', school_level='sss')
        s2 = GenSubject(branch_id=bid, name='ZzSyncBiology', school_level='sss')
        cc = GenClassConfig(branch_id=bid, class_name='ZzSyncSSS4', school_level='sss',
                            num_arms=1, arm_names='Only', has_streams=False)
        db.session.add_all([s1, s2, cc]); db.session.flush()
        db.session.add_all([
            GenClassSubjectConfig(class_config_id=cc.id, subject_id=s1.id, is_enabled=True, periods_per_week=10),
            GenClassSubjectConfig(class_config_id=cc.id, subject_id=s2.id, is_enabled=True, periods_per_week=10),
        ])
        db.session.add_all([
            GenTeacherAssignment(branch_id=bid, teacher_id=tid, subject_id=s1.id, class_config_id=cc.id, arm_name='Only'),
            GenTeacherAssignment(branch_id=bid, teacher_id=tid, subject_id=s2.id, class_config_id=cc.id, arm_name='Only'),
        ])
        db.session.commit()

    c = _admin(app)
    c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid)],
    })
    with app.app_context():
        t = db.session.get(GenTeacher, tid)
        assert t.max_periods_per_week == 20        # 10 + 10
        assert t.max_periods_per_day == 4            # ceil(20/5)=4, well under the cap of 10


def test_sync_skips_teacher_with_no_assignments(app):
    """A selected teacher with no active assignments has nothing to sync to --
    left unchanged, not zeroed, and reported as skipped."""
    tid = _seed_teacher(app, 'E', max_week=17, max_day=3)
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64, 'teacher_ids[]': [str(tid)],
    })
    assert 'Skipped 1' in r.get_data(as_text=True)
    with app.app_context():
        t = db.session.get(GenTeacher, tid)
        assert t.max_periods_per_week == 17
        assert t.max_periods_per_day == 3


def test_sync_with_no_selection_flashes_error(app):
    c = _admin(app)
    r = c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': 'a' * 64,
    })
    assert 'Select at least one teacher' in r.get_data(as_text=True)


def test_sync_skips_ids_from_another_branch(app):
    from models import User

    with app.app_context():
        other = Branch(name='ZzSyncOtherBranch', is_default=False)
        db.session.add(other); db.session.flush()
        u = User(username='zzsync_branch_admin', full_name='Zz Sync Branch Admin', role='admin',
                 scope='branch', branch_id=other.id, rank=50, manage_scope='branch',
                 is_active=True, must_change_password=False)
        u.set_password('Str0ng!Passw0rd1')
        other_teacher = GenTeacher(branch_id=other.id, name='Zz Other Sync Teacher', school_level='sss',
                                   max_periods_per_day=6, max_periods_per_week=30, available_days='0,1,2,3,4')
        subj = GenSubject(branch_id=other.id, name='ZzSyncOtherSubj', school_level='sss')
        cc = GenClassConfig(branch_id=other.id, class_name='ZzSyncOtherClass', school_level='sss',
                            num_arms=1, arm_names='Only', has_streams=False)
        db.session.add_all([u, other_teacher, subj, cc]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, periods_per_week=7))
        db.session.add(GenTeacherAssignment(branch_id=other.id, teacher_id=other_teacher.id,
                                            subject_id=subj.id, class_config_id=cc.id, arm_name='Only'))
        db.session.commit()
        other_bid = other.id
        other_tid = other_teacher.id
        db.session.add(GenTimetableRule(branch_id=other_bid, rule_type='periods_per_day',
                                        value='10', school_level='sss'))
        db.session.commit()

    own_tid = _seed_teacher(app, 'F', max_week=30, max_day=6)

    c = app.test_client()
    c.post('/login', data={'username': 'zzsync_branch_admin', 'password': 'Str0ng!Passw0rd1',
                           '_csrf_token': login_token(c)})
    from tests.conftest import auth_csrf
    r = c.post('/generator/teachers/bulk-sync-periods', follow_redirects=True, data={
        '_csrf_token': auth_csrf(c), 'teacher_ids[]': [str(other_tid), str(own_tid)],
    })
    assert r.status_code == 200

    with app.app_context():
        assert db.session.get(GenTeacher, other_tid).max_periods_per_week == 7
        assert db.session.get(GenTeacher, own_tid).max_periods_per_week == 30
