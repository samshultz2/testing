"""Paste-text WAEC/JAMB entry: paste a result, match the student, reuse the scan
review + save flow (no OCR)."""
import uuid

import routes.results as RR
from config import Config
from models import db, Student
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _student(app, surname, first):
    with app.app_context():
        s = Student(student_id='WP' + uuid.uuid4().hex[:6].upper(), first_name=first,
                    surname=surname, gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id, s.full_name


def _pin_cohort(monkeypatch, sid):
    """Pin get_sss3_students() to our student, independent of the active session."""
    monkeypatch.setattr(RR, 'get_sss3_students', lambda: Student.query.filter_by(id=sid).all())


def test_paste_waec_preview_matches_and_renders_grid(app, monkeypatch):
    sid, full = _student(app, 'Eghosasere', 'Eldorado')
    _pin_cohort(monkeypatch, sid)
    c = _admin(app)
    text = full + "\nEnglish Language, B3\nMathematics, C4\nBiology, B2\nPhysics, A1"
    r = c.post('/results/waec/paste', data={'_csrf_token': auth_csrf(c), 'exam_year': 2024, 'data': text})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/waec/add' in body                 # rendered the review grid that saves
    assert 'value="2024"' in body and 'B3' in body and 'A1' in body
    assert f'value="{sid}" selected' in body   # student matched on name


def test_paste_jamb_preview_matches_and_renders_grid(app, monkeypatch):
    sid, full = _student(app, 'Okoro', 'Chidi')
    _pin_cohort(monkeypatch, sid)
    c = _admin(app)
    text = full + "\nTotal: 254\nUse of English, 65\nMathematics, 60\nPhysics, 70\nChemistry, 59"
    r = c.post('/results/jamb/paste', data={'_csrf_token': auth_csrf(c), 'exam_year': 2024, 'data': text})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/jamb/add' in body
    assert 'value="254"' in body and 'value="2024"' in body
    assert f'value="{sid}" selected' in body


def test_paste_waec_empty_warns(app):
    c = _admin(app)
    r = c.post('/results/waec/paste',
               data={'_csrf_token': auth_csrf(c), 'data': 'just some text, no grades here'},
               follow_redirects=True)
    assert r.status_code == 200
    assert b'No subjects' in r.data or b'Paste WAEC Result' in r.data
