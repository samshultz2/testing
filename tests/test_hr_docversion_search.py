"""HR Phase 9 — document version chains and the global staff quick-search."""
import io

from config import Config
from models import db, StaffMember, StaffDocument
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


def _staff(app, tag, **kw):
    with app.app_context():
        s = StaffMember(staff_id=f'DV{tag}', first_name='Doc', surname=f'Zzver{tag}',
                        is_active=True, **kw)
        db.session.add(s); db.session.commit()
        return s.id


def _upload(client, sid, tok, title, extra=None):
    data = {'title': title, 'doc_type': 'Certificate', '_csrf_token': tok,
            'file': (io.BytesIO(b'%PDF-1.4 x'), 'f.pdf')}
    data.update(extra or {})
    return client.post(f'/hr/staff/{sid}/documents', content_type='multipart/form-data',
                       headers={'X-Requested-With': 'fetch'}, data=data)


def test_replace_document_creates_version_chain(app):
    sid = _staff(app, 'V1')
    client = _admin(app)
    tok = _csrf(client)
    _upload(client, sid, tok, 'Teaching licence')
    with app.app_context():
        first = StaffDocument.query.filter_by(staff_id=sid).first()
        assert first.version == 1 and first.is_current
        fid = first.id
    r = _upload(client, sid, tok, 'Teaching licence', extra={'replace_id': fid}).get_json()
    assert r['ok']
    with app.app_context():
        docs = StaffDocument.query.filter_by(staff_id=sid).order_by(StaffDocument.version).all()
        assert len(docs) == 2
        old, new = docs
        assert old.is_current is False
        assert new.version == 2 and new.is_current and new.replaces_id == old.id


def test_profile_shows_only_current_version(app):
    sid = _staff(app, 'V2')
    client = _admin(app)
    tok = _csrf(client)
    _upload(client, sid, tok, 'Contract')
    with app.app_context():
        fid = StaffDocument.query.filter_by(staff_id=sid).first().id
    _upload(client, sid, tok, 'Contract', extra={'replace_id': fid})
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    # payload documents list carries the current doc with a version + prior chain
    assert '"version": 2' in html and '"prior"' in html


def test_staff_search_endpoint(app):
    with app.app_context():
        s = StaffMember(staff_id='SRCH99', first_name='Findable', surname='Zzsearcher',
                        designation='Registrar', is_active=True)
        db.session.add(s); db.session.commit()
    client = _admin(app)
    rows = client.get('/hr/staff/search?q=Zzsearch').get_json()
    assert any('Zzsearcher' in r['label'] and r['url'] for r in rows)
    # too-short query returns nothing
    assert client.get('/hr/staff/search?q=z').get_json() == []
