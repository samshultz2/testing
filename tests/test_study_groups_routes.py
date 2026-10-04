"""Study Groups (Tools): generate, view, move students, change leaders,
rename, delete, and export -- end-to-end through the real routes."""
import re

from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Student, TermSummary,
                    GroupSet, StudentGroup, GroupMember)
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _scoped_to_branch(c, bid):
    with c.session_transaction() as s:
        s['view_branch_id'] = bid
    return c


def _post(c, url, **data):
    data.setdefault('_csrf_token', 'a' * 64)
    return c.post(url, data=data)


def _tag():
    _SEQ[0] += 1
    return f'ZzSG{_SEQ[0]}'


def _build_class(app, *, num_students=12, arms=1, averages=None, session_name=None,
                 term_number=2, prior_term_number=1):
    """One branch, one session with two terms (prior_term_number and
    term_number -- same session unless prior_term_number > term_number isn't
    used), one class with ``arms`` arms, ``num_students`` active students
    spread across those arms, enrolled in the CURRENT term (term_number).

    ``averages``: optional list of per-student average scores for the PRIOR
    term (same length as num_students; None entries mean "no data, random").
    Missing/omitted -> no TermSummary rows at all (every student random).

    Returns dict with ids: bid, class_id, arm_ids (list), term_id,
    prior_term_id, student_ids (list, in the same order as `averages`).
    """
    tag = _tag()
    with app.app_context():
        b = Branch(name=f'{tag}Branch', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        # AcademicSession.is_active/Term.is_active are global singletons (see
        # utils.helpers.get_active_term) -- leaving an earlier test's session
        # marked active would make get_active_term() resolve to THEIR term
        # instead of this test's own, so deactivate any stragglers first.
        AcademicSession.query.filter_by(is_active=True).update({'is_active': False})
        Term.query.filter_by(is_active=True).update({'is_active': False})

        sess = AcademicSession(name=session_name or f'{tag}-Sess', is_active=True)
        db.session.add(sess); db.session.flush()

        prior_term = Term(session_id=sess.id, term_number=prior_term_number,
                          name=f'Term {prior_term_number}', is_active=False)
        db.session.add(prior_term); db.session.flush()
        cur_term = Term(session_id=sess.id, term_number=term_number,
                        name=f'Term {term_number}', is_active=True)
        db.session.add(cur_term); db.session.flush()

        cc = SchoolClass(name=f'{tag}Class', level=3, is_active=True)
        db.session.add(cc); db.session.flush()

        arm_ids = []
        caa_ids = []
        for i in range(arms):
            arm = ClassArm(name=f'{tag}Arm{i}', is_active=True)
            db.session.add(arm); db.session.flush()
            arm_ids.append(arm.id)
            caa = ClassArmAssignment(class_id=cc.id, arm_id=arm.id, term_id=cur_term.id,
                                     branch_id=bid)
            db.session.add(caa); db.session.flush()
            caa_ids.append(caa.id)

        student_ids = []
        for i in range(num_students):
            caa_id = caa_ids[i % len(caa_ids)]
            s = Student(student_id=f'{tag}S{i:03d}', first_name=f'First{i}',
                       surname=f'{tag}Surn{i}', gender='Male', branch_id=bid, is_active=True)
            db.session.add(s); db.session.flush()
            enr = StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa_id, is_active=True)
            db.session.add(enr); db.session.flush()
            student_ids.append(s.id)
            if averages is not None and i < len(averages) and averages[i] is not None:
                db.session.add(TermSummary(student_id=s.id, term_id=prior_term.id,
                                           enrollment_id=enr.id, average_score=averages[i]))
        db.session.commit()
        return {'bid': bid, 'class_id': cc.id, 'arm_ids': arm_ids, 'term_id': cur_term.id,
               'prior_term_id': prior_term.id, 'student_ids': student_ids, 'tag': tag}


def test_index_lists_classes_with_arm_counts(app):
    built = _build_class(app, num_students=6, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    body = c.get('/tools/study-groups/').get_data(as_text=True)
    assert built['tag'] + 'Class' in body


def test_generate_ranks_by_prior_term_average_and_picks_leaders(app):
    # 12 students, strictly increasing averages 0..11 -> with group_size=4,
    # 3 groups, top-3 (ids at index 9,10,11) must each lead a group.
    averages = [float(i) for i in range(12)]
    built = _build_class(app, num_students=12, arms=1, averages=averages)
    c = _scoped_to_branch(_admin(app), built['bid'])
    r = _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
             **{'arm_ids[]': built['arm_ids']}, group_size='4')
    assert r.status_code in (200, 302)
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        assert gs is not None and gs.num_groups == 3
        assert gs.basis_term_id == built['prior_term_id']
        leader_ids = {g.leader_student_id for g in gs.groups}
        top3 = set(built['student_ids'][9:12])
        assert leader_ids == top3
        # every student placed exactly once
        all_members = [m.student_id for g in gs.groups for m in g.members]
        assert sorted(all_members) == sorted(built['student_ids'])


