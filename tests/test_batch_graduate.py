"""Batch graduation: pick the session, tick students, choose the graduation
date (last day of the session, or the day it's processed)."""
import uuid
from datetime import date

from config import Config
from models import (db, Student, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment)
from tests.conftest import login_token, auth_csrf
from utils import timeutil


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _sss3_cohort(app, session_name, end_date, n=3):
    """An (inactive) session with an SSS3 arm in its last term and ``n`` pupils."""
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name=session_name).first()
        if ssn is None:
            ssn = AcademicSession(name=session_name, is_active=False, end_date=end_date)
            db.session.add(ssn); db.session.flush()
            db.session.add(Term(session_id=ssn.id, term_number=3, name='Third Term', is_active=False,
                                end_date=end_date))
            db.session.flush()
        term = Term.query.filter_by(session_id=ssn.id).first()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=6)
        db.session.add(sss3); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=sss3.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=term.id))
        db.session.add(caa); db.session.flush()
        ids = []
        for i in range(n):
            st = Student(student_id='BG' + uuid.uuid4().hex[:6], first_name=f'Grad{i}',
                         surname=session_name.replace('/', ''), gender='Female')
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
            ids.append(st.id)
        db.session.commit()
        return ssn.id, ids


def test_preview_lists_the_chosen_sessions_sss3_with_both_dates(app):
    sid, ids = _sss3_cohort(app, '2041/2042', date(2042, 7, 24))
    c = _admin(app)
    data = c.get(f'/promotion/graduate-sss3/preview?session_id={sid}',
                 headers={'X-Requested-With': 'fetch'}).get_json()
    assert data['session']['id'] == sid
    assert data['session_end'] == '2042-07-24' and data['session_end_label'] == '24 July 2042'
    assert data['today'] == timeutil.today().isoformat()
    assert {s['id'] for s in data['students']} == set(ids)
    # The page itself renders too.
    assert c.get(f'/promotion/graduate-sss3/preview?session_id={sid}').status_code == 200


def test_graduates_only_ticked_students_with_session_end_date(app):
    sid, (a, b, keep) = _sss3_cohort(app, '2042/2043', date(2043, 7, 30))
    c = _admin(app)
    r = c.post('/promotion/graduate-sss3', data={'_csrf_token': auth_csrf(c), 'session_id': sid,
                                                 'date_mode': 'session_end', 'student_ids': [a, b]})
    assert r.status_code in (200, 302)
    with app.app_context():
        for i in (a, b):
            st = db.session.get(Student, i)
            assert st.is_graduated and st.graduation_date == date(2043, 7, 30)
            assert st.graduation_session_id == sid
        assert not db.session.get(Student, keep).is_graduated


def test_graduation_date_can_be_the_processing_day(app):
    sid, (a,) = _sss3_cohort(app, '2043/2044', date(2044, 7, 30), n=1)
    c = _admin(app)
    c.post('/promotion/graduate-sss3', data={'_csrf_token': auth_csrf(c), 'session_id': sid,
                                             'date_mode': 'today', 'student_ids': [a]})
    with app.app_context():
        assert db.session.get(Student, a).graduation_date == timeutil.today()


def test_session_end_mode_needs_an_end_date_and_ignores_non_sss3_ids(app):
    sid, (a,) = _sss3_cohort(app, '2044/2045', None, n=1)
    with app.app_context():
        outsider = Student(student_id='BGX' + uuid.uuid4().hex[:5], first_name='Not', surname='Sss3',
                           gender='Male')
        db.session.add(outsider); db.session.commit()
        out_id = outsider.id
    c = _admin(app)
    tok = auth_csrf(c)
    c.post('/promotion/graduate-sss3', data={'_csrf_token': tok, 'session_id': sid,
                                             'date_mode': 'session_end', 'student_ids': [a]})
    with app.app_context():
        assert not db.session.get(Student, a).is_graduated            # refused: no end date
    c.post('/promotion/graduate-sss3', data={'_csrf_token': tok, 'session_id': sid,
                                             'date_mode': 'today', 'student_ids': [a, out_id]})
    with app.app_context():
        assert db.session.get(Student, a).is_graduated
        assert not db.session.get(Student, out_id).is_graduated       # not SSS3 → ignored
