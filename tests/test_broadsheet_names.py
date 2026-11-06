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
    assert f(names='surname,first,middle', mid_init='1') == 'Okafor C. A. John'
    assert f(names='first,surname') == 'Okafor John'           # always register order
    assert f(names='surname') == 'Okafor'
    assert f(names='first,middle', mid_init='1') == 'C. A. John'
    assert format_name(ST, None) == 'Okafor John Chukwuemeka Ade'        # default = full name
    assert format_name(ST, name_opts(_A(names='bogus'))) == ST['full_name']
    assert initials('Akhtar-Ozomoya Ismail') == 'A.-O. I.'
    # Old cached broadsheet rows without middle_name: derived from full_name.
    old = {k: v for k, v in ST.items() if k != 'middle_name'}
    assert format_name(old, name_opts(_A(names='surname,first,middle', mid_init='1'))) == 'Okafor C. A. John'


import contextlib


@contextlib.contextmanager
def _own_rate_hits(app):
    """Remove the export rate-limit hits this test makes, so it doesn't eat into
    the shared test admin's export allowance used by later tests."""
    from models.models import RateLimitHit
    with app.app_context():
        RateLimitHit.query.filter(RateLimitHit.rkey.like('%export%')).delete(synchronize_session=False)
        db.session.commit()
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
    assert 'Namefmtokafor C. Namefmtjohn' in csv
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
    assert 'Mocksur M. Mockfirst' in text('names=surname,first,middle&mid_init=1')
    t = text('names=surname,first,middle')
    assert 'Middlemock' in t
    html = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/print').get_data(as_text=True)
    assert 'class="pdf-name"' in html and 'Names to show' in html


def test_blank_sheet_rows_grow_so_long_names_dont_overlap(app):
    """With surname + first + middle shown, a name that wraps onto 3 lines
    must not spill into the next student's row on the blank recording sheet."""
    import fitz
    from types import SimpleNamespace as NS
    from utils.mock_waec_pdf import blank_broadsheet_pdf
    studs = [NS(id=1, surname='Abdulwahab', first_name='Iluedo', middle_name='Akhtar-Ozomoya Ismail',
                full_name='Abdulwahab Iluedo Akhtar-Ozomoya Ismail', student_id='S1'),
             NS(id=2, surname='Zubairnext', first_name='Ade', middle_name=None,
                full_name='Zubairnext Ade', student_id='S2')]
    exam = NS(display_name='Mock 1', name='Mock 1', exam_number=1, exam_date=None,
              session=NS(name='2025/2026'))
    fmt = name_opts(_A(names='surname,first,middle'))
    with app.app_context():
        buf = blank_broadsheet_pdf(studs, {1: {'Mathematics'}, 2: {'Mathematics'}}, ['Mathematics'],
                                   exam, {'name': 'Demo'}, opts={'name_fmt': fmt})
    data = buf.getvalue() if hasattr(buf, 'getvalue') else buf
    with fitz.open(stream=data, filetype='pdf') as d:
        words = {w[4]: w for w in d[0].get_text('words')}
    last_line_bottom = words['Ismail'][3]
    next_name_top = words['Zubairnext'][1]
    assert last_line_bottom < next_name_top - 4          # clear gap, no overlap
