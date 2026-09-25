"""Timetable generator: bulk-remove multiple teacher assignments at once
from /generator/assignments, instead of one at a time."""
from config import Config
from models import db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _seed_assignments(app, tag, n=3):
    """One class-arm with `n` different subjects, each assigned to its own
    teacher — enough distinct assignments to exercise a multi-select bulk
    delete. Returns the list of assignment ids."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzBD{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}')
        db.session.add(cc); db.session.flush()

        ids = []
        for i in range(n):
            subj = GenSubject(branch_id=bid, name=f'ZzSubj{tag}{i}', school_level='sss')
            teacher = GenTeacher(branch_id=bid, name=f'Zz Teacher{tag}{i}', school_level='sss',
                                 max_periods_per_day=6, max_periods_per_week=30)
            db.session.add_all([subj, teacher]); db.session.flush()
            a = GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                     class_config_id=cc.id, arm_name=f'ZzArm{tag}')
            db.session.add(a); db.session.flush()
            ids.append(a.id)
        db.session.commit()
        return cc.id, ids


def test_assignments_page_has_checkboxes_and_bulk_delete_button(app):
    _seed_assignments(app, 'A', n=2)
    c = _admin(app)
    r = c.get('/generator/assignments')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'assignment-checkbox' in body
    assert 'bulk_delete_teacher_assignments' in body or 'bulkDeleteForm' in body
    assert 'Remove Selected' in body


def test_bulk_delete_removes_every_selected_assignment(app):
    cc_id, ids = _seed_assignments(app, 'B', n=3)
    c = _admin(app)

    r = c.post('/generator/assignments/bulk-delete', follow_redirects=True, data={
        '_csrf_token': 'a' * 64,
        'assignment_ids[]': [str(i) for i in ids],
    })
    assert r.status_code == 200
    assert '3 assignment(s) removed' in r.get_data(as_text=True)

    with app.app_context():
        remaining = GenTeacherAssignment.query.filter(
            GenTeacherAssignment.id.in_(ids), GenTeacherAssignment.is_active == True).count()
        assert remaining == 0


def test_bulk_delete_leaves_unselected_assignments_alone(app):
    cc_id, ids = _seed_assignments(app, 'C', n=3)
    c = _admin(app)
    # Only remove the first two of three.
    c.post('/generator/assignments/bulk-delete', follow_redirects=True, data={
        '_csrf_token': 'a' * 64,
        'assignment_ids[]': [str(ids[0]), str(ids[1])],
    })
    with app.app_context():
        assert GenTeacherAssignment.query.get(ids[0]).is_active is False
        assert GenTeacherAssignment.query.get(ids[1]).is_active is False
        assert GenTeacherAssignment.query.get(ids[2]).is_active is True


def test_bulk_delete_with_no_selection_flashes_error_and_deletes_nothing(app):
    cc_id, ids = _seed_assignments(app, 'D', n=1)
    c = _admin(app)
    r = c.post('/generator/assignments/bulk-delete', follow_redirects=True, data={
        '_csrf_token': 'a' * 64,
    })
    assert r.status_code == 200
    assert 'No assignments selected' in r.get_data(as_text=True)
    with app.app_context():
        assert GenTeacherAssignment.query.get(ids[0]).is_active is True


def test_bulk_delete_skips_ids_from_another_branch(app):
    """A stale/tampered id from a branch the current user can't access must
    be silently skipped, not removed and not allowed to 403 the whole batch."""
    from models import User

    with app.app_context():
        other = Branch(name='ZzBDOtherBranch', is_default=False)
        db.session.add(other); db.session.flush()
        u = User(username='zzbd_branch_admin', full_name='Zz Branch Admin', role='admin',
                 scope='branch', branch_id=other.id, rank=50, manage_scope='branch',
                 is_active=True, must_change_password=False)
        u.set_password('Str0ng!Passw0rd1')
        db.session.add(u); db.session.commit()
        other_bid = other.id

    # Assignment on the DEFAULT branch (own_ids) plus a fabricated id that
    # belongs to `other`'s branch, mixed into one bulk-delete request from a
    # user scoped to `other` only.
    cc_id, own_ids = _seed_assignments(app, 'E', n=1)
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=other_bid, class_name='ZzBDOtherClass',
                            school_level='sss', num_arms=1, arm_names='ZzOtherArm')
        subj = GenSubject(branch_id=other_bid, name='ZzOtherSubj', school_level='sss')
        teacher = GenTeacher(branch_id=other_bid, name='Zz Other Teacher', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([cc, subj, teacher]); db.session.flush()
        other_assignment = GenTeacherAssignment(branch_id=other_bid, teacher_id=teacher.id,
                                                 subject_id=subj.id, class_config_id=cc.id,
                                                 arm_name='ZzOtherArm')
        db.session.add(other_assignment); db.session.commit()
        other_assignment_id = other_assignment.id

    c = app.test_client()
    c.post('/login', data={'username': 'zzbd_branch_admin', 'password': 'Str0ng!Passw0rd1',
                           '_csrf_token': login_token(c)})
    from tests.conftest import auth_csrf
    r = c.post('/generator/assignments/bulk-delete', follow_redirects=True, data={
        '_csrf_token': auth_csrf(c),
        'assignment_ids[]': [str(other_assignment_id), str(own_ids[0])],
    })
    assert r.status_code == 200

    with app.app_context():
        # The branch-B admin's own assignment is removed...
        assert GenTeacherAssignment.query.get(other_assignment_id).is_active is False
        # ...but the default-branch assignment they have no access to is untouched.
        assert GenTeacherAssignment.query.get(own_ids[0]).is_active is True
