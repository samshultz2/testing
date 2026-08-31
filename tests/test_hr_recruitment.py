"""HR Phase 8 — recruitment / ATS: vacancies, applications, interviews and the
hire → StaffMember conversion."""
import io
import re

from config import Config
from models import (db, JobVacancy, JobApplication, Interview, StaffMember,
                    Department, StaffEvent)
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


def _vacancy(app, tag, positions=1, **kw):
    with app.app_context():
        v = JobVacancy(title=f'Role {tag}', positions=positions, status='Open',
                       staff_type='Teaching', employment_type='Full-time', **kw)
        db.session.add(v); db.session.commit()
        return v.id


def test_post_vacancy_and_list(app):
    client = _admin(app)
    tok = _csrf(client)
    r = client.post('/hr/recruitment/add', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'Physics Teacher', 'positions': '2', 'staff_type': 'Teaching',
                          '_csrf_token': tok}).get_json()
    assert r['ok'] and '/hr/recruitment/' in r['redirect']
    html = client.get('/hr/recruitment').get_data(as_text=True)
    assert '"page": "recruitment"' in html and 'Physics Teacher' in html


def test_add_application_with_resume(app):
    vid = _vacancy(app, 'APP1')
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/recruitment/{vid}/applications/add',
                    content_type='multipart/form-data', headers={'X-Requested-With': 'fetch'},
                    data={'first_name': 'Ada', 'surname': 'Lovelace', 'phone': '0803',
                          'qualification': 'B.Sc', '_csrf_token': tok,
                          'file': (io.BytesIO(b'%PDF-1.4 cv'), 'cv.pdf')}).get_json()
    assert r['ok']
    with app.app_context():
        a = JobApplication.query.filter_by(vacancy_id=vid).first()
        assert a is not None and a.full_name == 'Lovelace Ada' and a.resume_id


def test_application_status_and_interview_flow(app):
    vid = _vacancy(app, 'FLOW1')
    with app.app_context():
        a = JobApplication(vacancy_id=vid, first_name='Grace', surname='Hopper', status='Applied')
        db.session.add(a); db.session.commit()
        aid = a.id
    client = _admin(app)
    tok = _csrf(client)
    # shortlist
    client.post(f'/hr/applications/{aid}/status', headers={'X-Requested-With': 'fetch'},
                data={'status': 'Shortlisted', '_csrf_token': tok})
    # schedule interview -> advances to Interview stage
    ri = client.post(f'/hr/applications/{aid}/interview', headers={'X-Requested-With': 'fetch'},
                     data={'scheduled_at': '2026-02-01T10:00', 'mode': 'Video',
                           'interviewer': 'Head', '_csrf_token': tok}).get_json()
    assert ri['ok']
    with app.app_context():
        a = db.session.get(JobApplication, aid)
        assert a.status == 'Interview'
        iv = Interview.query.filter_by(application_id=aid).first()
        assert iv is not None and iv.mode == 'Video'
        ivid = iv.id
    ro = client.post(f'/hr/interviews/{ivid}/outcome', headers={'X-Requested-With': 'fetch'},
                     data={'outcome': 'Passed', '_csrf_token': tok}).get_json()
    assert ro['ok']
    with app.app_context():
        assert db.session.get(Interview, ivid).outcome == 'Passed'


def test_hire_creates_staff_and_fills_vacancy(app):
    with app.app_context():
        dep = Department(name='Recruit Dept'); db.session.add(dep); db.session.flush()
        v = JobVacancy(title='Bursar', positions=1, status='Open', department_id=dep.id,
                       staff_type='Non-teaching', employment_type='Full-time')
        db.session.add(v); db.session.flush()
        a = JobApplication(vacancy_id=v.id, first_name='John', surname='Doe-Hire',
                           phone='0805', qualification='HND', experience_years=4, status='Offered')
        db.session.add(a); db.session.commit()
        vid, aid, did = v.id, a.id, dep.id
    client = _admin(app)
    tok = _csrf(client)
    r = client.post(f'/hr/applications/{aid}/hire', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': tok}).get_json()
    assert r['ok'] and '/hr/staff/' in r['redirect']
    with app.app_context():
        s = StaffMember.query.filter_by(surname='Doe-Hire').first()
        assert s is not None and s.designation == 'Bursar' and s.department_id == did
        assert s.staff_type == 'Non-teaching' and s.prior_experience_years == 4
        a = db.session.get(JobApplication, aid)
        assert a.status == 'Hired' and a.hired_staff_id == s.id
        assert db.session.get(JobVacancy, vid).status == 'Filled'   # single opening filled
        # employment event recorded on the new staff timeline
        assert StaffEvent.query.filter_by(staff_id=s.id, kind='employment').count() >= 1


def test_hire_is_idempotent(app):
    vid = _vacancy(app, 'IDEM', positions=2)
    with app.app_context():
        a = JobApplication(vacancy_id=vid, first_name='Twice', surname='Hired', status='Offered')
        db.session.add(a); db.session.commit()
        aid = a.id
    client = _admin(app)
    tok = _csrf(client)
    client.post(f'/hr/applications/{aid}/hire', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    again = client.post(f'/hr/applications/{aid}/hire', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    assert again.status_code == 400   # already hired
    with app.app_context():
        assert StaffMember.query.filter_by(surname='Hired').count() == 1


def test_vacancy_detail_renders(app):
    vid = _vacancy(app, 'DET1')
    client = _admin(app)
    html = client.get(f'/hr/recruitment/{vid}').get_data(as_text=True)
    assert '"page": "vacancy"' in html and '"applications"' in html
