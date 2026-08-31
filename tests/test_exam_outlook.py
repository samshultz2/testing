"""Cohort JAMB outlook: projected mean ± measured error, confidence breakdown,
and predicted-score distribution (predictions dashboard)."""
import uuid
from datetime import date

from config import Config
from models import db, AcademicSession, Student, JAMBResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from tests.conftest import login_token
from utils import exam_insights as EI


def _session(app):
    with app.app_context():
        s = AcademicSession(name='OL ' + uuid.uuid4().hex[:5])
        db.session.add(s); db.session.commit()
        return s.id


def _student_with_mocks(app, ssid, scores):
    """A student with a Mock JAMB result per score (one exam per sitting)."""
    with app.app_context():
        s = Student(student_id='OL' + uuid.uuid4().hex[:7].upper(), first_name='Out',
                    surname='Look', gender='Male')
        db.session.add(s); db.session.flush()
        for n, total in enumerate(scores, 1):
            ex = MockJAMBExam(name=f'MJ{n}', exam_number=n, session_id=ssid,
                              exam_date=date(2025, 1, n))
            db.session.add(ex); db.session.flush()
            db.session.add(MockJAMBResult(student_id=s.id, mock_exam_id=ex.id, total_score=total))
        db.session.commit()
        return s.id


def test_outlook_aggregates_mean_band_confidence_distribution(app):
    ssid = _session(app)
    ids = [_student_with_mocks(app, ssid, [200, 210]),   # ~2 mocks → medium confidence
           _student_with_mocks(app, ssid, [250, 260]),
           _student_with_mocks(app, ssid, [150, 160])]
    with app.app_context():
        students = [db.session.get(Student, i) for i in ids]
        out = EI.cohort_jamb_outlook(students, ssid, calibration=None, mae=20)

    assert out['assessed'] == 3
    # band is the projected mean ± the supplied MAE
    assert out['band_low'] == max(0, out['projected_mean'] - 20)
    assert out['band_high'] == min(400, out['projected_mean'] + 20)
    # every projected student lands in exactly one score band
    assert sum(b['count'] for b in out['bands']) == 3
    # confidence buckets partition the cohort; 2 sittings → medium
    assert sum(out['confidence'].values()) == 3
    assert out['confidence']['medium'] == 3          # 2 sittings → medium band
    assert 40 <= out['mean_confidence'] < 80


def test_outlook_empty_when_no_projections(app):
    ssid = _session(app)
    with app.app_context():
        out = EI.cohort_jamb_outlook([], ssid, mae=20)
    assert out['assessed'] == 0 and out['projected_mean'] is None
    assert out['band_low'] is None
    assert sum(b['count'] for b in out['bands']) == 0
    assert sum(out['confidence'].values()) == 0


def test_outlook_no_mae_leaves_band_open(app):
    ssid = _session(app)
    sid = _student_with_mocks(app, ssid, [220, 230])
    with app.app_context():
        out = EI.cohort_jamb_outlook([db.session.get(Student, sid)], ssid, mae=None)
    assert out['assessed'] == 1
    assert out['band_low'] is None and out['band_high'] is None


def test_predictions_dashboard_renders(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    resp = c.get('/results/predictions')
    assert resp.status_code == 200
