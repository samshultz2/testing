"""A teacher's personal timetable: every period they teach, matched by name.
(The app fixture is a session-scoped shared DB, so use unique names + get-or-create.)"""
import re
from datetime import time

from models import (db, User, Term, AcademicSession, SchoolClass, ClassArm,
                    ClassArmAssignment, Subject, TimetableSlot, ClassTimetable)


def _get_or_add(model, defaults=None, **filt):
    obj = model.query.filter_by(**filt).first()
    if obj is None:
        obj = model(**filt, **(defaults or {}))
        db.session.add(obj)
        db.session.flush()
    return obj


def _setup(app):
    with app.app_context():
        u = User.query.filter_by(username='mytt_teach').first()
        if not u:
            u = User(username='mytt_teach', full_name='Mytt Teacher', role='teacher', is_active=True)
            u.set_password('Zebra!Mango42Q'); u.must_change_password = False
            db.session.add(u)
        ssn = _get_or_add(AcademicSession, name='MYTT-Sess')
        term = _get_or_add(Term, defaults={'session_id': ssn.id, 'term_number': 1}, name='MYTT-Term')
        cls = _get_or_add(SchoolClass, defaults={'level': 1}, name='MYTT-Grade')
        arm = _get_or_add(ClassArm, defaults={'is_active': True}, name='MYTT-Arm')
        caa = _get_or_add(ClassArmAssignment, class_id=cls.id, arm_id=arm.id, term_id=term.id)
        subj = _get_or_add(Subject, defaults={'short_name': 'MYX'}, name='MYTT-Maths')
        slot = _get_or_add(TimetableSlot,
                           defaults={'slot_number': 1, 'order': 1, 'is_active': True, 'is_break': False,
                                     'start_time': time(8, 0), 'end_time': time(8, 40)},
                           name='MYTT-P1')
        if not ClassTimetable.query.filter_by(teacher_name='Mytt Teacher').first():
            db.session.add(ClassTimetable(class_arm_assignment_id=caa.id, slot_id=slot.id,
                                          day_of_week=0, subject_id=subj.id,
                                          teacher_name='Mytt Teacher', is_active=True))
            db.session.add(ClassTimetable(class_arm_assignment_id=caa.id, slot_id=slot.id,
                                          day_of_week=1, subject_id=subj.id,
                                          teacher_name='Someone Else', is_active=True))
        db.session.commit()
        return term.id


def _login(app, username='mytt_teach'):
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/login').get_data(as_text=True)).group(1)
    c.post('/login', data={'username': username, 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    return c


def test_my_timetable_shows_only_my_periods(app):
    term_id = _setup(app)
    c = _login(app)
    page = c.get(f'/timetable/mine?term_id={term_id}').get_data(as_text=True)
    assert 'My timetable' in page
    assert 'MYX' in page and 'MYTT-Grade' in page        # my period, with its class
    assert 'No periods are assigned to you' not in page


def test_my_timetable_empty_state_when_name_has_no_periods(app):
    term_id = _setup(app)
    with app.app_context():
        if not User.query.filter_by(username='mytt_nobody').first():
            u = User(username='mytt_nobody', full_name='Mytt Nobody', role='teacher', is_active=True)
            u.set_password('Zebra!Mango42Q'); u.must_change_password = False
            db.session.add(u); db.session.commit()
    c = _login(app, username='mytt_nobody')
    page = c.get(f'/timetable/mine?term_id={term_id}').get_data(as_text=True)
    assert 'No periods are assigned to you' in page
