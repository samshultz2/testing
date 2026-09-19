"""Attendance Phase 3 — parent notifications (absentees / low-attendance drafts
via Communication, gated by the Automation Center) + profile history."""
from datetime import date, timedelta

from config import Config
from models import (db, Branch, Student, ParentContact, ClassArmAssignment, SchoolClass,
                    ClassArm, Term, AcademicSession, StudentEnrollment, Week, Attendance,
                    Message)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _seed(app, tag, marks):
    """One student (surname Zz…, sorts last) with a parent phone, and the given
    attendance marks (offset, morning, afternoon)."""
    with app.app_context():
        sess = AcademicSession(name=f'NSess{tag}', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'NTerm{tag}', is_active=False,
                    start_date=date(2025, 5, 5), end_date=date(2025, 5, 9))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=date(2025, 5, 5), end_date=date(2025, 5, 11))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'NC{tag}', level=1); arm = ClassArm(name=f'NA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        st = Student(student_id=f'N{tag}', first_name='Nora', surname=f'Zz{tag}',
                     gender='Female', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        db.session.add(ParentContact(student_id=st.id, phone_number=f'0805{abs(hash(tag)) % 1000000:06d}',
                                     is_primary=True))
        en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for off, m, a in marks:
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id,
                                      date=date(2025, 5, 5) + timedelta(days=off),
                                      morning_present=m, afternoon_present=a))
        db.session.commit()
        return term.id, caa.id, st.id


def test_absentee_ids_full_day_only(app):
    from utils import attendance_notify as AN
    # Mon absent(both), Tue late(morning only) → only Mon counts as absent.
    tid, caa_id, sid = _seed(app, 'AB1', [(0, False, False), (1, True, False)])
    with app.app_context():
        assert AN.absentee_student_ids([caa_id], date(2025, 5, 5)) == [sid]
        assert AN.absentee_student_ids([caa_id], date(2025, 5, 6)) == []   # late, not absent


def _enable(app, key, on=True):
    from utils import automations
    with app.app_context():
        automations.set_enabled(key, on)
        db.session.commit()


def _post(client, url, payload):
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return client.post(url, json=payload, headers={
        'X-Requested-With': 'fetch', 'X-CSRFToken': 'a' * 64, 'Content-Type': 'application/json'})


def test_draft_absentee_notice_and_history(app):
    from utils import attendance_notify as AN
    tid, caa_id, sid = _seed(app, 'DR1', [(0, False, False)])
    _enable(app, 'attendance_absent_parent', True)
    client = _admin(app)
    r = _post(client, '/attendance/api/notify/absentees',
              {'assignment_id': caa_id, 'date': '2025-05-05'}).get_json()
    assert r['ok']
    with app.app_context():
        assert Message.query.filter_by(title=AN.ABSENT_TITLE).count() >= 1
        hist = AN.student_notification_history(sid)
        assert any(h['title'] == AN.ABSENT_TITLE for h in hist)
    _enable(app, 'attendance_absent_parent', False)


def test_draft_low_attendance_notice(app):
    from utils import attendance_notify as AN
    # all-absent week → 0% → below 75% threshold
    tid, caa_id, sid = _seed(app, 'LOW1', [(d, False, False) for d in range(5)])
    _enable(app, 'attendance_low_parent', True)
    client = _admin(app)
    r = _post(client, '/attendance/api/notify/low', {'term_id': tid}).get_json()
    assert r['ok']
    with app.app_context():
        assert Message.query.filter_by(title=AN.LOW_TITLE).count() >= 1
    _enable(app, 'attendance_low_parent', False)


def test_notify_endpoint_gated_by_automation(app):
    from utils import automations
    tid, caa_id, sid = _seed(app, 'EP1', [(0, False, False)])
    client = _admin(app)
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    hdrs = {'X-Requested-With': 'fetch', 'X-CSRFToken': 'a' * 64, 'Content-Type': 'application/json'}
    with app.app_context():
        automations.set_enabled('attendance_absent_parent', False)
        db.session.commit()
    off = client.post('/attendance/api/notify/absentees',
                      json={'assignment_id': caa_id, 'date': '2025-05-05'}, headers=hdrs)
    assert off.status_code == 400 and off.get_json()['ok'] is False
    with app.app_context():
        automations.set_enabled('attendance_absent_parent', True)
        db.session.commit()
    on = client.post('/attendance/api/notify/absentees',
                     json={'assignment_id': caa_id, 'date': '2025-05-05'}, headers=hdrs)
    assert on.status_code == 200 and on.get_json()['ok'] is True
    assert '/communication/' in on.get_json()['redirect']
    with app.app_context():
        automations.set_enabled('attendance_absent_parent', False)   # restore registry default
        db.session.commit()


