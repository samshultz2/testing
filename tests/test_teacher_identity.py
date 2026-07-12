"""Teacher <-> timetable association: tolerant name matching + explicit account
link, so a teacher sees their personal timetable even when the published name
differs from their login name."""
import re
from datetime import time

from models import (db, User, Term, AcademicSession, SchoolClass, ClassArm,
                    ClassArmAssignment, Subject, TimetableSlot, ClassTimetable)
from models.models.generator import GenTeacher
from utils import name_match as nm


# --- unit: normalization ---------------------------------------------------- #
def test_normalize_drops_titles_and_is_order_independent():
    assert nm.normalize_person_name('Mr. John Doe') == nm.normalize_person_name('Doe, John')
    assert nm.normalize_person_name('john  doe') == nm.normalize_person_name('Dr John DOE')
    assert nm.names_match('Mrs Ada N. Okafor', 'okafor ada n')
    assert not nm.names_match('John Doe', 'Jane Doe')
    assert nm.normalize_person_name('') == '' and nm.normalize_person_name(None) == ''


# --- route helpers ---------------------------------------------------------- #
def _get_or_add(model, defaults=None, **filt):
    obj = model.query.filter_by(**filt).first()
    if obj is None:
        obj = model(**filt, **(defaults or {}))
        db.session.add(obj); db.session.flush()
    return obj


def _scaffold(app, tag):
    """A term + class + slot + subject to hang timetable entries on. Returns
    (term_id, caa_id, slot_id, subject_id)."""
    with app.app_context():
        ssn = _get_or_add(AcademicSession, name=f'TI-{tag}-S')
        term = _get_or_add(Term, defaults={'session_id': ssn.id, 'term_number': 1}, name=f'TI-{tag}-T')
        cls = _get_or_add(SchoolClass, defaults={'level': 1}, name=f'TI-{tag}-G')
        arm = _get_or_add(ClassArm, defaults={'is_active': True}, name=f'TI-{tag}-A')
        caa = _get_or_add(ClassArmAssignment, class_id=cls.id, arm_id=arm.id, term_id=term.id)
        subj = _get_or_add(Subject, defaults={'short_name': 'TIX'}, name=f'TI-{tag}-Maths')
        slot = _get_or_add(TimetableSlot,
                           defaults={'slot_number': 1, 'order': 1, 'is_active': True, 'is_break': False,
                                     'start_time': time(8, 0), 'end_time': time(8, 40)},
                           name=f'TI-{tag}-P1')
        db.session.commit()
        return term.id, caa.id, slot.id, subj.id


def _user(app, username, full_name, email=None):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=full_name, email=email,
                     role='teacher', is_active=True)
            u.set_password('Zebra!Mango42Q'); u.must_change_password = False
            db.session.add(u); db.session.commit()
        return u.id


def _login(app, username):
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/login').get_data(as_text=True)).group(1)
    c.post('/login', data={'username': username, 'password': 'Zebra!Mango42Q', '_csrf_token': tok})
    return c


def test_timetable_matches_slightly_different_name(app):
    term_id, caa_id, slot_id, subj_id = _scaffold(app, 'slug')
    _user(app, 'jdoe_ti', 'John Doe')
    with app.app_context():
        if not ClassTimetable.query.filter_by(teacher_name='Mr. Doe John').first():
            db.session.add(ClassTimetable(class_arm_assignment_id=caa_id, slot_id=slot_id,
                                          day_of_week=0, subject_id=subj_id,
                                          teacher_name='Mr. Doe John', is_active=True))
            db.session.commit()
    page = _login(app, 'jdoe_ti').get(f'/timetable/mine?term_id={term_id}').get_data(as_text=True)
    assert 'TIX' in page                                   # the period shows despite name diff
    assert 'No periods are assigned to you' not in page


def test_explicit_account_link_resolves_unrelated_name(app):
    term_id, caa_id, slot_id, subj_id = _scaffold(app, 'link')
    uid = _user(app, 'alice_ti', 'Alice Smith')
    with app.app_context():
        gt = GenTeacher.query.filter_by(name='Codename Falcon').first()
        if not gt:
            gt = GenTeacher(name='Codename Falcon', user_id=uid)
            db.session.add(gt)
        else:
            gt.user_id = uid
        if not ClassTimetable.query.filter_by(teacher_name='Codename Falcon').first():
            db.session.add(ClassTimetable(class_arm_assignment_id=caa_id, slot_id=slot_id,
                                          day_of_week=0, subject_id=subj_id,
                                          teacher_name='Codename Falcon', is_active=True))
        db.session.commit()
    page = _login(app, 'alice_ti').get(f'/timetable/mine?term_id={term_id}').get_data(as_text=True)
    assert 'TIX' in page
    assert 'No periods are assigned to you' not in page


def test_email_autolink_resolves_name(app):
    term_id, caa_id, slot_id, subj_id = _scaffold(app, 'mail')
    _user(app, 'bola_ti', 'Bola A', email='bola.ti@school.edu')
    with app.app_context():
        if not GenTeacher.query.filter_by(name='B. Adewale').first():
            db.session.add(GenTeacher(name='B. Adewale', email='Bola.TI@school.edu'))  # case-insensitive
        if not ClassTimetable.query.filter_by(teacher_name='B. Adewale').first():
            db.session.add(ClassTimetable(class_arm_assignment_id=caa_id, slot_id=slot_id,
                                          day_of_week=0, subject_id=subj_id,
                                          teacher_name='B. Adewale', is_active=True))
        db.session.commit()
    page = _login(app, 'bola_ti').get(f'/timetable/mine?term_id={term_id}').get_data(as_text=True)
    assert 'TIX' in page
