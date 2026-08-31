"""Mock WAEC: score->grade derivation, paste-import preview/confirm, and the
engine signal that low mock-WAEC credits raise academic risk."""
import uuid
from datetime import date

from config import Config
from models import db, Student, AcademicSession
from models.mock_waec import (MockWAECExam, MockWAECResult, MockWAECAnalytics,
                              waec_grade_from_score)
from models.analytics_models import StudentRiskAssessment
from tests.conftest import login_token, auth_csrf, enroll_sss3


def test_subject_aliases():
    from utils.subject_match import canonical_subject
    assert canonical_subject('Eng') == 'English Language'
    assert canonical_subject('english language') == 'English Language'
    assert canonical_subject('MATHS') == 'Mathematics'
    assert canonical_subject('F. Maths') == 'Further Mathematics'
    assert canonical_subject('Econs') == 'Economics'
    assert canonical_subject('CRS') == 'Christian Religious Studies'
    assert canonical_subject('Agric') == 'Agricultural Science'
    assert canonical_subject('Computer') == 'Computer Studies'
    assert canonical_subject('Basket Weaving') is None


def test_name_match_tolerates_missing_middle_name(app):
    """Paste preview resolves a student by name when the scoresheet drops or
    reorders the middle name, and flags a genuinely unknown name."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=5)
    with app.app_context():
        st = Student(student_id='NM001', first_name='John',
                     middle_name='Adewale', surname='Okafor', gender='Male')
        db.session.add(st)
        db.session.commit()
        nm_id = st.id
    enroll_sss3(app, nm_id)
    c = _admin_client(app)
    tok = auth_csrf(c)

    def preview(data):
        return c.post(f'/mock-waec/exam/{exam_id}/results/paste',
                      data={'_csrf_token': tok, 'action': 'preview', 'data': data}).get_data(as_text=True)

    # Middle name dropped + order reversed -> still matches "Okafor John Adewale".
    html = preview('John Okafor, Maths, 70')
    assert 'Okafor John Adewale' in html and b'ready' in html.encode()
    html = preview('Okafor John, Eng, 55')
    assert 'Okafor John Adewale' in html
    # Unknown name -> flagged, nothing to import.
    html = preview('Zainab Yusuf, Maths, 50')
    assert 'No SSS3 student matches' in html


def test_grade_boundaries():
    assert waec_grade_from_score(75) == 'A1'
    assert waec_grade_from_score(74) == 'B2'
    assert waec_grade_from_score(64) == 'C4'
    assert waec_grade_from_score(50) == 'C6'
    assert waec_grade_from_score(49) == 'D7'
    assert waec_grade_from_score(39) == 'F9'
    assert waec_grade_from_score(0) == 'F9'
    assert waec_grade_from_score(None) is None


def _session(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first()
        if not s:
            s = AcademicSession(name='2025/2026', is_active=True)
            db.session.add(s)
            db.session.commit()
        return s.id


def _exam(app, session_id, n=1):
    with app.app_context():
        ex = MockWAECExam(name=f'Mock {n}', exam_number=n, session_id=session_id,
                          exam_date=date(2025, 2, n))
        db.session.add(ex)
        db.session.commit()
        return ex.id


def _student(app, adm):
    with app.app_context():
        s = Student(student_id=adm, first_name='Test', surname='Mwaec', gender='Female')
        db.session.add(s)
        db.session.commit()
        return s.id


def _admin_client(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_paste_preview_then_confirm_creates_results(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid)
    adm = 'MW' + uuid.uuid4().hex[:6].upper()
    sid = _student(app, adm)
    enroll_sss3(app, sid)
    c = _admin_client(app)
    tok = auth_csrf(c)
    # Abbreviated subjects must canonicalise (Maths -> Mathematics, Eng -> English Language).
    data = f"{adm}, Maths, 72\n{adm}, Eng, 64"

    # Preview shows ready rows without persisting anything.
    r = c.post(f'/mock-waec/exam/{exam_id}/results/paste',
               data={'_csrf_token': tok, 'action': 'preview', 'data': data})
    assert r.status_code == 200 and b'ready' in r.data
    with app.app_context():
        assert MockWAECResult.query.filter_by(mock_exam_id=exam_id).count() == 0

    # Confirm persists with auto-derived grades.
    r = c.post(f'/mock-waec/exam/{exam_id}/results/paste',
               data={'_csrf_token': tok, 'action': 'confirm', 'data': data},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid).all()
        grades = {x.subject: x.grade for x in rows}
        assert grades.get('Mathematics') == 'B2'        # 72
        assert grades.get('English Language') == 'C4'   # 64


def test_paste_flags_unknown_student(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=2)
    c = _admin_client(app)
    tok = auth_csrf(c)
    r = c.post(f'/mock-waec/exam/{exam_id}/results/paste',
               data={'_csrf_token': tok, 'action': 'preview',
                     'data': 'NoSuchPerson, Mathematics, 50'})
    assert r.status_code == 200 and b'No SSS3 student matches' in r.data


def test_low_mock_waec_credits_feed_engine(app):
    """Confirming a sub-5-credit sitting triggers a persisted risk assessment."""
    from utils.analytics_engine import AnalyticsEngine
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=3)
    adm = 'MW' + uuid.uuid4().hex[:6].upper()
    sid = _student(app, adm)
    with app.app_context():
        for subj, sc in [('Mathematics', 30), ('English Language', 35), ('Biology', 20)]:
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id,
                                          subject=subj, score=sc,
                                          grade=waec_grade_from_score(sc)))
        db.session.commit()
        AnalyticsEngine.recompute_student_risk(sid)
        risk = StudentRiskAssessment.query.filter_by(student_id=sid).first()
        assert risk is not None
        assert any('mock waec' in f.lower() for f in __import__('json').loads(risk.risk_factors))


def test_export_returns_xlsx(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=4)
    c = _admin_client(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/export')
    assert r.status_code == 200
    assert 'spreadsheet' in r.headers.get('Content-Type', '')
