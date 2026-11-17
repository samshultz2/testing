"""Marking a subject absent from the Add-results page and the per-student
edit page (the grid already could)."""
import uuid

from models import db
from models.mock_waec import MockWAECResult
from tests.conftest import auth_csrf, enroll_sss3
from tests.test_mock_waec_broadsheet_extras import _admin, _session, _exam, _student


def _rows(app, exam_id, sid):
    with app.app_context():
        return {r.subject: (r.score, r.grade, bool(r.is_absent))
                for r in MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid)}


def test_add_page_saves_absent_subjects(app):
    ex = _exam(app, _session(app), n=300 + int(uuid.uuid4().int % 600))
    sid = _student(app, 'AA' + uuid.uuid4().hex[:5].upper(), 'Abby', 'Absent')
    enroll_sss3(app, sid)
    c = _admin(app)
    html = c.get(f'/mock-waec/exam/{ex}/results/add?student={sid}').get_data(as_text=True)
    assert 'ae-abs' in html and 'absent[]' in html
    r = c.post(f'/mock-waec/exam/{ex}/results/add', data={
        '_csrf_token': auth_csrf(c), 'student_id': sid,
        'subject[]': ['English Language', 'Mathematics', 'Physics'],
        'score[]': ['66', '71', ''], 'grade[]': ['', '', ''],
        'absent[]': ['Mathematics', 'Physics']})            # absent wins over the 71 left in the box
    assert r.status_code in (302, 303)
    got = _rows(app, ex, sid)
    assert got['English Language'] == (66, 'B3', False)
    assert got['Mathematics'] == (None, None, True) and got['Physics'] == (None, None, True)


def test_add_page_accepts_only_absences(app):
    ex = _exam(app, _session(app), n=300 + int(uuid.uuid4().int % 600))
    sid = _student(app, 'AO' + uuid.uuid4().hex[:5].upper(), 'Only', 'Absent')
    enroll_sss3(app, sid)
    c = _admin(app)
    c.post(f'/mock-waec/exam/{ex}/results/add', data={
        '_csrf_token': auth_csrf(c), 'student_id': sid, 'subject[]': ['Biology'],
        'score[]': [''], 'grade[]': [''], 'absent[]': ['Biology']})
    assert _rows(app, ex, sid) == {'Biology': (None, None, True)}


def test_edit_page_marks_and_clears_absence(app):
    ex = _exam(app, _session(app), n=300 + int(uuid.uuid4().int % 600))
    sid = _student(app, 'AE' + uuid.uuid4().hex[:5].upper(), 'Edie', 'Absent')
    enroll_sss3(app, sid)
    with app.app_context():
        r = MockWAECResult(student_id=sid, mock_exam_id=ex, subject='Chemistry', score=58, grade='C5')
        db.session.add(r); db.session.commit(); rid = r.id
    c = _admin(app)
    url = f'/mock-waec/exam/{ex}/student/{sid}/edit'
    assert f'absent_{rid}' in c.get(url).get_data(as_text=True)
    c.post(url, data={'_csrf_token': auth_csrf(c), f'score_{rid}': '58', f'absent_{rid}': 'on'})
    assert _rows(app, ex, sid)['Chemistry'] == (None, None, True)
    c.post(url, data={'_csrf_token': auth_csrf(c), f'score_{rid}': '63'})      # unticked + a score
    assert _rows(app, ex, sid)['Chemistry'] == (63, 'C4', False)
    # "Add a subject" with Absent ticked needs no score.
    c.post(url, data={'_csrf_token': auth_csrf(c), 'add': '1', 'subject': 'Economics', 'score': '', 'absent': 'on'})
    assert _rows(app, ex, sid)['Economics'] == (None, None, True)
