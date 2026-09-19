"""The WAEC/JAMB add-result dropdowns must hide students who already have that
year's result entered, so results are never entered twice. Covers the shared
routes.results.students_needing_result filter, plus the student-profile
"Add" deep-link that must pre-select the named student on /waec/add and
/jamb/add.
"""
import types
import uuid
from datetime import date

from config import Config
from models import db, Student, JAMBResult, WAECResult
import routes.results as RR
from routes.results import students_needing_result
from tests.conftest import login_token


def _student(sid, surname):
    s = Student(student_id=sid, first_name='T', surname=surname,
                gender='Male', is_active=True)
    db.session.add(s); db.session.flush()
    return s


def test_jamb_filter_hides_students_with_this_years_result(app):
    year = date.today().year
    with app.app_context():
        done = _student('JF-DONE', 'Done')
        todo = _student('JF-TODO', 'Todo')
        db.session.add(JAMBResult(student_id=done.id, exam_year=year, total_score=250))
        # A prior-year result must NOT hide them from this year's entry.
        db.session.add(JAMBResult(student_id=todo.id, exam_year=year - 1, total_score=200))
        db.session.commit()
        cohort = [done, todo]

        remaining = students_needing_result(cohort, JAMBResult, year)
        ids = {s.id for s in remaining}
        assert todo.id in ids            # no result this year → still offered
        assert done.id not in ids        # already has this year's result → hidden

        # Cleanup
        JAMBResult.query.filter(JAMBResult.student_id.in_([done.id, todo.id])).delete(
            synchronize_session=False)
        for s in (done, todo):
            db.session.delete(s)
        db.session.commit()


def test_waec_filter_hides_students_with_this_years_result(app):
    year = date.today().year
    with app.app_context():
        done = _student('WF-DONE', 'Done')
        todo = _student('WF-TODO', 'Todo')
        # WAEC has one row per subject; any row for the year counts as "entered".
        db.session.add(WAECResult(student_id=done.id, exam_year=year,
                                  subject='Mathematics', grade='A1'))
        db.session.commit()
        cohort = [done, todo]

        remaining = students_needing_result(cohort, WAECResult, year)
        ids = {s.id for s in remaining}
        assert todo.id in ids
        assert done.id not in ids

        WAECResult.query.filter(WAECResult.student_id.in_([done.id, todo.id])).delete(
            synchronize_session=False)
        for s in (done, todo):
            db.session.delete(s)
        db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pin_cohort(monkeypatch, ids):
    """Pin get_sss3_students() to an exact id list, independent of the active
    session/enrolment — patched on every routes.results submodule since each
    does its own `from routes.results import *` binding (see test_waec_paste.py)."""
    fn = lambda: Student.query.filter(Student.id.in_(ids)).all()
    targets = [RR] + [getattr(RR, n) for n in dir(RR)
                      if isinstance(getattr(RR, n), types.ModuleType)]
    for mod in targets:
        if hasattr(mod, 'get_sss3_students'):
            monkeypatch.setattr(mod, 'get_sss3_students', fn, raising=False)


def test_waec_add_preselects_student_from_profile_link(app, monkeypatch):
    """A student profile's WAEC "Add" button links to /waec/add?student_id=N —
    that student must come pre-selected, and must still appear in the list even
    if they already have this year's result (so the link never 404s into an
    empty picker)."""
    year = date.today().year
    with app.app_context():
        already = Student(student_id='PS' + uuid.uuid4().hex[:6].upper(), first_name='Pre',
                          surname='Selected', gender='Female', is_active=True)
        db.session.add(already); db.session.flush()
        db.session.add(WAECResult(student_id=already.id, exam_year=year,
                                  subject='Mathematics', grade='A1'))
        db.session.commit()
        sid = already.id
    _pin_cohort(monkeypatch, [sid])
    c = _admin(app)
    html = c.get(f'/results/waec/add?student_id={sid}').get_data(as_text=True)
    assert f'value="{sid}"' in html               # kept in the dropdown despite already having a result
    assert str(sid) in html                       # PRESELECT constant fed to the pre-select script


def test_jamb_add_preselects_student_from_profile_link(app, monkeypatch):
    year = date.today().year
    with app.app_context():
        already = Student(student_id='PJ' + uuid.uuid4().hex[:6].upper(), first_name='Pre',
                          surname='Jay', gender='Male', is_active=True)
        db.session.add(already); db.session.flush()
        db.session.add(JAMBResult(student_id=already.id, exam_year=year, total_score=250))
        db.session.commit()
        sid = already.id
    _pin_cohort(monkeypatch, [sid])
    c = _admin(app)
    html = c.get(f'/results/jamb/add?student_id={sid}').get_data(as_text=True)
    assert f'value="{sid}"' in html
    assert str(sid) in html


def test_jamb_add_form_has_client_side_total_autocalc(app):
    """The total-score field must be wired to the four subject-score inputs so
    the total adds up as the user types (see templates/results/add_jamb.html)."""
    c = _admin(app)
    html = c.get('/results/jamb/add').get_data(as_text=True)
    assert 'jamb-score' in html and 'recalcTotal' in html and 'id="totalScore"' in html
