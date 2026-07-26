"""Phase 3 — alumni self-service portal + admin alumni records."""
import re

from config import Config
from models import db, Student, GraduateDocument, AlumniProfile, DocumentRequest
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def _grad(app, sid='ALU1', pw=None):
    with app.app_context():
        s = Student(student_id=sid, first_name='Alum', surname='Nus',
                    gender='Male', is_active=True, is_graduated=True,
                    graduate_status='Graduated')
        if pw:
            s.set_portal_password(pw)
        db.session.add(s); db.session.commit()
        return s.id


def _portal_csrf(c):
    html = c.get('/alumni/login').get_data(as_text=True)
    return re.search(r'name="_csrf_token" value="([0-9a-f]+)"', html).group(1)


def _meta_csrf(c, path):
    html = c.get(path).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"', html).group(1)


def test_login_with_portal_password_and_home(app):
    sid = _grad(app, 'ALUPW', pw='secretpw')
    c = app.test_client()
    tok = _portal_csrf(c)
    r = c.post('/alumni/login', data={'student_id': 'ALUPW', 'credential': 'secretpw',
                                      '_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200 and b'My Documents' in r.data
    # wrong credential is rejected
    c2 = app.test_client()
    tok2 = _portal_csrf(c2)
    r2 = c2.post('/alumni/login', data={'student_id': 'ALUPW', 'credential': 'nope',
                                        '_csrf_token': tok2}, follow_redirects=True)
    assert b'Invalid admission number' in r2.data


def test_login_with_verification_code(app):
    sid = _grad(app, 'ALUVC')
    admin = _admin(app)
    # issue a document so a verification code exists
    admin.get(f'/promotion/graduates/{sid}/document/slc')
    with app.app_context():
        code = GraduateDocument.query.filter_by(student_id=sid, doc_type='slc').first().verification_code
    c = app.test_client()
    tok = _portal_csrf(c)
    r = c.post('/alumni/login', data={'student_id': 'ALUVC', 'credential': code,
                                      '_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200 and b'My Documents' in r.data
    # the alumnus can download their own issued document
    assert c.get('/alumni/document/slc').data[:4] == b'%PDF'
    # but not a document that was never issued
    assert c.get('/alumni/document/transcript').status_code == 404


def test_alumnus_updates_profile_and_requests_document(app):
    sid = _grad(app, 'ALUPR', pw='secretpw')
    c = app.test_client()
    tok = _portal_csrf(c)
    c.post('/alumni/login', data={'student_id': 'ALUPR', 'credential': 'secretpw',
                                  '_csrf_token': tok})
    ptok = _meta_csrf(c, '/alumni/')   # token from home meta (session rotated at login)
    # update profile
    r = c.post('/alumni/profile', data={
        'occupation': 'Engineer', 'employer': 'ACME', 'willing_to_mentor': '1',
        '_csrf_token': ptok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        p = AlumniProfile.query.filter_by(student_id=sid).first()
        assert p and p.occupation == 'Engineer' and p.willing_to_mentor is True
        assert p.updated_by == 'self'
    # request a document
    r = c.post('/alumni/request', data={'doc_type': 'transcript', 'note': 'For uni',
                                        '_csrf_token': ptok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        req = DocumentRequest.query.filter_by(student_id=sid).first()
        assert req and req.doc_type == 'transcript' and req.status == 'pending'
    # a duplicate pending request is refused
    r = c.post('/alumni/request', data={'doc_type': 'transcript', '_csrf_token': ptok},
               follow_redirects=True)
    assert b'already have a pending request' in r.data


def test_admin_fulfils_and_declines_requests(app):
    sid = _grad(app, 'ALUAD', pw='secretpw')
    with app.app_context():
        db.session.add(DocumentRequest(student_id=sid, doc_type='transcript', status='pending'))
        db.session.add(DocumentRequest(student_id=sid, doc_type='testimonial', status='pending'))
        db.session.commit()
        rq_fulfil = DocumentRequest.query.filter_by(student_id=sid, doc_type='transcript').first().id
        rq_decline = DocumentRequest.query.filter_by(student_id=sid, doc_type='testimonial').first().id
    admin = _admin(app)
    tok = _csrf(admin)
    # directory + inbox render
    j = admin.get('/promotion/alumni', headers={'X-Requested-With': 'fetch'}).get_json()
    mine = [r for r in j['requests'] if r['student_id'] == sid]
    assert j['page'] == 'alumni' and len(mine) == 2
    # fulfil -> PDF + status fulfilled + document created
    r = admin.get(f'/promotion/alumni/requests/{rq_fulfil}/fulfil')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    with app.app_context():
        assert db.session.get(DocumentRequest, rq_fulfil).status == 'fulfilled'
        assert GraduateDocument.query.filter_by(student_id=sid, doc_type='transcript').first()
    # decline with a note
    r = admin.post(f'/promotion/alumni/requests/{rq_decline}/decline',
                   data={'response_note': 'Not eligible', '_csrf_token': tok},
                   headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        d = db.session.get(DocumentRequest, rq_decline)
        assert d.status == 'declined' and d.response_note == 'Not eligible'


def test_admin_edits_alumni_profile_and_sets_password(app):
    sid = _grad(app, 'ALUED')
    admin = _admin(app)
    tok = _csrf(admin)
    r = admin.post(f'/promotion/graduates/{sid}/alumni',
                   json={'occupation': 'Doctor', 'city': 'Lagos', 'willing_to_mentor': True},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        p = AlumniProfile.query.filter_by(student_id=sid).first()
        assert p.occupation == 'Doctor' and p.city == 'Lagos' and p.willing_to_mentor is True
        assert p.updated_by and p.updated_by != 'self'
    # set portal password (too short is rejected)
    r = admin.post(f'/promotion/graduates/{sid}/portal-password',
                   json={'password': '123'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 400
    r = admin.post(f'/promotion/graduates/{sid}/portal-password',
                   json={'password': 'longenough'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(Student, sid).check_portal_password('longenough')


def test_alumni_analytics_and_search_and_export(app):
    # a graduate with a rich alumni profile
    sid = _grad(app, 'ALUAN1')
    with app.app_context():
        db.session.add(AlumniProfile(student_id=sid, occupation='Engineer', employer='ZENITHCORP',
                                     higher_institution='Unilag', city='Lagos', country='Nigeria',
                                     email='grad@example.com', willing_to_mentor=True))
        # a second graduate with no profile
        db.session.add(Student(student_id='ALUAN2', first_name='Bare', surname='Grad',
                               gender='Female', is_active=True, is_graduated=True,
                               graduate_status='Graduated'))
        db.session.commit()
    admin = _admin(app)
    # analytics aggregates
    j = admin.get('/promotion/alumni/analytics', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['page'] == 'alumni_analytics'
    assert j['total'] >= 2 and j['mentors'] >= 1 and j['employed'] >= 1 and j['higher_ed'] >= 1
    assert any(e['label'] == 'ZENITHCORP' for e in j['top_employers'])
    # advanced search by employer narrows the directory
    j = admin.get('/promotion/alumni?employer=ZENITHCORP', headers={'X-Requested-With': 'fetch'}).get_json()
    assert [r['student_id'] for r in j['alumni']] == ['ALUAN1']
    # mentor filter
    j = admin.get('/promotion/alumni?mentor=1', headers={'X-Requested-With': 'fetch'}).get_json()
    assert all(r['willing_to_mentor'] for r in j['alumni'])
    # CSV export (filtered) contains the matching row and the header
    r = admin.get('/promotion/alumni/export?employer=ZENITHCORP')
    assert r.status_code == 200 and r.mimetype == 'text/csv'
    text = r.get_data(as_text=True)
    assert 'Admission No' in text and 'ALUAN1' in text and 'ZENITHCORP' in text
    assert 'ALUAN2' not in text


def test_bulk_email_requires_config_or_recipients(app):
    sid = _grad(app, 'ALUEM1')
    with app.app_context():
        db.session.add(AlumniProfile(student_id=sid, email='mailme@example.com'))
        db.session.commit()
    admin = _admin(app)
    tok = _csrf(admin)
    # email is not configured in tests -> friendly error, no crash
    r = admin.post('/promotion/alumni/bulk-email',
                   json={'subject': 'Hi', 'body': 'Hello alumni'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 400 and 'not configured' in r.get_json()['error'].lower()


def test_transcript_templates_gallery_default_and_preview(app):
    from models import DocTemplatePref
    admin = _admin(app)
    tok = _csrf(admin)
    # gallery lists designs, one marked default
    j = admin.get('/promotion/doc-templates', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['page'] == 'doc_templates'
    keys = [t['key'] for t in j['templates']]
    assert 'classic' in keys and 'verbins' in keys and 'govsci' in keys
    assert sum(1 for t in j['templates'] if t['is_default']) == 1
    # preview renders a sample PDF for a design
    r = admin.get('/promotion/doc-templates/transcript/verbins/preview')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    # set a new default -> persisted
    r = admin.post('/promotion/doc-templates/transcript/default',
                   json={'template_key': 'govsci'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        assert DocTemplatePref.query.filter_by(doc_type='transcript').first().template_key == 'govsci'
    # unknown template rejected
    r = admin.post('/promotion/doc-templates/transcript/default',
                   json={'template_key': 'nope'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 400
    # unknown preview -> 404
    assert admin.get('/promotion/doc-templates/transcript/nope/preview').status_code == 404


def test_slc_designs_gallery_default_and_issue(app):
    from models import DocTemplatePref
    sid = _grad(app, 'ALUSLC')
    admin = _admin(app)
    tok = _csrf(admin)
    # SLC design gallery lists the landscape + portrait designs
    j = admin.get('/promotion/doc-templates?doc_type=slc', headers={'X-Requested-With': 'fetch'}).get_json()
    assert j['page'] == 'doc_templates' and j['doc_type'] == 'slc'
    keys = [t['key'] for t in j['templates']]
    assert 'comprehensive' in keys and 'awarded' in keys and 'vintage' in keys
    # the page offers both document types to switch between
    assert {'transcript', 'slc'} <= {dt['key'] for dt in j['doc_types']}
    # preview a landscape design
    r = admin.get('/promotion/doc-templates/slc/awarded/preview')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    # set default + issue an SLC under it
    r = admin.post('/promotion/doc-templates/slc/default', json={'template_key': 'comprehensive'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        assert DocTemplatePref.query.filter_by(doc_type='slc').first().template_key == 'comprehensive'
    r = admin.get(f'/promotion/graduates/{sid}/document/slc')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'
    # a transcript design key is not valid for slc
    r = admin.post('/promotion/doc-templates/slc/default', json={'template_key': 'pioneer'},
                   headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    assert r.status_code == 400


def test_issued_transcript_uses_selected_template(app):
    from models import DocTemplatePref
    sid = _grad(app, 'ALUTS')
    admin = _admin(app)
    tok = _csrf(admin)
    admin.post('/promotion/doc-templates/transcript/default',
               json={'template_key': 'modern'},
               headers={'X-Requested-With': 'fetch', 'X-CSRFToken': tok})
    # issuing the transcript still produces a valid PDF under the chosen design
    r = admin.get(f'/promotion/graduates/{sid}/document/transcript')
    assert r.status_code == 200 and r.data[:4] == b'%PDF'


def test_non_graduate_cannot_use_alumni_portal(app):
    with app.app_context():
        s = Student(student_id='NOTGRAD', first_name='Not', surname='Grad',
                    gender='Female', is_active=True, is_graduated=False)
        s.set_portal_password('secretpw')
        db.session.add(s); db.session.commit()
    c = app.test_client()
    tok = _portal_csrf(c)
    r = c.post('/alumni/login', data={'student_id': 'NOTGRAD', 'credential': 'secretpw',
                                      '_csrf_token': tok}, follow_redirects=True)
    assert b'Invalid admission number' in r.data
