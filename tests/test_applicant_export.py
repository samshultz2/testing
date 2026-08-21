"""Applicant emergency-contact fields persist, and the applicant record is
downloadable as a branded PDF (reportlab) and Word (.docx)."""
import re

from config import Config
from models import db, Applicant, Branch
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _seed(app):
    with app.app_context():
        bid = Branch.get_default().id
        a = Applicant(application_no='APP-TEST-01', first_name='Ada', surname='Obi',
                      gender='Female', status='Applied', branch_id=bid,
                      parent_name='Mr Obi', parent_phone='08011112222', relationship='Father',
                      emergency_name='Aunt Ngozi', emergency_phone='08033334444',
                      emergency_relationship='Aunt', emergency_address='5 Market Rd, Enugu')
        db.session.add(a); db.session.commit()
        return a.id


def test_emergency_fields_saved_via_form(app):
    client = _admin(app)
    r = client.post('/admissions/applicants/add', headers={'X-Requested-With': 'fetch'}, data={
        'first_name': 'Musa', 'surname': 'Bello', 'gender': 'Male',
        'emergency_name': 'Uncle Sani', 'emergency_phone': '07099998888',
        'emergency_relationship': 'Uncle', 'emergency_address': '12 Ikoyi crescent',
        '_csrf_token': _ptoken(client),
    })
    assert r.status_code == 200 and r.get_json().get('ok')
    with app.app_context():
        a = Applicant.query.filter_by(surname='Bello', first_name='Musa').first()
        assert a and a.emergency_name == 'Uncle Sani' and a.emergency_phone == '07099998888'
        assert a.emergency_relationship == 'Uncle' and a.emergency_address == '12 Ikoyi crescent'
        db.session.delete(a); db.session.commit()


def test_blank_application_form_is_fillable_pdf(app):
    client = _admin(app)
    r = client.get('/admissions/applicants/blank-form')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    # it is an interactive AcroForm (has fillable field objects)
    assert b'/AcroForm' in r.data and b'/Widget' in r.data

    # a black-and-white, print-friendly variant is available and still fillable
    bw = client.get('/admissions/applicants/blank-form', query_string={'bw': '1'})
    assert bw.status_code == 200 and bw.data[:4] == b'%PDF'
    assert b'/AcroForm' in bw.data and b'/Widget' in bw.data


def test_applicant_export_pdf_and_docx(app):
    aid = _seed(app)
    client = _admin(app)

    r = client.get(f'/admissions/applicants/{aid}/export', query_string={'format': 'pdf'})
    assert r.status_code == 200 and r.data[:4] == b'%PDF'

    r = client.get(f'/admissions/applicants/{aid}/export', query_string={'format': 'docx'})
    assert r.status_code == 200 and r.data[:2] == b'PK'

    # the emergency contact is included in the detail payload
    payload = client.get(f'/admissions/applicants/{aid}',
                         headers={'X-Requested-With': 'fetch'}).get_json()
    assert payload is not None
    emergency = payload.get('emergency') or []
    flat = [str(v) for _k, v in emergency]
    assert 'Aunt Ngozi' in flat and '08033334444' in flat

    with app.app_context():
        o = db.session.get(Applicant, aid)
        if o:
            db.session.delete(o); db.session.commit()
