"""One-student Mock WAEC entry: Save & next, nothing-to-save guard, preselect."""
from tests.test_subsections import _mw_session, _mw_exam, _mw_student
from tests.test_settings_react import _admin, _ptoken


def test_save_and_next_and_empty_save(app, monkeypatch):
    import routes.mock_waec as mw
    from models import db, Student
    from models.mock_waec import MockWAECResult
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 731)
    a, b = _mw_student(app, 'MWE001'), _mw_student(app, 'MWE002')
    monkeypatch.setattr(mw, 'get_sss3_students', lambda: Student.query.filter(Student.id.in_([a, b])).order_by(Student.id).all())
    monkeypatch.setattr('utils.access_control.assert_exam_student', lambda sid: None)
    c = _admin(app)
    page = c.get(f'/mock-waec/exam/{exam_id}/results/add?student={b}').get_data(as_text=True)
    assert 'Save &amp; next student' in page and f'"preselect"' not in page
    assert f'var PRESELECT = {b};' in page
    tok = _ptoken(c)
    # Nothing typed: nothing saved, back to the same student.
    r = c.post(f'/mock-waec/exam/{exam_id}/results/add', data={'_csrf_token': tok, 'student_id': a,
               'subject[]': ['Mathematics'], 'score[]': [''], 'grade[]': ['']})
    assert r.status_code in (302, 303) and f'student={a}' in r.headers['Location']
    # Save & next goes to the next student without results.
    r = c.post(f'/mock-waec/exam/{exam_id}/results/add', data={'_csrf_token': tok, 'student_id': a, 'next': '1',
               'subject[]': ['Mathematics', 'English Language'], 'score[]': ['71', '48'], 'grade[]': ['', '']})
    assert r.status_code in (302, 303) and f'student={b}' in r.headers['Location']
    with app.app_context():
        rows = {x.subject: x.grade for x in MockWAECResult.query.filter_by(student_id=a, mock_exam_id=exam_id)}
        assert rows == {'Mathematics': 'B2', 'English Language': 'D7'}
    # The last student: Save & next lands back on the exam.
    r = c.post(f'/mock-waec/exam/{exam_id}/results/add', data={'_csrf_token': tok, 'student_id': b, 'next': '1',
               'subject[]': ['Mathematics'], 'score[]': ['80'], 'grade[]': ['']})
    assert r.status_code in (302, 303) and 'student=' not in r.headers['Location']
