"""Students list "Profile & records" filter: NIN, class this term, contacts,
portal password, exam numbers … each returns exactly the matching students,
and the legacy ?incomplete=1 link still works."""
import uuid
from datetime import date

from config import Config
from models import (db, Branch, Student, ParentContact, AcademicSession, Term, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        bid = Branch.get_default().id
        term = Term.query.filter_by(is_active=True).first()
        if not term:
            sess = AcademicSession(name=f'PF{tag}', is_active=True); db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='First Term', is_active=True)
            db.session.add(term); db.session.flush()
        sc = SchoolClass(name=f'PFC{tag}', level=3); arm = ClassArm(name=f'PFA{tag}', is_active=True)
        db.session.add_all([sc, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        full = Student(student_id=f'PF{tag}A', first_name='Full', surname=f'Zpf{tag}', gender='Male',
                       is_active=True, branch_id=bid, date_of_birth=date(2010, 1, 1), nin='12345678901',
                       jamb_reg_number='J1', waec_reg_number='W1', waec_subjects='English Language',
                       blood_group='O+', genotype='AA')
        full.set_portal_password('pw123456')
        bare = Student(student_id=f'PF{tag}B', first_name='Bare', surname=f'Zpf{tag}', gender='Female',
                       is_active=True, branch_id=bid, nin='  ')
        db.session.add_all([full, bare]); db.session.flush()
        db.session.add(ParentContact(student_id=full.id, phone_number='0801', email='p@x.ng', relationship='Father'))
        db.session.add(StudentEnrollment(student_id=full.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return tag


def _ids(c, tag, **params):
    q = '&'.join(f'{k}={v}' for k, v in params.items())
    j = c.get(f'/api/students?per_page=100&search=Zpf{tag}&{q}').get_json()
    return {s['student_id'] for s in j['students']}


def test_profile_filters_split_the_two_students(app):
    tag = _seed(app)
    c = _admin(app)
    A, B = f'PF{tag}A', f'PF{tag}B'
    assert _ids(c, tag) == {A, B}
    expect = {
        'has_nin': {A}, 'no_nin': {B},                 # blank-ish NIN counts as none
        'in_class': {A}, 'no_class': {B},
        'no_dob': {B}, 'no_contact': {B}, 'no_email': {B}, 'incomplete': {B},
        'has_portal': {A}, 'no_portal': {B},
        'no_jamb_reg': {B}, 'no_waec_reg': {B}, 'no_neco_reg': {A, B},
        'no_waec_subjects': {B}, 'no_jamb_subjects': {A, B}, 'no_health': {B},
        'no_photo': {A, B},
    }
    for key, want in expect.items():
        assert _ids(c, tag, profile=key) == want, key


def test_legacy_incomplete_link_still_filters(app):
    tag = _seed(app)
    c = _admin(app)
    assert _ids(c, tag, incomplete='1') == {f'PF{tag}B'}


def test_options_are_listed_for_the_dropdown(app):
    c = _admin(app)
    j = c.get('/api/students').get_json()
    groups = {g['group']: [o['value'] for o in g['options']] for g in j['filters']['profile']}
    assert groups['NIN'] == ['has_nin', 'no_nin']
    assert 'no_class' in groups['Class this term']
