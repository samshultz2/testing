"""Parent portal: one parent (shared phone) can switch between their children."""
import re
from models import db, Student, ParentContact, Branch


def _seed(app):
    with app.app_context():
        if Student.query.filter_by(student_id='SIBA').first():
            a = Student.query.filter_by(student_id='SIBA').first()
            b = Student.query.filter_by(student_id='SIBB').first()
            x = Student.query.filter_by(student_id='OUTX').first()
            return a.id, b.id, x.id
        bid = Branch.get_default().id
        a = Student(student_id='SIBA', first_name='Ada', surname='Family', gender='Female', is_active=True, branch_id=bid)
        b = Student(student_id='SIBB', first_name='Ben', surname='Family', gender='Male', is_active=True, branch_id=bid)
        x = Student(student_id='OUTX', first_name='Out', surname='Sider', gender='Male', is_active=True, branch_id=bid)
        for s in (a, b, x):
            s.set_portal_password('pw12345')
        db.session.add_all([a, b, x]); db.session.flush()
        db.session.add(ParentContact(student_id=a.id, phone_number='08099990000', name='Mum', is_primary=True))
        db.session.add(ParentContact(student_id=b.id, phone_number='08099990000', name='Mum', is_primary=True))
        db.session.add(ParentContact(student_id=x.id, phone_number='08000001111', name='Other', is_primary=True))
        db.session.commit()
        return a.id, b.id, x.id


def _login(app, sid):
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/parent/login').get_data(as_text=True)).group(1)
    c.post('/parent/login', data={'student_id': sid, 'password': 'pw12345', '_csrf_token': tok})
    return c


def test_switch_between_siblings(app):
    a, b, x = _seed(app)
    c = _login(app, 'SIBA')
    html = c.get('/parent/').get_data(as_text=True)
    assert 'SIBA' in html                       # viewing Ada
    assert f'/parent/child/{b}' in html         # switcher links to sibling Ben
    c.get(f'/parent/child/{b}')
    assert 'SIBB' in c.get('/parent/').get_data(as_text=True)


def test_cannot_switch_to_unrelated(app):
    a, b, x = _seed(app)
    c = _login(app, 'SIBA')
    c.get(f'/parent/child/{x}', follow_redirects=True)
    html = c.get('/parent/').get_data(as_text=True)
    assert 'SIBA' in html and 'OUTX' not in html    # still on Ada; unrelated rejected
