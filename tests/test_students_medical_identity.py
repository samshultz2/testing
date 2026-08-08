"""Students Phase 1 — optional medical + identity/pastoral fields.

These are additive, always-optional columns. They must round-trip through the
add/edit endpoints, surface in the view payload only when populated, and boot
onto a legacy table that predates them.
"""
from config import Config
from models import db, Student, Branch
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def test_add_student_stores_medical_and_identity(app):
    c = _admin(app)
    token = _csrf(c)
    r = c.post('/students/add', data={
        '_csrf_token': token,
        'first_name': 'Mi', 'surname': 'ZzMedIdent', 'gender': 'Male',
        'house': 'Blue', 'boarding_status': 'Boarding',
        'nin': '12345678901', 'jamb_reg_number': '2024JMB999',
        'jamb_profile_code': 'PC-42', 'waec_epin': 'WAEC-EPIN-7788',
        'blood_group': 'O+', 'genotype': 'AS',
        'allergies': 'Peanuts', 'medical_conditions': 'Asthma',
        'disabilities': 'None', 'medications': 'Inhaler',
        'medical_notes': 'Keep inhaler in bag',
        'emergency_medical': 'Call Dr. Ada 080000',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        s = Student.query.filter_by(surname='ZzMedIdent').first()
        assert s is not None
        assert s.house == 'Blue' and s.boarding_status == 'Boarding'
        assert s.nin == '12345678901'
        assert s.jamb_reg_number == '2024JMB999'
        assert s.jamb_profile_code == 'PC-42'
        assert s.waec_epin == 'WAEC-EPIN-7788'
        assert s.blood_group == 'O+' and s.genotype == 'AS'
        assert s.allergies == 'Peanuts'
        assert s.medical_conditions == 'Asthma'
        assert s.medications == 'Inhaler'
        assert s.medical_notes == 'Keep inhaler in bag'
        assert s.emergency_medical == 'Call Dr. Ada 080000'
        assert s.has_medical and s.has_identity


def test_view_payload_hides_sections_until_populated(app):
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        bare = Student(student_id='ZZ_BARE_1', first_name='B', surname='ZzBare',
                       gender='Female', is_active=True, branch_id=bid)
        db.session.add(bare); db.session.commit()
        sid = bare.id

    payload = c.get(f'/api/students/{sid}').get_json()
    assert payload['identity'] is None
    assert payload['medical'] is None

    with app.app_context():
        s = db.session.get(Student, sid)
        s.nin = '99999999999'
        s.blood_group = 'A+'
        db.session.commit()

    payload = c.get(f'/api/students/{sid}').get_json()
    assert payload['identity']['nin'] == '99999999999'
    assert payload['medical']['blood_group'] == 'A+'


def test_edit_partial_post_does_not_blank_medical(app):
    """A partial POST (no form_complete flag) only touches submitted fields."""
    c = _admin(app)
    token = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_PARTIAL_1', first_name='P', surname='ZzPartial',
                    gender='Male', is_active=True, branch_id=bid,
                    blood_group='B+', genotype='SS')
        db.session.add(s); db.session.commit()
        sid = s.id
    # Partial POST that sets only the NIN — blood_group must survive.
    c.post(f'/students/{sid}/edit', data={'_csrf_token': token,
                                          'nin': '11122233344'})
    with app.app_context():
        s = db.session.get(Student, sid)
        assert s.nin == '11122233344'
        assert s.blood_group == 'B+' and s.genotype == 'SS'


def test_complete_edit_clears_omitted_medical(app):
    """A complete edit (form_complete=1) blanks fields absent from the POST."""
    c = _admin(app)
    token = _csrf(c)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_CLEAR_1', first_name='C', surname='ZzClear',
                    gender='Male', is_active=True, branch_id=bid,
                    allergies='Dust', house='Red')
        db.session.add(s); db.session.commit()
        sid = s.id
    c.post(f'/students/{sid}/edit', data={
        '_csrf_token': token, 'form_complete': '1',
        'first_name': 'C', 'surname': 'ZzClear', 'gender': 'Male',
        # allergies + house intentionally omitted
    })
    with app.app_context():
        s = db.session.get(Student, sid)
        assert s.allergies is None and s.house is None


def test_legacy_table_bootstrap(app):
    """ensure_tables adds the new columns to a table created without them."""
    from sqlalchemy import inspect, text
    from utils.finance_ledger import ensure_tables
    with app.app_context():
        insp = inspect(db.engine)
        cols = {c['name'] for c in insp.get_columns('students')}
        for col in ('house', 'boarding_status', 'nin', 'jamb_reg_number',
                    'jamb_profile_code', 'blood_group', 'genotype', 'allergies',
                    'medical_conditions', 'disabilities', 'medications',
                    'medical_notes', 'emergency_medical'):
            assert col in cols, f'{col} missing from students table'
