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
    """Pin get_sss3_students() to our student, independent of the active session.

    routes.results is now a package whose route submodules each hold their own
    `from routes.results import *` binding of get_sss3_students, so patch the name on
    every submodule that has it (and the package itself) — patch where it is looked up.
    """
    import types
    fn = lambda: Student.query.filter_by(id=sid).all()
    targets = [RR] + [getattr(RR, n) for n in dir(RR)
                      if isinstance(getattr(RR, n), types.ModuleType)]
    for mod in targets:
        if hasattr(mod, 'get_sss3_students'):
            monkeypatch.setattr(mod, 'get_sss3_students', fn, raising=False)


def test_paste_waec_preview_matches_and_renders_grid(app, monkeypatch):
    sid, full = _student(app, 'Eghosasere', 'Eldorado')
    _pin_cohort(monkeypatch, sid)
    c = _admin(app)
    text = full + "\nEnglish Language, B3\nMathematics, C4\nBiology, B2\nPhysics, A1"
    r = c.post('/results/waec/paste', data={'_csrf_token': auth_csrf(c), 'exam_year': 2024, 'data': text})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/waec/paste/save' in body          # rendered the review grid that saves
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


def test_waec_student_page_can_open_and_edit_every_year(app):
    """Every WAEC sitting is reachable and editable from the student page, not
    only the latest one."""
    from models import WAECResult
    sid, _ = _student(app, 'Multiyear', 'Kemi')
    with app.app_context():
        for y, g in ((2023, 'C6'), (2024, 'C5'), (2025, 'B3')):
            db.session.add(WAECResult(student_id=sid, exam_year=y, subject='Mathematics', grade=g))
        db.session.commit()
    c = _admin(app)
    html = c.get(f'/results/waec/student/{sid}').get_data(as_text=True)
    assert f'/results/waec/student/{sid}/edit/2025' in html            # latest by default
    for y in (2023, 2024):
        assert f'/results/waec/student/{sid}?year={y}' in html          # year switcher
    html = c.get(f'/results/waec/student/{sid}?year=2023').get_data(as_text=True)
    assert 'Results (2023)' in html and f'/results/waec/student/{sid}/edit/2023' in html
    r = c.post(f'/results/waec/student/{sid}/edit/2023', data={
        '_csrf_token': auth_csrf(c), 'subject[]': ['Mathematics'], 'grade[]': ['B2']})
    assert r.headers['Location'].endswith(f'/results/waec/student/{sid}?year=2023')
    with app.app_context():
        got = {w.exam_year: w.grade for w in WAECResult.query.filter_by(student_id=sid)}
    assert got == {2023: 'B2', 2024: 'C5', 2025: 'B3'}


def test_waec_dashboard_sorts_by_name_and_distinctions(app):
    from models import WAECResult
    from tests.conftest import enroll_sss3
    zed, _ = _student(app, 'Sortwaec', 'Zed')      # 2 distinctions
    amy, _ = _student(app, 'Sortwaec', 'Amy')      # none
    with app.app_context():
        for sid, grades in ((zed, ('A1', 'B3', 'C4')), (amy, ('C5', 'C6', 'D7'))):
            for subj, g in zip(('Mathematics', 'English Language', 'Biology'), grades):
                db.session.add(WAECResult(student_id=sid, exam_year=2038, subject=subj, grade=g))
        db.session.commit()
    for sid in (zed, amy):
        enroll_sss3(app, sid)
    c = _admin(app)

    def amy_first(qs):
        html = c.get(f'/results/waec?year=2038&search=Sortwaec&{qs}').get_data(as_text=True)
        assert 'id="waecSort"' in html
        html = html[html.index('id="waecStudentList"'):]
        return html.index('Sortwaec Amy') < html.index('Sortwaec Zed')
    assert amy_first('sort=name') is True
    assert amy_first('sort=name_desc') is False
    assert amy_first('sort=name&order=desc') is False          # old button links still work
    assert amy_first('sort=distinctions') is False
    html = c.get('/results/waec?year=2038&search=Sortwaec&sort=distinctions').get_data(as_text=True)
    assert '<option value="distinctions" selected>' in html
    assert 'search=Sortwaec' in html[html.index('id="waecStudentList"'):]  # sort links keep the search


def test_waec_pickers_hide_students_who_already_have_results(app, monkeypatch):
    from models import WAECResult
    done, done_name = _student(app, 'Pickdone', 'Ada')
    todo, _ = _student(app, 'Picktodo', 'Ben')
    with app.app_context():
        db.session.add(WAECResult(student_id=done, exam_year=2039, subject='Mathematics', grade='B3'))
        db.session.commit()
    import types
    fn = lambda: Student.query.filter(Student.id.in_([done, todo])).all()
    for mod in [RR] + [getattr(RR, n) for n in dir(RR) if isinstance(getattr(RR, n), types.ModuleType)]:
        if hasattr(mod, 'get_sss3_students'):
            monkeypatch.setattr(mod, 'get_sss3_students', fn, raising=False)
    c = _admin(app)
    html = c.get('/results/waec/add?year=2039').get_data(as_text=True)
    assert f'value="{todo}"' in html and f'value="{done}"' not in html
    assert f'value="{done}"' in c.get('/results/waec/add?year=2040').get_data(as_text=True)
    # Paste review: hidden too, unless the slip is for that student.
    r = c.post('/results/waec/paste', data={'_csrf_token': auth_csrf(c), 'exam_year': 2039,
               'data': 'Someone Else Entirely\nMathematics, A1'}).get_data(as_text=True)
    assert f'value="{done}"' not in r and f'value="{todo}"' in r
    r = c.post('/results/waec/paste', data={'_csrf_token': auth_csrf(c), 'exam_year': 2039,
               'data': done_name + '\nMathematics, A1'}).get_data(as_text=True)
    assert f'value="{done}" selected' in r
