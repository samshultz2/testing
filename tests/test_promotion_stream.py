"""enroll_promoted must place a promoted student in the chosen stream (arm) of the
destination class, not just reuse the old arm."""
from config import Config
from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Student, PromotionRecord)
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _setup(app):
    with app.app_context():
        fs = AcademicSession(name='PS-FROM'); ts = AcademicSession(name='PS-TO')
        db.session.add_all([fs, ts]); db.session.flush()
        t3 = Term(session_id=fs.id, term_number=3, name='Third Term')
        t1 = Term(session_id=ts.id, term_number=1, name='First Term')
        db.session.add_all([t3, t1]); db.session.flush()
        ca = SchoolClass(name='PS-A', level=1); cb = SchoolClass(name='PS-B', level=2)
        sci = ClassArm(name='Science', is_active=True); arts = ClassArm(name='Arts', is_active=True)
        db.session.add_all([ca, cb, sci, arts]); db.session.flush()
        # from: class A / Science (third term); to: class B / both arms (first term)
        a_sci = ClassArmAssignment(class_id=ca.id, arm_id=sci.id, term_id=t3.id)
        b_sci = ClassArmAssignment(class_id=cb.id, arm_id=sci.id, term_id=t1.id)
        b_arts = ClassArmAssignment(class_id=cb.id, arm_id=arts.id, term_id=t1.id)
        db.session.add_all([a_sci, b_sci, b_arts]); db.session.flush()
        st = Student(student_id='PSS1', first_name='Move', surname='Up', gender='Male', is_active=True)
        db.session.add(st); db.session.flush()
        db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=a_sci.id, is_active=True))
        # promotion record: promote to class B, stream Arts
        db.session.add(PromotionRecord(student_id=st.id, from_session_id=fs.id, to_session_id=ts.id,
                                       from_class_id=ca.id, to_class_id=cb.id, stream='Arts',
                                       status='promoted', is_manual=True))
        db.session.commit()
        return dict(fs=fs.id, ts=ts.id, st=st.id, b_sci=b_sci.id, b_arts=b_arts.id)


def test_enroll_promoted_uses_chosen_stream(app):
    ids = _setup(app)
    c = _admin(app)
    r = c.post('/promotion/enroll-promoted',
               data={'from_session_id': ids['fs'], 'to_session_id': ids['ts'],
                     '_csrf_token': auth_csrf(c)}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        # enrolled into the Arts arm of class B (the chosen stream), not Science
        assert StudentEnrollment.query.filter_by(
            student_id=ids['st'], class_arm_assignment_id=ids['b_arts']).count() == 1
        assert StudentEnrollment.query.filter_by(
            student_id=ids['st'], class_arm_assignment_id=ids['b_sci']).count() == 0
