"""Formula-injection regression coverage for export routes that write
attacker/lower-privilege-influenced free text into a CSV/XLSX cell.

Excel and Sheets execute a cell that starts with ``=``, ``+``, ``-`` or ``@``
as a formula when the file is opened, so a spreadsheet export of records
written by an applicant, an alumnus self-service portal, or an anonymous
website visitor must run every such field through
``utils.web_exports.formula_guard`` before it lands in the sheet. Each test
here seeds a record whose free-text field is a formula-injection payload and
asserts the exported cell/row was neutralised (prefixed with a leading
quote) rather than written raw.
"""
import re
import uuid

from config import Config
from tests.conftest import login_token

PAYLOAD = "=cmd|'/c calc'!A1"
GUARDED = "'" + PAYLOAD


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_admissions_export_guards_applicant_free_text(app):
    from models import db, Applicant
    with app.app_context():
        a = Applicant(first_name=PAYLOAD, surname='X', parent_name=PAYLOAD,
                      parent_phone=PAYLOAD, application_no='INJ' + uuid.uuid4().hex[:6])
        db.session.add(a); db.session.commit()

    body = _admin(app).get('/admissions/export').get_data(as_text=True)
    assert GUARDED in body


def test_library_export_guards_title_and_author(app):
    from models import db, Book
    with app.app_context():
        db.session.add(Book(title=PAYLOAD, author=PAYLOAD, is_active=True))
        db.session.commit()

    body = _admin(app).get('/library/export').get_data(as_text=True)
    assert GUARDED in body


def test_alumni_export_guards_self_service_profile_fields(app):
    from models import db, Student, AcademicSession, AlumniProfile
    with app.app_context():
        sess = AcademicSession(name='InjAlumni ' + uuid.uuid4().hex[:5])
        db.session.add(sess); db.session.flush()
        s = Student(student_id='INJ' + uuid.uuid4().hex[:7].upper(), first_name='A',
                    surname='Alumnus', gender='Male', is_active=True, is_graduated=True,
                    graduate_status='Graduated', graduation_session_id=sess.id)
        db.session.add(s); db.session.flush()
        db.session.add(AlumniProfile(student_id=s.id, occupation=PAYLOAD, employer=PAYLOAD))
        db.session.commit()

    body = _admin(app).get('/promotion/alumni/export').get_data(as_text=True)
    assert GUARDED in body


def test_website_analytics_export_guards_visitor_controlled_referrer_and_path(app):
    from utils import site_analytics

    class _FakeReq:
        headers = {'User-Agent': 'RealBrowser/1.0', 'Referer': f'http://{PAYLOAD}/x'}
        host = 'school.example'

    with app.app_context():
        site_analytics.record(PAYLOAD, _FakeReq())

    body = _admin(app).get('/website/analytics/export').get_data(as_text=True)
    assert GUARDED in body
