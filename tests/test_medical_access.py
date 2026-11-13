"""Medical details are private: admins see them, other staff only with the
'students.medical' grant. Saving the student form without the grant leaves the
recorded medical fields untouched. The Students list offers medical filters and
a health flag to permitted users only."""
import uuid

from config import Config
from models import db, Branch, Student, User
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _user(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, full_name=username, role='staff', scope='branch',
                     branch_id=Branch.get_default().id, rank=20, manage_scope='none')
            u.set_password('secret123')
            u.set_permissions(perms)
            db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123', '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'b' * 64
    return 'b' * 64


def _seed(app):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        bid = Branch.get_default().id
        a = Student(student_id=f'MD{tag}A', first_name='Ast', surname=f'Zmd{tag}', gender='Male',
                    is_active=True, branch_id=bid, medical_conditions='Asthma, Migraine',
                    allergies='Penicillin', blood_group='O+', genotype='AA')
        b = Student(student_id=f'MD{tag}B', first_name='Sic', surname=f'Zmd{tag}', gender='Female',
                    is_active=True, branch_id=bid, genotype='SS')
        n = Student(student_id=f'MD{tag}C', first_name='Non', surname=f'Zmd{tag}', gender='Female',
                    is_active=True, branch_id=bid, medical_conditions='None', allergies='nil')
        db.session.add_all([a, b, n]); db.session.commit()
        return tag, a.id, b.id, n.id


def _names(c, tag, profile):
    d = c.get(f'/api/students?search=Zmd{tag}&profile={profile}&per_page=50').get_json()
    return sorted(s['first_name'] for s in d['students']), d


def test_admin_sees_medical_filters_and_flags(app):
    tag, a, b, n = _seed(app)
    c = _admin(app)
    names, d = _names(c, tag, 'has_medical')
    assert names == ['Ast', 'Sic']                   # "None" / "nil" don't count; SS does
    assert _names(c, tag, 'cond_asthma')[0] == ['Ast']
    assert _names(c, tag, 'has_allergy')[0] == ['Ast']
    assert _names(c, tag, 'genotype_ss')[0] == ['Sic']
    assert d['can_medical'] is True
    assert any(g['group'] == 'Medical' for g in d['filters']['profile'])
    rows = {s['first_name']: s for s in _names(c, tag, '')[1]['students']}
    assert 'Asthma' in rows['Ast']['medical'] and 'Penicillin' in rows['Ast']['medical']
    assert rows['Sic']['medical'] == 'Genotype SS'
    assert rows['Non']['medical'] is None
    prof = c.get(f'/api/students/{a}').get_json()
    assert prof['medical']['medical_conditions'] == 'Asthma, Migraine'


def test_staff_without_grant_cannot_see_or_wipe_medical(app):
    tag, a, b, n = _seed(app)
    c = _user(app, 'md_staff', {'students': 'edit'})
    prof = c.get(f'/api/students/{a}').get_json()
    assert prof['medical'] is None
    names, d = _names(c, tag, '')
    assert d['can_medical'] is False
    assert all(s['medical'] is None for s in d['students'])
    assert not any(g['group'] == 'Medical' for g in d['filters']['profile'])
    assert _names(c, tag, 'has_medical')[0] == []    # a crafted URL reveals nothing

    # Edit form never carries the medical values …
    page = c.get(f'/students/{a}/edit').get_data(as_text=True)
    assert 'Penicillin' not in page
    # … and a full save (which would send blanks) keeps them.
    token = _csrf(c)
    r = c.post(f'/students/{a}/edit', data={
        '_csrf_token': token, 'form_complete': '1', 'first_name': 'Ast', 'surname': f'Zmd{tag}',
        'gender': 'Male', 'medical_conditions': '', 'allergies': '', 'genotype': ''})
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        s = db.session.get(Student, a)
        assert s.medical_conditions == 'Asthma, Migraine'
        assert s.allergies == 'Penicillin' and s.genotype == 'AA'


def test_staff_with_grant_sees_medical(app):
    tag, a, b, n = _seed(app)
    c = _user(app, 'md_nurse', {'students': 'view', 'students.medical': 'view'})
    prof = c.get(f'/api/students/{a}').get_json()
    assert prof['medical']['allergies'] == 'Penicillin'
    assert _names(c, tag, 'has_medical')[0] == ['Ast']


def test_export_drops_medical_columns_without_grant(app):
    tag, a, b, n = _seed(app)
    import json
    q = f'/students/export?format=csv&search=Zmd{tag}&fields=' + json.dumps(['name', 'medical_conditions', 'allergies'])
    staff = _user(app, 'md_staff2', {'students': 'edit'})
    body = staff.get(q).get_data(as_text=True)
    assert 'Penicillin' not in body and 'Conditions' not in body
    body = _admin(app).get(q).get_data(as_text=True)
    assert 'Penicillin' in body
