"""Behavioural (affective) ratings: entry grid persists, report card reflects them."""
import re
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, TermSummary)
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        if Student.query.filter_by(student_id='AFF1').first():
            t = Term.query.filter_by(name='AFF-Term').first()
            caa = ClassArmAssignment.query.filter_by(term_id=t.id).first()
            s = Student.query.filter_by(student_id='AFF1').first()
            return t.id, caa.id, s.id
        bid = Branch.get_default().id
        sess = AcademicSession(name='AFF-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='AFF-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        s = Student(student_id='AFF1', first_name='Aff', surname='Kid', gender='Male',
                    is_active=True, branch_id=bid); db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return term.id, caa.id, s.id


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def test_affective_entry_and_persist(app):
    tid, aid, sid = _setup(app)
    c = _admin(app)
    assert c.get(f'/subjects/affective?term_id={tid}&assignment_id={aid}').status_code == 200
    c.post('/subjects/affective', data={
        'term_id': tid, 'assignment_id': aid, '_csrf_token': _pt(c),
        f'r_{sid}_punctuality': '5', f'r_{sid}_honesty': '4', f'r_{sid}_neatness': '3',
    }, follow_redirects=True)
    with app.app_context():
        ts = TermSummary.query.filter_by(student_id=sid, term_id=tid).first()
        assert ts is not None
        m = ts.affective_map
        assert m.get('punctuality') == 5 and m.get('honesty') == 4 and m.get('neatness') == 3


def test_invalid_ratings_ignored(app):
    from models import TermSummary as TS
    tid, aid, sid = _setup(app)
    with app.app_context():
        ts = TS.query.filter_by(student_id=sid, term_id=tid).first() or TS(student_id=sid, term_id=tid, enrollment_id=None)
        ts.set_affective({'punctuality': 9, 'honesty': 0, 'neatness': 4})  # 9 and 0 out of range
        m = ts.affective_map
        assert 'punctuality' not in m and 'honesty' not in m and m.get('neatness') == 4
