"""Undoing a merge of two different pupils: a graduate (from a past session)
whose record absorbed a current SSS3 pupil's class must (1) not appear on the
current class register, and (2) be able to hand the class — enrolment,
attendance, scores, term summary — back to the pupil's re-added record."""
import datetime
import itertools
import uuid

from config import Config
from models import (db, Student, Branch, ClassArm, SchoolClass, ClassArmAssignment,
                    StudentEnrollment, Attendance, Term, AcademicSession, Week, TermSummary)
from tests.conftest import login_token

_SEQ = itertools.count()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _setup(app):
    with app.app_context():
        tag = next(_SEQ)
        bid = Branch.get_default().id
        old = AcademicSession(name=f'MV OLD {tag}', is_active=False)
        cur = AcademicSession(name=f'MV CUR {tag}', is_active=False)
        db.session.add_all([old, cur]); db.session.flush()
        term = Term(session_id=cur.id, term_number=1, name='First Term')
        db.session.add(term); db.session.flush()
        cls = SchoolClass(name=f'MVSSS3{tag}', level=12)
        arm = ClassArm(name=f'Iris{tag}', is_active=True)
        db.session.add_all([cls, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        d = datetime.date(2031, 1, 13)
        wk = Week(term_id=term.id, week_number=1, start_date=d, end_date=d + datetime.timedelta(days=4))
        db.session.add(wk); db.session.flush()
        # The graduate (left in a past session) now holds the current pupil's
        # class after a wrong merge.
        grad = Student(student_id='MVG' + uuid.uuid4().hex[:5], first_name='Osahenrhun', surname='Emma-Osagie',
                       middle_name='Israel', gender='Male', branch_id=bid, is_active=True,
                       is_graduated=True, graduation_session_id=old.id)
        db.session.add(grad); db.session.flush()
        en = StudentEnrollment(student_id=grad.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.flush()
        for i in range(3):
            db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=d + datetime.timedelta(days=i),
                                      morning_present=True, afternoon_present=i != 1))
        db.session.add(TermSummary(student_id=grad.id, term_id=term.id, enrollment_id=en.id, average_score=64))
        # The pupil, re-added, already enrolled in SSS3 Iris with one newer mark.
        pupil = Student(student_id='MVP' + uuid.uuid4().hex[:5], first_name='Osahenrhun',
                        surname='Emma-Osagie', gender='Male', branch_id=bid, is_active=True)
        db.session.add(pupil); db.session.flush()
        en2 = StudentEnrollment(student_id=pupil.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en2); db.session.flush()
        db.session.add(Attendance(enrollment_id=en2.id, week_id=wk.id, date=d + datetime.timedelta(days=3),
                                  morning_present=False, afternoon_present=False))
        db.session.commit()
        return caa.id, grad.id, pupil.id, en.id, d


def test_past_graduate_is_not_on_the_current_register(app):
    from utils.calculations import _active_enrollments
    caa, grad, pupil, _en, _d = _setup(app)
    with app.app_context():
        ids = {e.student_id for e in _active_enrollments(caa)}
        assert pupil in ids and grad not in ids
    c = _admin(app)
    r = c.get(f'/attendance/api/roster?assignment_id={caa}&date=2031-01-13').get_json()
    names = [s['name'] for s in r['students']]
    assert any('Israel' not in n for n in names) and not any('Israel' in n for n in names)


def test_move_class_records_back_to_the_readded_pupil(app):
    caa, grad, pupil, en, d = _setup(app)
    c = _admin(app)
    page = c.get(f'/students/move-records?from={grad}&to={pupil}').get_data(as_text=True)
    assert 'Move Class Records' in page and '3 attendance days' in page
    tok = page.split('name="_csrf_token" value="')[1].split('"')[0]
    r = c.post('/students/move-records', data={'_csrf_token': tok, 'from': grad, 'to': pupil,
                                                'enrollment': [en]}, follow_redirects=True)
    assert r.status_code == 200 and 'Moved' in r.get_data(as_text=True)
    with app.app_context():
        assert StudentEnrollment.query.filter_by(student_id=grad, class_arm_assignment_id=caa).count() == 0
        e2 = StudentEnrollment.query.filter_by(student_id=pupil, class_arm_assignment_id=caa).one()
        marks = Attendance.query.filter_by(enrollment_id=e2.id).count()
        assert marks == 4                                    # 3 moved + the pupil's own day
        ts = TermSummary.query.filter_by(student_id=pupil).one()
        assert ts.enrollment_id == e2.id and ts.average_score == 64
        assert db.session.get(Student, grad) is not None     # the graduate is kept


def test_merge_suggestion_warns_when_one_record_has_graduated(app):
    from flask import session
    from utils.student_merge import find_groups
    _caa, grad, pupil, _en, _d = _setup(app)
    with app.test_request_context():
        session['role'] = 'super_admin'
        g = [g for g in find_groups() if {grad, pupil} <= {m['id'] for m in g['members']}]
        assert g and any('graduated' in w for w in g[0]['warnings'])