def test_profile_includes_notifications_key(app):
    tid, caa_id, sid = _seed(app, 'PN1', [(0, False, False)])
    client = _admin(app)
    body = client.get(f'/attendance/api/student/{sid}').get_json()
    assert 'notifications' in body


def _seed_class(app, tag, students):
    """One class/date with several students. ``students``: list of
    (first, surname, gender, morning, afternoon, parent_name, relationship, phone)."""
    with app.app_context():
        sess = AcademicSession(name=f'AbsSess{tag}', is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'AbsTerm{tag}', is_active=False,
                    start_date=date(2025, 6, 2), end_date=date(2025, 6, 6))
        db.session.add(term); db.session.flush()
        wk = Week(term_id=term.id, week_number=1, start_date=date(2025, 6, 2), end_date=date(2025, 6, 8))
        db.session.add(wk); db.session.flush()
        sc = SchoolClass(name=f'AC{tag}', level=1); arm = ClassArm(name=f'AA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        bid = Branch.get_default().id
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        target = date(2025, 6, 2)
        sids = []
        for i, (fn, sn, g, m, a, pname, rel, phone) in enumerate(students):
            st = Student(student_id=f'{tag}{i}', first_name=fn, surname=sn, gender=g,
                        is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            if phone:
                db.session.add(ParentContact(student_id=st.id, name=pname, relationship=rel,
                                             phone_number=phone, is_primary=True))
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True)
            db.session.add(en); db.session.flush()
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=target,
                                      morning_present=m, afternoon_present=a))
            sids.append(st.id)
        db.session.commit()
        return caa.id, target, sids


def test_absentees_endpoint_lists_full_day_absentees_with_contact_and_share_text(app):
    caa_id, target, sids = _seed_class(app, 'LST1', [
        ('John', 'Doe', 'Male', False, False, 'Mr Doe', 'Father', '08012345678'),
        ('Jane', 'Smith', 'Female', False, False, 'Mrs Smith', 'Mother', '08087654321'),
        ('Amaka', 'Okafor', 'Female', True, True, None, None, None),   # present -> excluded
        ('Tunde', 'Bello', 'Male', True, False, None, None, None),     # late, not absent -> excluded
    ])
    client = _admin(app)
    body = client.get(f'/attendance/api/absentees?assignment_id={caa_id}&date={target.isoformat()}').get_json()

    assert [a['student_name'] for a in body['absentees']] == ['Doe John', 'Smith Jane']
    assert body['absentees'][0]['parent_name'] == 'Mr Doe'
    assert body['absentees'][0]['parent_relationship'] == 'Father'
    assert body['absentees'][0]['parent_phone'] == '08012345678'
    assert body['absentees'][0]['wa_intl'] == '2348012345678'

    text = body['share_text']
    assert 'absent from school today' in text
    assert 'Doe John' in text and 'Mr Doe' in text and '08012345678' in text
    assert 'Smith Jane' in text and 'Mrs Smith' in text and '08087654321' in text
    assert 'Okafor Amaka' not in text and 'Bello Tunde' not in text


def test_absentees_endpoint_handles_no_contact_and_no_absentees(app):
    caa_id, target, sids = _seed_class(app, 'LST2', [
        ('NoPhone', 'Kid', 'Male', False, False, None, None, None),
    ])
    client = _admin(app)
    body = client.get(f'/attendance/api/absentees?assignment_id={caa_id}&date={target.isoformat()}').get_json()
    assert len(body['absentees']) == 1
    assert body['absentees'][0]['parent_phone'] == '' and body['absentees'][0]['wa_intl'] == ''
    assert 'no phone on file' in body['share_text']

    caa_id2, target2, _ = _seed_class(app, 'LST3', [
        ('All', 'Present', 'Female', True, True, None, None, None),
    ])
    empty = client.get(f'/attendance/api/absentees?assignment_id={caa_id2}&date={target2.isoformat()}').get_json()
    assert empty['absentees'] == []


def test_absentees_endpoint_requires_view_access(app):
    caa_id, target, sids = _seed_class(app, 'LST4', [
        ('John', 'Doe', 'Male', False, False, 'Mr Doe', 'Father', '08012345678'),
    ])
    client = app.test_client()   # not logged in
    r = client.get(f'/attendance/api/absentees?assignment_id={caa_id}&date={target.isoformat()}')
    assert r.status_code in (302, 401, 403)
