"""Cohort-aware class-arm league for external (WAEC/JAMB) results."""
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, WAECResult, JAMBResult)

_SEQ = [0]


def _seed(app):
    """Two SSS3 arms (A stronger, B weaker) with WAEC + JAMB results in 2025."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'ECL{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=3, name='Third Term'); db.session.add(term); db.session.flush()
        sss3 = SchoolClass(name=f'{tag}-SSS3', level=6, section='senior', is_active=True)
        db.session.add(sss3); db.session.flush()
        armA = ClassArm(name=f'{tag}-A'); armB = ClassArm(name=f'{tag}-B')
        db.session.add_all([armA, armB]); db.session.flush()

        def arm_assignment(arm):
            caa = ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            return caa
        caaA, caaB = arm_assignment(armA), arm_assignment(armB)

        def add_student(caa, jamb, waec_grades):
            _SEQ[0] += 1
            st = Student(student_id=f'{tag}-{_SEQ[0]}', first_name='S', surname='T',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
            db.session.add(JAMBResult(student_id=st.id, exam_year=2025, total_score=jamb))
            for subj, g in waec_grades.items():
                db.session.add(WAECResult(student_id=st.id, exam_year=2025, subject=subj, grade=g))

        strong = {'English Language': 'B2', 'Mathematics': 'B3', 'Physics': 'C4',
                  'Chemistry': 'C5', 'Biology': 'C6'}
        weak = {'English Language': 'D7', 'Mathematics': 'E8', 'Physics': 'F9',
                'Chemistry': 'C6', 'Biology': 'D7'}
        for _ in range(3):
            add_student(caaA, 260, strong)
        for _ in range(3):
            add_student(caaB, 180, weak)
        db.session.commit()
        return dict(sss3=sss3.id)


def test_class_league_ranks_arms(app):
    from utils.exam_class_league import exam_class_league
    _seed(app)
    with app.app_context():
        d = exam_class_league(2025)
        assert d['summary']['arms'] == 2
        assert d['meta']['matched'] == 6
        arms = d['units']
        # arm A (JAMB 260, 5 credits incl. core) ranks above arm B
        assert arms[0]['jamb_mean'] == 260 and arms[-1]['jamb_mean'] == 180
        top, bottom = arms[0], arms[-1]
        assert top['five_core_rate'] == 100.0        # A: 5 credits incl Eng+Maths
        assert bottom['five_core_rate'] == 0.0        # B: fails core
        assert top['jamb_above_rate'] == 100.0        # all ≥ 200
        assert bottom['jamb_above_rate'] == 0.0
        assert d['recommendations']


def test_class_league_empty_year(app):
    from utils.exam_class_league import exam_class_league
    with app.app_context():
        d = exam_class_league(1999)
        assert d['meta'].get('insufficient') is True


def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_class_league_route_and_export(app):
    _seed(app)
    c = _admin(app)
    r = c.get('/results/analytics/by-class?year=2025')
    assert r.status_code == 200 and b'Class Arm' in r.data
    r = c.get('/results/analytics/by-class/export?year=2025')
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']
    assert r.get_data()[:2] == b'PK'