def test_new_students_with_no_data_are_placed_randomly_not_as_leaders(app):
    averages = [100.0, 90.0] + [None] * 10   # 2 ranked, 10 brand-new
    built = _build_class(app, num_students=12, arms=1, averages=averages)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='4')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        leader_ids = {g.leader_student_id for g in gs.groups}
        ranked_ids = set(built['student_ids'][:2])
        assert ranked_ids <= leader_ids   # both genuinely-ranked students lead


def test_merging_two_arms_widens_the_pool_without_touching_enrollment(app):
    built = _build_class(app, num_students=10, arms=2)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='5')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        all_members = [m.student_id for g in gs.groups for m in g.members]
        assert sorted(all_members) == sorted(built['student_ids'])
        # enrollment itself is untouched -- still pointing at their original arm's CAA
        for sid in built['student_ids']:
            enr = StudentEnrollment.query.filter_by(student_id=sid).first()
            assert enr is not None and enr.is_active is True


def test_first_term_of_a_session_carries_over_from_previous_session_last_term(app):
    tag = _tag()
    with app.app_context():
        b = Branch(name=f'{tag}Branch', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        AcademicSession.query.filter_by(is_active=True).update({'is_active': False})
        Term.query.filter_by(is_active=True).update({'is_active': False})

        old_sess = AcademicSession(name=f'{tag}-OldSess', is_active=False)
        db.session.add(old_sess); db.session.flush()
        old_term3 = Term(session_id=old_sess.id, term_number=3, name='Term 3', is_active=False)
        db.session.add(old_term3); db.session.flush()

        new_sess = AcademicSession(name=f'{tag}-NewSess', is_active=True)
        db.session.add(new_sess); db.session.flush()
        new_term1 = Term(session_id=new_sess.id, term_number=1, name='Term 1', is_active=True)
        db.session.add(new_term1); db.session.flush()

        cc = SchoolClass(name=f'{tag}Class', level=4, is_active=True)
        db.session.add(cc); db.session.flush()
        arm = ClassArm(name=f'{tag}Arm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment(class_id=cc.id, arm_id=arm.id, term_id=new_term1.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        student_ids = []
        for i in range(6):
            s = Student(student_id=f'{tag}S{i:03d}', first_name=f'F{i}', surname=f'{tag}Su{i}',
                       gender='Male', branch_id=bid, is_active=True)
            db.session.add(s); db.session.flush()
            enr = StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(enr); db.session.flush()
            student_ids.append(s.id)
            db.session.add(TermSummary(student_id=s.id, term_id=old_term3.id,
                                       enrollment_id=enr.id, average_score=float(90 - i)))
        db.session.commit()
        old_term3_id = old_term3.id
        class_id = cc.id
        arm_id = arm.id

    c = _scoped_to_branch(_admin(app), bid)
    _post(c, '/tools/study-groups/generate', class_id=class_id, **{'arm_ids[]': [arm_id]},
         group_size='3')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=class_id).first()
        assert gs.basis_term_id == old_term3_id
        # top-2 (lowest index, highest average) must each lead one of the 2 groups
        leader_ids = {g.leader_student_id for g in gs.groups}
        assert leader_ids == set(student_ids[:2])


def test_move_student_and_leader_reassignment(app):
    averages = [90.0, 80.0, 70.0, 60.0, None, None, None, None]
    built = _build_class(app, num_students=8, arms=1, averages=averages)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='4')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id = gs.id
        group_a, group_b = gs.groups[0], gs.groups[1]
        leader_a_id = group_a.leader_student_id
        group_a_id, group_b_id = group_a.id, group_b.id

    # Move group A's leader into group B -- group A must get a new leader.
    r = c.post(f'/tools/study-groups/{set_id}/move',
              data={'_csrf_token': 'a' * 64, 'student_id': leader_a_id, 'group_id': group_b_id})
    assert r.status_code in (200, 302)
    with app.app_context():
        ga = db.session.get(StudentGroup, group_a_id)
        gb = db.session.get(StudentGroup, group_b_id)
        assert gb.leader_student_id != leader_a_id or any(
            m.student_id == leader_a_id for m in gb.members)
        moved_member = GroupMember.query.filter_by(group_set_id=set_id, student_id=leader_a_id).first()
        assert moved_member.group_id == group_b_id
        assert ga.leader_student_id is not None
        assert ga.leader_student_id != leader_a_id


