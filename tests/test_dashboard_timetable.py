"""Today's-schedule dashboard glance.

The timetable widget summarises the current day's periods and how many classes
are running in each, scoped to the viewer. It only surfaces when there are
actual scheduled classes today.
"""
from datetime import date, time
from flask import session
from models import (db, SchoolClass, ClassArm, ClassArmAssignment, ClassTimetable,
                    TimetableSlot, Subject, Term, AcademicSession)


def test_timetable_today_summarises_periods(app):
    from routes.main import _dash_timetable_today
    dow = date.today().weekday()
    with app.app_context():
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            s = AcademicSession(name='TTG-Sess', is_active=True)
            db.session.add(s); db.session.flush()
            term = Term(session_id=s.id, term_number=1, name='TTG-Term', is_active=True)
            db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first()
        if not sc:
            sc = SchoolClass(name='TTG-Class', level=1)
            db.session.add(sc); db.session.flush()
        arm = ClassArm.query.first()
        if not arm:
            arm = ClassArm(name='TTG-Arm')
            db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(
            class_id=sc.id, arm_id=arm.id, term_id=term.id).first()
        if not caa:
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id)
            db.session.add(caa); db.session.flush()
        # A wide slot so it reads as "in session" for most of the day.
        slot = TimetableSlot.query.filter_by(slot_number=91).first()
        if not slot:
            slot = TimetableSlot(slot_number=91, name='TT-Glance', start_time=time(7, 0),
                                 end_time=time(23, 59), is_break=False, order=91, is_active=True)
            db.session.add(slot); db.session.flush()
        subj = Subject.query.first()
        if not subj:
            subj = Subject(name='TT-Glance-Subj', is_active=True)
            db.session.add(subj); db.session.flush()
        if not ClassTimetable.query.filter_by(class_arm_assignment_id=caa.id,
                                              slot_id=slot.id, day_of_week=dow).first():
            db.session.add(ClassTimetable(class_arm_assignment_id=caa.id, slot_id=slot.id,
                                          day_of_week=dow, subject_id=subj.id, is_active=True))
        db.session.commit()
        slot_id, term_id = slot.id, term.id

    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'   # central: sees every branch's timetable
        active_term = db.session.get(Term, term_id)   # bound to this request's session
        data = _dash_timetable_today(active_term, None)
        assert data is not None
        assert data['total_today'] >= 1
        # The seeded slot is in the ladder and its class count is counted.
        row = next((s for s in data['slots'] if s['id'] == slot_id), None)
        assert row is not None and row['classes'] >= 1


def test_timetable_slot_drilldown(app):
    """Tapping a period drills down to each class arm's subject + teacher for that
    slot today (utils helper + the JSON route)."""
    from routes.main import _dash_timetable_slot
    from config import Config
    from tests.conftest import login_token
    dow = date.today().weekday()
    with app.app_context():
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            s = AcademicSession(name='TTD-Sess', is_active=True); db.session.add(s); db.session.flush()
            term = Term(session_id=s.id, term_number=1, name='TTD-Term', is_active=True)
            db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first() or SchoolClass(name='TTD-Class', level=1)
        arm = ClassArm.query.first() or ClassArm(name='TTD-Arm')
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sc.id, arm_id=arm.id, term_id=term.id).first()
        if not caa:
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id)
            db.session.add(caa); db.session.flush()
        slot = TimetableSlot.query.filter_by(slot_number=92).first()
        if not slot:
            slot = TimetableSlot(slot_number=92, name='TTD-Period', start_time=time(7, 0),
                                 end_time=time(23, 59), is_break=False, order=92, is_active=True)
            db.session.add(slot); db.session.flush()
        subj = Subject.query.filter_by(name='TTD-Subject').first() or Subject(name='TTD-Subject', is_active=True)
        db.session.add(subj); db.session.flush()
        if not ClassTimetable.query.filter_by(class_arm_assignment_id=caa.id, slot_id=slot.id, day_of_week=dow).first():
            db.session.add(ClassTimetable(class_arm_assignment_id=caa.id, slot_id=slot.id, day_of_week=dow,
                                          subject_id=subj.id, teacher_name='Mr. Bello', room='Rm 4', is_active=True))
        db.session.commit()
        slot_id, term_id = slot.id, term.id

    with app.test_request_context('/'):
        session['logged_in'] = True; session['role'] = 'super_admin'
        data = _dash_timetable_slot(db.session.get(Term, term_id), None, slot_id)
    assert data is not None and data['slot']['id'] == slot_id
    mine = [r for r in data['rows'] if r['subject'] == 'TTD-Subject']
    assert mine and mine[0]['teacher'] == 'Mr. Bello' and mine[0]['room'] == 'Rm 4'
    assert mine[0]['class_arm']

    # And via the JSON route.
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.get(f'/api/dashboard/timetable/slot/{slot_id}')
    assert r.status_code == 200
    body = r.get_json()
    assert any(row['subject'] == 'TTD-Subject' and row['teacher'] == 'Mr. Bello' for row in body['rows'])
