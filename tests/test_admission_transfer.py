"""Admitting an applicant carries their whole application into the student record."""
import base64
import io

from models import db, Applicant, Student, StudentPhoto, ParentContact
from tests.test_admissions import _admin, _ptoken


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (60, 80), (30, 120, 90)).save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _apply(c, tok, **extra):
    data = {'first_name': 'Tobenna', 'middle_name': 'Chukwuemeka', 'surname': 'Transfer', 'gender': 'Male',
            'date_of_birth': '2012-04-09', 'address': '12 Unity Road, Benin', 'blood_group': 'O+', 'genotype': 'AA',
            'parent_name': 'Mrs. Ada Transfer', 'relationship': 'Mother', 'parent_phone': '08031234567',
            'parent_email': 'ada@example.com', 'emergency_name': 'Uncle Obi', 'emergency_phone': '08039876543',
            'emergency_relationship': 'Uncle', 'previous_school': 'Hilltop Primary', 'state_of_origin': 'Anambra',
            'lga': 'Onitsha North', 'photo_data': _png(), 'status': 'Accepted', '_csrf_token': tok}
    data.update(extra)
    r = c.post('/admissions/applicants/add', headers={'X-Requested-With': 'fetch'}, data=data)
    assert r.get_json()['ok']
    return Applicant.query.filter_by(surname=data['surname']).order_by(Applicant.id.desc()).first().id


def test_admit_copies_everything(app):
    c = _admin(app); tok = _ptoken(c)
    with app.app_context():
        aid = _apply(c, tok)
    r = c.post(f'/admissions/applicants/{aid}/convert', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    assert r.get_json()['ok']
    with app.app_context():
        st = db.session.get(Applicant, aid).admitted_student
        assert (st.first_name, st.middle_name, st.surname) == ('Tobenna', 'Chukwuemeka', 'Transfer')
        assert st.home_address == '12 Unity Road, Benin' and st.blood_group == 'O+' and st.genotype == 'AA'
        assert st.date_of_birth.isoformat() == '2012-04-09'
        assert StudentPhoto.query.filter_by(student_id=st.id).first() is not None
        contacts = {c_.phone_number: c_ for c_ in ParentContact.query.filter_by(student_id=st.id).all()}
        assert contacts['08031234567'].email == 'ada@example.com' and contacts['08031234567'].is_primary
        assert contacts['08031234567'].name == 'Mrs. Ada Transfer'
        assert '08039876543' in contacts and contacts['08039876543'].relationship == 'Uncle'
        sid = st.id
    # Extra application details show on the student profile.
    d = c.get(f'/api/students/{sid}').get_json()
    rows = dict(map(tuple, d['admission']['rows']))
    assert rows['Previous school'] == 'Hilltop Primary' and rows['L.G.A. of origin'] == 'Onitsha North'


def test_admitted_label_requires_admit_and_copy_backfills(app):
    c = _admin(app); tok = _ptoken(c)
    with app.app_context():
        aid = _apply(c, tok, surname='Backfill')
    r = c.post(f'/admissions/applicants/{aid}/status', headers={'X-Requested-With': 'fetch'},
               data={'status': 'Admitted', '_csrf_token': tok})
    assert not r.get_json()['ok']
    # An older admission that only got the basics: copying fills the gaps, never overwrites.
    with app.app_context():
        a = db.session.get(Applicant, aid)
        st = Student(student_id='BKF0001', first_name='Tobenna', surname='Backfill', gender='Male',
                     home_address='Typed later', is_active=True)
        db.session.add(st); db.session.flush()
        a.admitted_student_id = st.id; a.status = 'Admitted'
        db.session.commit()
        sid = st.id
    r = c.post(f'/admissions/applicants/{aid}/copy-to-student', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok})
    j = r.get_json()
    assert j['ok'] and 'passport photo' in j['message'] and 'parent contact' in j['message']
    with app.app_context():
        st = db.session.get(Student, sid)
        assert st.home_address == 'Typed later'           # not overwritten
        assert st.middle_name == 'Chukwuemeka' and st.genotype == 'AA'
        assert ParentContact.query.filter_by(student_id=sid).count() == 2
    again = c.post(f'/admissions/applicants/{aid}/copy-to-student', headers={'X-Requested-With': 'fetch'}, data={'_csrf_token': tok}).get_json()
    assert 'already has everything' in again['message']


def test_link_application_to_hand_made_student(app):
    from datetime import date
    c = _admin(app); tok = _ptoken(c)
    with app.app_context():
        aid = _apply(c, tok, surname='Linkme', first_name='Chiamaka', gender='Female')
        # Admitted in real life, profile typed by hand: names + DOB only.
        st = Student(student_id='LNK0001', first_name='Chiamaka', surname='Linkme', gender='Female',
                     date_of_birth=date(2012, 4, 9), is_active=True)
        decoy = Student(student_id='LNK0002', first_name='Other', surname='Linkme', gender='Male', is_active=True)
        db.session.add_all([st, decoy]); db.session.commit()
        sid, did = st.id, decoy.id
    d = c.get(f'/admissions/applicants/{aid}', headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    assert d['matches'] and d['matches'][0]['id'] == sid and d['matches'][0]['strong']
    assert did not in [m['id'] for m in d['matches']]          # wrong gender is not suggested
    dash = c.get('/admissions/', headers={'X-Requested-With': 'fetch'}).get_json()
    dash = dash.get('data', dash)
    assert dash['action']['linkable'] >= 1
    r = c.post(f'/admissions/applicants/{aid}/link', headers={'X-Requested-With': 'fetch'},
               data={'student_id': sid, '_csrf_token': tok}).get_json()
    assert r['ok'] and 'passport photo' in r['message']
    with app.app_context():
        a = db.session.get(Applicant, aid)
        st = db.session.get(Student, sid)
        assert a.admitted_student_id == sid and a.status == 'Admitted'
        assert st.middle_name == 'Chukwuemeka' and st.home_address == '12 Unity Road, Benin'
        assert StudentPhoto.query.filter_by(student_id=sid).first() is not None
        assert ParentContact.query.filter_by(student_id=sid).count() == 2
    # The same student can't be claimed by a second application.
    with app.app_context():
        aid2 = _apply(c, tok, surname='Linkme2')
    r = c.post(f'/admissions/applicants/{aid2}/link', headers={'X-Requested-With': 'fetch'},
               data={'student_id': sid, '_csrf_token': tok}).get_json()
    assert not r['ok'] and 'already linked' in r['error']
