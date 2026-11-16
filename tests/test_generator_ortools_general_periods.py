"""Best quality (OR-Tools) on a class whose per-class subjects page was never
saved: it used to stop with "No requirements found" while Fast built the
same class from each subject's general periods. It now falls back to them."""
import pytest

from models import (db, GenClassConfig, GenSubject, GenSubjectConfig, GenTeacher,
                    GenTeacherAssignment, GenTimetableResult, GenTimetableRule)
from tests.test_generator_arm_count_display import _admin, _scoped_to_branch, _seed_branch


def test_ortools_uses_general_subject_periods_when_class_has_no_rows(app):
    from routes.generator_ortools import check_ortools_available
    if not check_ortools_available():
        pytest.skip('OR-Tools not installed')
    bid = _seed_branch(app, 'OrGen')
    with app.app_context():
        for rt, v in (('day_separation_enabled', 'false'), ('first_period_no_repeat', 'false')):
            db.session.add(GenTimetableRule(branch_id=bid, rule_type=rt, value=v,
                                            school_level='sss', is_active=True))
        cc = GenClassConfig(branch_id=bid, class_name='ZzOrGenCls', school_level='sss',
                            num_arms=1, arm_names='ZzOrA', has_streams=False)
        subj = GenSubject(branch_id=bid, name='ZzOrGenSubj', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()
        db.session.add(GenSubjectConfig(branch_id=bid, subject_id=subj.id, school_level='sss',
                                        periods_per_week=3, is_active=True))
        t = GenTeacher(branch_id=bid, name='Zz Or Teacher', school_level='sss',
                       max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(t); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=None))
        db.session.commit()
        cc_id, sid = cc.id, subj.id

    c = _scoped_to_branch(_admin(app), bid)
    r = c.post('/generator/generate/ortools', data={
        '_csrf_token': 'a' * 64, 'method': 'ortools', 'class_ids[]': str(cc_id), 'time_limit': '10'})
    assert r.status_code == 302
    assert '/generator/results/' in r.headers['Location'], r.headers['Location']
    with app.app_context():
        n = GenTimetableResult.query.filter_by(branch_id=bid, class_name='ZzOrGenCls', subject_id=sid).count()
    assert n == 3
