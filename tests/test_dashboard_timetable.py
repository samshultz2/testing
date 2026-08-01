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