def test_set_leader_requires_membership_in_that_group(app):
    built = _build_class(app, num_students=8, arms=1, averages=[float(i) for i in range(8)])
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='4')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id = gs.id
        group_a, group_b = gs.groups[0], gs.groups[1]
        # a student who belongs to group B, attempted as leader of group A
        outsider_id = group_b.members[0].student_id
        group_a_id = group_a.id

    r = c.post(f'/tools/study-groups/{set_id}/leader',
              data={'_csrf_token': 'a' * 64, 'group_id': group_a_id, 'student_id': outsider_id},
              headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400
    assert r.get_json()['ok'] is False


def test_rename_group(app):
    built = _build_class(app, num_students=4, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='4')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id, group_id = gs.id, gs.groups[0].id

    r = c.post(f'/tools/study-groups/{set_id}/rename',
              data={'_csrf_token': 'a' * 64, 'group_id': group_id, 'label': 'The Eagles'},
              headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['label'] == 'The Eagles'
    with app.app_context():
        assert db.session.get(StudentGroup, group_id).label == 'The Eagles'


def test_view_page_renders(app):
    built = _build_class(app, num_students=5, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='5')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id = gs.id
    body = c.get(f'/tools/study-groups/{set_id}').get_data(as_text=True)
    assert 'sg-data' in body
    assert built['tag'] in body


def test_export_pdf_and_xlsx(app):
    built = _build_class(app, num_students=5, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='5')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id = gs.id
    rp = c.get(f'/tools/study-groups/{set_id}/export.pdf')
    assert rp.status_code == 200 and rp.data[:4] == b'%PDF'
    rx = c.get(f'/tools/study-groups/{set_id}/export.xlsx')
    assert rx.status_code == 200 and len(rx.data) > 0
    assert 'spreadsheet' in rx.headers.get('Content-Type', '') or 'xlsx' in rx.headers.get(
        'Content-Disposition', '')
    rg = c.get(f'/tools/study-groups/{set_id}/export.png')
    assert rg.status_code == 200 and rg.data[:8] == b'\x89PNG\r\n\x1a\n'
    assert len(rg.data) > 1000


def test_delete_set_removes_groups_and_members(app):
    built = _build_class(app, num_students=4, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='4')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id = gs.id

    r = c.post(f'/tools/study-groups/{set_id}/delete', data={'_csrf_token': 'a' * 64})
    assert r.status_code in (200, 302)
    with app.app_context():
        assert db.session.get(GroupSet, set_id) is None
        assert StudentGroup.query.filter_by(group_set_id=set_id).count() == 0
        assert GroupMember.query.filter_by(group_set_id=set_id).count() == 0


def test_cross_branch_access_is_denied(app):
    built = _build_class(app, num_students=4, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    _post(c, '/tools/study-groups/generate', class_id=built['class_id'],
         **{'arm_ids[]': built['arm_ids']}, group_size='4')
    with app.app_context():
        gs = GroupSet.query.filter_by(class_id=built['class_id']).first()
        set_id = gs.id

    other = _build_class(app, num_students=2, arms=1)
    from models import User
    username = f'{other["tag"]}admin'
    with app.app_context():
        u = User(username=username, full_name='Other Branch Admin', role='admin',
                scope='branch', branch_id=other['bid'], password_hash='x', is_active=True,
                must_change_password=False)
        u.set_password('Str0ng!Passw0rd1')
        db.session.add(u); db.session.commit()

    other_client = app.test_client()
    tok = login_token(other_client)
    other_client.post('/login', data={'username': username, 'password': 'Str0ng!Passw0rd1',
                                      '_csrf_token': tok})
    r = other_client.get(f'/tools/study-groups/{set_id}')
    assert r.status_code == 403


def test_generate_rejects_missing_class_or_arms(app):
    built = _build_class(app, num_students=4, arms=1)
    c = _scoped_to_branch(_admin(app), built['bid'])
    r = _post(c, '/tools/study-groups/generate', class_id='', **{'arm_ids[]': []}, group_size='4')
    assert r.status_code in (200, 302)
    with app.app_context():
        assert GroupSet.query.filter_by(class_id=built['class_id']).count() == 0
