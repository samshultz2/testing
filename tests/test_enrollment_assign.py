"""Assigning students to a class: enroll persists, remove + re-enroll works,
and already-enrolled students drop out of the available list."""
import json
import re
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment)
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        if Student.query.filter_by(student_id='ENR1').first():
            t = Term.query.filter_by(name='ENR-Term').first()
            caa = ClassArmAssignment.query.filter_by(term_id=t.id).first()
            s = Student.query.filter_by(student_id='ENR1').first()
            return caa.id, s.id
        bid = Branch.get_default().id
        sess = AcademicSession(name='ENR-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='ENR-Term')
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        s = Student(student_id='ENR1', first_name='Enr', surname='One', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        return caa.id, s.id


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    """Page CSRF token from the meta tag for state-changing POSTs."""
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def _roster(c, caa_id):
    """Parse the React shell's JSON payload for a class roster page."""
    html = c.get(f'/academics/assignments/{caa_id}').get_data(as_text=True)
    m = re.search(r'id="acad-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def _enrolled(app, caa_id, sid, active=True):
    with app.app_context():
        e = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=caa_id, student_id=sid).first()
        return e is not None and e.is_active == active


def test_enroll_persists_and_reactivates(app):
    caa_id, sid = _setup(app)
    c = _admin(app)

    # available picker shows the unassigned student
    roster = _roster(c, caa_id)
    assert any(s['student_id'] == 'ENR1' for s in roster['available_students'])

    # enroll
    c.post(f'/academics/assignments/{caa_id}/enroll',
           data={'student_ids[]': [str(sid)], '_csrf_token': _pt(c)})
    assert _enrolled(app, caa_id, sid, active=True)

    # once enrolled, the student leaves the available picker and shows as enrolled
    roster = _roster(c, caa_id)
    assert not any(s['student_id'] == 'ENR1' for s in roster['available_students'])
    assert any(e['student_id'] == 'ENR1' for e in roster['enrollments'])

    # remove (soft delete) then re-enroll -> must reactivate, not silently skip
    with app.app_context():
        e = StudentEnrollment.query.filter_by(
            class_arm_assignment_id=caa_id, student_id=sid).first()
        eid = e.id
    c.post(f'/academics/enrollments/{eid}/remove', data={'_csrf_token': _pt(c)})
    assert _enrolled(app, caa_id, sid, active=False)

    c.post(f'/academics/assignments/{caa_id}/enroll',
           data={'student_ids[]': [str(sid)], '_csrf_token': _pt(c)})
    assert _enrolled(app, caa_id, sid, active=True)
