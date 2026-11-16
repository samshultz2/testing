"""A student with no contacts is offered the contacts of same-surname pupils
(likely siblings): one tap copies them, "Not siblings" stops the suggestion."""
import uuid

from models import db, Branch, ParentContact, Student
from tests.test_medical_access import _admin, _csrf, _user


def _seed(app, with_contacts=True, other_branch=False):
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        bid = Branch.get_default().id
        if other_branch:
            b2 = Branch(name=f'ZzSibBranch{tag}', code=None); db.session.add(b2); db.session.flush()
        new = Student(student_id=f'SB{tag}N', first_name='Ada', surname=f'Zsib{tag}', gender='Female',
                      is_active=True, branch_id=bid, home_address='12 Palm Street')
        sib = Student(student_id=f'SB{tag}S', first_name='Chidi', surname=f'ZSIB{tag}', gender='Male',
                      is_active=True, branch_id=(b2.id if other_branch else bid), home_address='12 Palm Street')
        other = Student(student_id=f'SB{tag}O', first_name='Emeka', surname=f'Zother{tag}', gender='Male',
                        is_active=True, branch_id=bid)
        db.session.add_all([new, sib, other]); db.session.flush()
        if with_contacts:
            db.session.add_all([
                ParentContact(student_id=sib.id, phone_number='08031112222', name='Mrs Zsib',
                              relationship='Mother', is_primary=True),
                ParentContact(student_id=sib.id, phone_number='08033334444', name='Mr Zsib',
                              relationship='Father'),
                ParentContact(student_id=other.id, phone_number='08099990000', name='Mr Other'),
            ])
        db.session.commit()
        return new.id, sib.id, other.id


def _payload(c, sid):
    return c.get(f'/api/students/{sid}').get_json()


def test_same_surname_sibling_contacts_are_suggested(app):
    new, sib, other = _seed(app)
    d = _payload(_admin(app), new)
    sugg = d['sibling_contacts']
    assert [s['id'] for s in sugg] == [sib]           # case-insensitive surname; not the other family
    assert sugg[0]['same_address'] is True
    assert [c['phone_number'] for c in sugg[0]['contacts']] == ['08031112222', '08033334444']


def test_no_suggestion_when_student_already_has_contacts_or_none_exist(app):
    new, sib, _ = _seed(app)
    c = _admin(app)
    assert _payload(c, sib)['sibling_contacts'] == []  # has contacts already
    new2, _, _ = _seed(app, with_contacts=False)
    assert _payload(c, new2)['sibling_contacts'] == []  # nobody to copy from


def test_other_branch_pupils_are_not_suggested(app):
    new, _, _ = _seed(app, other_branch=True)
    assert _payload(_admin(app), new)['sibling_contacts'] == []


def test_copy_contacts_adds_them_once(app):
    new, sib, _ = _seed(app)
    c = _admin(app)
    tok = _csrf(c)
    r = c.post(f'/students/{new}/contacts/copy-from/{sib}', data={'_csrf_token': tok})
    assert r.status_code == 200 and r.get_json() == {'ok': True, 'added': 2}
    r2 = c.post(f'/students/{new}/contacts/copy-from/{sib}', data={'_csrf_token': tok})
    assert r2.get_json()['added'] == 0                 # no duplicates on a second tap
    with app.app_context():
        rows = ParentContact.query.filter_by(student_id=new).order_by(ParentContact.id).all()
        assert [(x.phone_number, x.relationship, x.is_primary) for x in rows] == [
            ('08031112222', 'Mother', True), ('08033334444', 'Father', False)]
    d = _payload(c, new)
    assert len(d['contacts']) == 2 and d['sibling_contacts'] == []


def test_not_siblings_stops_the_suggestion(app):
    new, sib, _ = _seed(app)
    c = _admin(app)
    r = c.post(f'/students/{new}/not-sibling/{sib}', data={'_csrf_token': _csrf(c)})
    assert r.status_code == 200 and r.get_json()['ok']
    assert _payload(c, new)['sibling_contacts'] == []
    with app.app_context():
        assert ParentContact.query.filter_by(student_id=new).count() == 0


def test_view_only_staff_cannot_copy(app):
    new, sib, _ = _seed(app)
    c = _user(app, 'zz_sib_viewer', {'students': 'view'})
    r = c.post(f'/students/{new}/contacts/copy-from/{sib}', data={'_csrf_token': _csrf(c)})
    assert r.status_code in (302, 403)
    with app.app_context():
        assert ParentContact.query.filter_by(student_id=new).count() == 0


def test_two_siblings_with_the_same_numbers_are_suggested_once(app):
    new, sib, _ = _seed(app)
    c = _admin(app)
    with app.app_context():
        s = db.session.get(Student, sib)
        twin = Student(student_id=s.student_id + 'T', first_name='Twin', surname=s.surname,
                       gender='Male', is_active=True, branch_id=s.branch_id)
        db.session.add(twin); db.session.flush()
        for pc in ParentContact.query.filter_by(student_id=sib).all():
            db.session.add(ParentContact(student_id=twin.id, phone_number=pc.phone_number, name=pc.name))
        db.session.commit()
    assert len(_payload(c, new)['sibling_contacts']) == 1
