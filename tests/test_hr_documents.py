"""HR Phase 4 — staff documents, training/development records and performance
reviews attached to a profile."""
import io
import re
from datetime import date

from config import Config
from models import (db, StaffMember, StaffDocument, TrainingRecord, PerformanceReview,
                    CommAttachment)
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _csrf(client):
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _staff(app, tag):
    with app.app_context():
        s = StaffMember(staff_id=f'DOC{tag}', first_name='Doc', surname=f'Zz{tag}', is_active=True)
        db.session.add(s)
        db.session.commit()
        return s.id


def test_upload_and_delete_document(app):
    sid = _staff(app, 'UP1')
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/staff/{sid}/documents', headers={'X-Requested-With': 'fetch'},
                    content_type='multipart/form-data',
                    data={'title': 'Appointment letter', 'doc_type': 'Appointment letter',
                          'expires_on': '', '_csrf_token': tok,
                          'file': (io.BytesIO(b'%PDF-1.4 fake'), 'letter.pdf')}).get_json()
    assert r['ok']
    with app.app_context():
        doc = StaffDocument.query.filter_by(staff_id=sid).first()
        assert doc is not None and doc.title == 'Appointment letter' and doc.attachment_id
        did = doc.id
        att_id = doc.attachment_id
    # profile exposes it
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    assert '"documents"' in html and 'Appointment letter' in html
    # delete removes doc + attachment row
    rd = client.post(f'/hr/staff/{sid}/documents/{did}/delete', headers={'X-Requested-With': 'fetch'},
                     data={'_csrf_token': tok}).get_json()
    assert rd['ok']
    with app.app_context():
        assert db.session.get(StaffDocument, did) is None
        assert db.session.get(CommAttachment, att_id) is None


def test_document_rejects_bad_type(app):
    sid = _staff(app, 'BAD1')
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/staff/{sid}/documents', headers={'X-Requested-With': 'fetch'},
                    content_type='multipart/form-data',
                    data={'title': 'Malware', 'doc_type': 'Other', '_csrf_token': tok,
                          'file': (io.BytesIO(b'MZ'), 'x.exe')})
    assert r.status_code == 400


def test_add_training_without_certificate(app):
    sid = _staff(app, 'TRN1')
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/staff/{sid}/training', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'Classroom Management', 'kind': 'Workshop',
                          'provider': 'TRCN', 'hours': '8', 'start_date': '2025-02-01',
                          'end_date': '2025-02-02', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        t = TrainingRecord.query.filter_by(staff_id=sid).first()
        assert t is not None and t.hours == 8 and t.kind == 'Workshop'
        tid = t.id
    rd = client.post(f'/hr/staff/{sid}/training/{tid}/delete', headers={'X-Requested-With': 'fetch'},
                     data={'_csrf_token': tok}).get_json()
    assert rd['ok']
    with app.app_context():
        assert db.session.get(TrainingRecord, tid) is None


def test_add_review_and_profile_exposes_it(app):
    sid = _staff(app, 'REV1')
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/staff/{sid}/reviews', headers={'X-Requested-With': 'fetch'},
                    data={'period': '2024/2025', 'reviewer': 'Principal', 'score': '85',
                          'rating': 'Good', 'strengths': 'Punctual',
                          'improvements': 'Documentation', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        rev = PerformanceReview.query.filter_by(staff_id=sid).first()
        assert rev is not None and rev.score == 85 and rev.rating == 'Good'
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    assert '"reviews"' in html and '2024/2025' in html


def test_review_requires_period(app):
    sid = _staff(app, 'REV2')
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/staff/{sid}/reviews', headers={'X-Requested-With': 'fetch'},
                    data={'period': '', '_csrf_token': tok})
    assert r.status_code == 400
