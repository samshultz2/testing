"""Mock→actual examination validation (Mock JAMB vs actual JAMB; Mock WAEC vs
actual WAEC): correlation, error, bias, calibration and threshold reliability."""
import datetime as _dt
from models import db, Branch, AcademicSession, Student, JAMBResult, WAECResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from models.mock_waec import MockWAECExam, MockWAECResult

_SEQ = [0]


def _seed_jamb(app, n=10, bias=0):
    """A Mock JAMB and matching actual JAMB results. ``bias`` shifts every
    actual score relative to the mock (to test calibration)."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'MV{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        exam = MockJAMBExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=_dt.date(2025, 1, 1), branch_id=bid)
        db.session.add(exam); db.session.flush()
        for i in range(n):
            st = Student(student_id=f'{tag}-{i}', first_name=f'S{i}', surname='T',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            mock = 150 + i * 12           # 150..258, well spread
            actual = max(0, min(400, mock + bias + (2 if i % 2 else -2)))  # tight, small noise
            db.session.add(MockJAMBResult(student_id=st.id, mock_exam_id=exam.id, total_score=mock))
            db.session.add(JAMBResult(student_id=st.id, exam_year=2025, total_score=actual))
        db.session.commit()
        return dict(session=sess.id, exam=exam.id)


def test_jamb_validation_metrics(app):
    from utils.mock_validation import jamb_validation
    ids = _seed_jamb(app, n=10, bias=0)
    with app.app_context():
        v = jamb_validation(mock_exam_id=ids['exam'])
        s = v['summary']
        assert s['matched'] == 10
        assert s['correlation'] > 0.95           # mock tracks actual almost perfectly
        assert abs(s['bias']) < 10               # ~unbiased
        assert s['bias_direction'] == 'well-calibrated'
        assert s['threshold']['cutoff'] == 200
        assert v['recommendations']


def test_jamb_validation_detects_optimistic_mock(app):
    from utils.mock_validation import jamb_validation
    ids = _seed_jamb(app, n=10, bias=-40)   # actual 40 pts below mock -> optimistic mock
    with app.app_context():
        v = jamb_validation(mock_exam_id=ids['exam'])
        assert v['summary']['bias'] < -20
        assert v['summary']['bias_direction'] == 'optimistic'
        assert any('optimistic' in r['title'].lower() for r in v['recommendations'])


def test_jamb_validation_insufficient(app):
    from utils.mock_validation import jamb_validation
    ids = _seed_jamb(app, n=2)
    with app.app_context():
        v = jamb_validation(mock_exam_id=ids['exam'])
        assert v['meta'].get('insufficient') is True


def _seed_waec(app, n=8):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'MW{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        exam = MockWAECExam(name=f'{tag} Mock', exam_number=1, session_id=sess.id,
                            exam_date=_dt.date(2025, 1, 1), branch_id=bid)
        db.session.add(exam); db.session.flush()
        grades = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8']
        for i in range(n):
            st = Student(student_id=f'{tag}-{i}', first_name=f'S{i}', surname='T',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            for subj in ('English Language', 'Mathematics'):
                g = grades[i % len(grades)]
                db.session.add(MockWAECResult(student_id=st.id, mock_exam_id=exam.id,
                                              subject=subj, score=70, grade=g))
                db.session.add(WAECResult(student_id=st.id, exam_year=2025, subject=subj, grade=g))
        db.session.commit()
        return dict(session=sess.id, exam=exam.id)


def test_waec_validation_perfect_agreement(app):
    from utils.mock_validation import waec_validation
    ids = _seed_waec(app, n=8)
    with app.app_context():
        v = waec_validation(mock_exam_id=ids['exam'])
        s = v['summary']
        assert s['matched'] == 16                # 8 students x 2 subjects
        assert s['exact_pct'] == 100.0           # mock grade == actual grade everywhere
        assert s['within1_pct'] == 100.0
        assert len(v['subjects']) == 2
        assert v['recommendations']


def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_waec_validation_route_and_exports(app):
    ids = _seed_waec(app, n=8)
    c = _admin(app)
    r = c.get(f"/mock-waec/exam/{ids['exam']}/validation")
    assert r.status_code == 200 and b'Mock' in r.data and b'Validation' in r.data
    r = c.get(f"/mock-waec/exam/{ids['exam']}/validation/export?format=pdf")
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'
    r = c.get(f"/mock-waec/exam/{ids['exam']}/validation/export?format=excel")
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']


def test_jamb_validation_route_and_exports(app):
    ids = _seed_jamb(app, n=10)
    c = _admin(app)
    r = c.get(f"/mock-jamb/validation?session_id={ids['session']}&mock_exam_id={ids['exam']}")
    assert r.status_code == 200 and b'Mock Validation' in r.data
    r = c.get(f"/mock-jamb/validation/export?mock_exam_id={ids['exam']}&format=pdf")
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'
    r = c.get(f"/mock-jamb/validation/export?mock_exam_id={ids['exam']}&format=excel")
    assert r.status_code == 200 and 'spreadsheetml' in r.headers['Content-Type']
