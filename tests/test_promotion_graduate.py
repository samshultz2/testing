"""SSS3 bulk-graduation: an enrolled SSS3 student gets marked graduated."""
import re

import pytest
from config import Config
from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Student)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def test_graduate_sss3_marks_enrolled_student(app):
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='GRAD24/25').first()
        if not sess:
            sess = AcademicSession(name='GRAD24/25', is_active=True)
            db.session.add(sess); db.session.flush()
        term = Term.query.filter_by(session_id=sess.id, term_number=1).first()
        if not term:
            term = Term(session_id=sess.id, term_number=1, name='First Term', is_active=True)
            db.session.add(term); db.session.flush()
        # active flags must be the ones get_active_* returns
        AcademicSession.query.update({AcademicSession.is_active: False})
        Term.query.update({Term.is_active: False})
        sess.is_active = True; term.is_active = True

        sss3 = SchoolClass.query.filter_by(name='SSS3').first()
        if not sss3:
            sss3 = SchoolClass(name='SSS3', level=6); db.session.add(sss3); db.session.flush()
        arm = ClassArm.query.first()
        if not arm:
            arm = ClassArm(name='A', is_active=True); db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(
            class_id=sss3.id, arm_id=arm.id, term_id=term.id).first()
        if not caa:
            caa = ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=term.id)
            db.session.add(caa); db.session.flush()
        s = Student(student_id='GRADME', first_name='Grad', surname='Uate',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id,
                                         is_active=True))
        db.session.commit()
        sid = s.id

    c = _admin(app)
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                    c.get('/students').get_data(as_text=True)).group(1)
    c.post('/promotion/graduate-sss3', data={'_csrf_token': tok})

    with app.app_context():
        g = db.session.get(Student, sid)
        assert g.is_graduated is True
        assert g.graduation_date is not None


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def test_graduate_status_lifecycle_and_audit(app):
    from models import GraduateAudit
    with app.app_context():
        s = Student(student_id='GSTAT1', first_name='Sta', surname='Tus',
                    gender='Female', is_active=True, is_graduated=True,
                    graduate_status='Graduated')
        db.session.add(s); db.session.commit()
        sid = s.id

    c = _admin(app)
    tok = _csrf(c)
    # advance the lifecycle status with a reason -> writes an audit row
    r = c.post(f'/promotion/graduates/{sid}/status',
               data={'status': 'Certificate Issued', 'reason': 'Collected 12 Aug',
                     '_csrf_token': tok}, headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['ok'] is True

    with app.app_context():
        g = db.session.get(Student, sid)
        assert g.graduate_status == 'Certificate Issued'
        a = GraduateAudit.query.filter_by(student_id=sid).order_by(GraduateAudit.id.desc()).first()
        assert a and a.old_value == 'Graduated' and a.new_value == 'Certificate Issued'
        assert a.reason == 'Collected 12 Aug' and a.actor

    # an invalid status is rejected
    r = c.post(f'/promotion/graduates/{sid}/status',
               data={'status': 'Nonsense', '_csrf_token': tok},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400

    # un-graduate returns JSON (redirect to the graduates list) and clears the flag
    r = c.post(f'/promotion/ungraduate/{sid}', data={'_csrf_token': tok},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        assert db.session.get(Student, sid).is_graduated is False
