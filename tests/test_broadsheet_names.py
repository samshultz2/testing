"""Broadsheets: choose which name parts to show and middle name as initial."""
import uuid

from config import Config
from models import db, Student, WAECResult
from tests.conftest import login_token, enroll_sss3
from utils.name_display import name_opts, format_name, initials


class _A(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


ST = {'surname': 'Okafor', 'first_name': 'John', 'middle_name': 'Chukwuemeka Ade',
      'full_name': 'Okafor John Chukwuemeka Ade'}


def test_format_name_parts_and_initials():
    f = lambda **a: format_name(ST, name_opts(_A(a)))
    assert f(names='surname,first,middle') == 'Okafor John Chukwuemeka Ade'
    assert f(names='surname,first,middle', mid_init='1') == 'Okafor John C. A.'
    assert f(names='first,surname') == 'Okafor John'           # always register order
    assert f(names='surname') == 'Okafor'
    assert f(names='first,middle', mid_init='1') == 'John C. A.'
    assert format_name(ST, None) == 'Okafor John Chukwuemeka Ade'        # default = full name
    assert format_name(ST, name_opts(_A(names='bogus'))) == ST['full_name']
    assert initials('Akhtar-Ozomoya Ismail') == 'A.-O. I.'
    # Old cached broadsheet rows without middle_name: derived from full_name.
    old = {k: v for k, v in ST.items() if k != 'middle_name'}
    assert format_name(old, name_opts(_A(names='surname,first,middle', mid_init='1'))) == 'Okafor John C. A.'


import contextlib


@contextlib.contextmanager
def _own_rate_hits(app):
    """Remove the export rate-limit hits this test makes, so it doesn't eat into
    the shared test admin's export allowance used by later tests."""
    from models.models import RateLimitHit
    with app.app_context():
        top = db.session.query(db.func.max(RateLimitHit.id)).scalar() or 0
    try:
        yield
    finally:
        with app.app_context():
            RateLimitHit.query.filter(RateLimitHit.id > top).delete(synchronize_session=False)
            db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_waec_custom_download_uses_chosen_names(app):
    with app.app_context():
        s = Student(student_id='NM' + uuid.uuid4().hex[:6], first_name='Namefmtjohn',
                    middle_name='Chukwuemeka', surname='Namefmtokafor', gender='Male')
        db.session.add(s); db.session.flush()
        db.session.add(WAECResult(student_id=s.id, exam_year=2047, subject='Mathematics', grade='B3'))
        db.session.commit()
        sid = s.id
    enroll_sss3(app, sid)
    c = _admin(app)
    with _own_rate_hits(app):
        _waec_download_checks(c)


def _waec_download_checks(c):
    csv = c.get('/results/waec/broadsheet/download?year=2047&format=csv'
                '&names=surname,first,middle&mid_init=1').get_data(as_text=True)
    assert 'Namefmtokafor Namefmtjohn C.' in csv
    csv = c.get('/results/waec/broadsheet/download?year=2047&format=csv&names=first').get_data(as_text=True)
    assert 'Namefmtjohn' in csv and 'Namefmtokafor' not in csv
    html = c.get('/results/waec/broadsheet?year=2047').get_data(as_text=True)
    assert 'class="bs-name"' in html and 'id="bsMidInit"' in html


def test_mock_waec_broadsheet_pdf_uses_chosen_names(app):
    import fitz
    from tests.test_mock_waec_broadsheet import _session, _exam, _seed_results
    ssid = _session(app)
    exam_id = _exam(app, ssid, 77)
    with app.app_context():
        s = Student(student_id='NMW' + uuid.uuid4().hex[:5], first_name='Mockfirst',
                    middle_name='Middlemock', surname='Mocksur', gender='Female')
        db.session.add(s); db.session.commit()
        sid = s.id
    enroll_sss3(app, sid)
    _seed_results(app, exam_id, sid, {'Mathematics': 70})
    c = _admin(app)
    with _own_rate_hits(app):
        _mock_pdf_checks(c, exam_id)


def _mock_pdf_checks(c, exam_id):
    import fitz

    def text(qs):
        data = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?{qs}').get_data()
        with fitz.open(stream=data, filetype='pdf') as d:
            return ' '.join(p.get_text() for p in d)
    assert 'Middlemock' not in text('')                         # default: surname + first
    assert 'Mocksur Mockfirst M.' in text('names=surname,first,middle&mid_init=1')
    t = text('names=surname,first,middle')
    assert 'Middlemock' in t
    html = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/print').get_data(as_text=True)
    assert 'class="pdf-name"' in html and 'Names to show' in html
