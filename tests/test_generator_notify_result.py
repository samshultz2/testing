"""A timetable generation run's outcome (success or failure, either engine)
should be posted to the bell, not just a one-time flash message that's lost
if the admin navigates away before reading it -- gated by the
'generation_result' automation toggle, same pattern as every other
automated notification in utils/automations.py."""
from config import Config
from models import db, Branch, GenTimetableRule, GenTimetableResult, Notification, User
from tests.conftest import login_token
from tests.test_generator_day_separation_opt_in import _build_needs_both_days_class


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


def _add_branch_admin(bid, username):
    """notify_branch_admins() addresses real admin User rows individually, not
    a role broadcast, so one must exist scoped to this branch for a
    notification to land -- same requirement as the HR leave-request tests."""
    u = User(username=username, full_name='Gen Branch Admin', role='admin',
            branch_id=bid, password_hash='x', is_active=True)
    db.session.add(u)
    db.session.commit()
    return u.id


def test_failed_ortools_generation_notifies_admins(app):
    cc_id, subj_id, bid = _build_needs_both_days_class(
        app, 'NotifyFail', explicit_config={'day_separation_exempt': False})
    with app.app_context():
        admin_uid = _add_branch_admin(bid, 'zzgennotifyfail')
    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        notes = Notification.query.filter_by(
            title='Timetable generation failed', user_id=admin_uid).all()
        assert notes, 'expected a bell notification for the failed run'
        assert any(n.category == 'error' for n in notes)


def test_successful_ortools_generation_notifies_admins(app):
    with app.app_context():
        from models import GenClassConfig, GenSubject, GenTeacher, GenTeacherAssignment, \
            GenSubjectConfig, GenClassSubjectConfig
        b = Branch(name='ZzGenNotifyOk', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id
        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value='6',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value='3',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_separation_enabled', value='false',
                             school_level='sss', is_active=True),
        ])
        cc = GenClassConfig(branch_id=bid, class_name='ZzGenOkCls', school_level='sss',
                            num_arms=1, arm_names='ZzGenOkArm')
        subj = GenSubject(branch_id=bid, name='ZzGenOkSubj', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()
        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=subj.id, school_level='sss',
                                        periods_per_week=2))
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=2))
        teacher = GenTeacher(branch_id=bid, name='ZzGenOkTeacher', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name='ZzGenOkArm'))
        db.session.commit()
        cc_id = cc.id
        admin_uid = _add_branch_admin(bid, 'zzgennotifyok')

    c = _scoped_to_branch(_admin(app), bid)
    r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
             time_limit='20', periods_per_day='6', follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = GenTimetableResult.query.filter_by(branch_id=bid).all()
        assert rows, 'expected generation to succeed for this trivially-satisfiable setup'
        notes = Notification.query.filter_by(
            title='Timetable generated', user_id=admin_uid).all()
        assert notes, 'expected a bell notification for the successful run'
        assert any(n.category in ('success', 'warning') for n in notes)
        assert any(n.url for n in notes)   # links to the saved batch's results page


def test_disabling_generation_result_automation_skips_notification(app):
    cc_id, subj_id, bid = _build_needs_both_days_class(
        app, 'NotifyOff', explicit_config={'day_separation_exempt': False})
    with app.app_context():
        from utils import automations
        automations.set_enabled('generation_result', False)
        admin_uid = _add_branch_admin(bid, 'zzgennotifyoff')
    try:
        c = _scoped_to_branch(_admin(app), bid)
        r = _post(c, '/generator/generate/ortools', **{'class_ids[]': cc_id},
                 time_limit='20', periods_per_day='6', follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            notes = Notification.query.filter_by(user_id=admin_uid).all()
            assert not notes
    finally:
        with app.app_context():
            from utils import automations
            automations.set_enabled('generation_result', True)
