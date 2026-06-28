"""Graduate vs current-SSS3 comparison analytics + access control."""
from datetime import date

from models import db, Student, WAECResult, JAMBResult, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from tests.conftest import login_token, auth_csrf

_SUBJECTS = ['English Language', 'Mathematics', 'Biology', 'Chemistry',
             'Physics', 'Economics']


def _mk_student(surname, graduated=False, session_id=None):
    s = Student(student_id=Student.generate_student_id(), first_name='T',
                surname=surname, gender='Male', is_active=True,
                is_graduated=graduated, graduation_session_id=session_id,
                graduation_date=date(2025, 7, 1) if graduated else None)
    db.session.add(s); db.session.flush()
    return s


def _mock_waec(student_id, session_id, scores):
    ex = MockWAECExam(name='GC Mock', exam_number=9, session_id=session_id,
                      exam_date=date(2025, 3, 1))
    db.session.add(ex); db.session.flush()
    for subj, sc in scores.items():
        db.session.add(MockWAECResult(student_id=student_id, mock_exam_id=ex.id,
                                      subject=subj, score=sc,
                                      grade=waec_grade_from_score(sc)))


def _mock_jamb(student_id, session_id, total):
    ex = MockJAMBExam(name='GC MJ', exam_number=9, session_id=session_id,
                      exam_date=date(2025, 3, 2))
    db.session.add(ex); db.session.flush()
    db.session.add(MockJAMBResult(student_id=student_id, mock_exam_id=ex.id,
                                  total_score=total))


def _seed(app):
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='GC 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()

        grad = _mk_student('Graduate', graduated=True, session_id=ssn.id)
        # Real WAEC: strong (5 credits incl. core)
        for subj in _SUBJECTS:
            db.session.add(WAECResult(student_id=grad.id, exam_year=2025,
                                      subject=subj, grade='B2'))
        db.session.add(JAMBResult(student_id=grad.id, exam_year=2025, total_score=270))
        # Mock for the graduate: weaker than real (only 4 credits vs 6) so the
        # mock->real pattern is a clear improvement.
        grad_mock = {s: 58 for s in _SUBJECTS}
        grad_mock['Physics'] = 45      # D7 — not a credit
        grad_mock['Economics'] = 45    # D7 — not a credit
        _mock_waec(grad.id, ssn.id, grad_mock)
        _mock_jamb(grad.id, ssn.id, 240)

        cur = _mk_student('Current')
        _mock_waec(cur.id, ssn.id, {s: 52 for s in _SUBJECTS})    # C6 -> credits
        _mock_jamb(cur.id, ssn.id, 210)
        db.session.commit()
        return grad.id, cur.id, ssn.id


def test_compare_cohorts_structure(app):
    grad_id, cur_id, _ = _seed(app)
    with app.app_context():
        from models.graduate_compare import compare_cohorts
        d = compare_cohorts([grad_id], [cur_id])

        assert d['cohorts']['graduates']['total'] == 1
        assert d['cohorts']['sss3']['total'] == 1

        # Real WAEC only for graduates; current class has none.
        assert d['real_waec']['graduates']['n'] == 1
        assert d['real_waec']['graduates']['avg_credits'] == 6
        assert d['real_waec']['sss3'] is None

        # Mock WAEC for both cohorts.
        assert d['mock_waec']['graduates']['n'] == 1
        assert d['mock_waec']['sss3']['n'] == 1

        # Real > mock for the graduate -> pattern improved.
        assert d['pattern']['waec_credits']['direction'] == 'improved'
        assert d['pattern']['jamb_score']['direction'] == 'improved'

        # Projection applies the positive shift to the current class's mock avg.
        assert d['projection']['waec']['projected_avg_credits'] >= \
            d['projection']['waec']['mock_avg_credits']
        assert d['projection']['jamb']['projected_avg_score'] >= \
            d['projection']['jamb']['mock_avg_score']


def test_compare_route_admin_ok(app):
    _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': 'test-admin-secret-pw', '_csrf_token': login_token(c)})
    r = c.get('/promotion/graduates/compare')
    assert r.status_code == 200


def test_compare_route_requires_login(app):
    c = app.test_client()   # not logged in
    r = c.get('/promotion/graduates/compare')
    assert r.status_code in (301, 302, 303)   # redirect to login
