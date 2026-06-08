"""Cross-branch overview + per-branch identity on documents."""
import re

from config import Config
from models import db, Branch, Student, User, Product
from tests.conftest import login_token


def _legacy_admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def _ptoken(c):
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                  c.get('/students').get_data(as_text=True))
    return m.group(1) if m else None


def test_overview_central_only(app):
    with app.app_context():
        if not User.query.filter_by(username='ovbranch').first():
            u = User(username='ovbranch', role='staff', scope='branch',
                     branch_id=Branch.get_default().id)
            u.set_password('secret123'); u.set_modules(['students']); db.session.add(u)
            db.session.commit()
    # central sees it
    assert _legacy_admin(app).get('/branch-overview').status_code == 200
    # branch user is redirected away
    c = app.test_client()
    c.post('/login', data={'username': 'ovbranch', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    r = c.get('/branch-overview', follow_redirects=False)
    assert r.status_code in (302, 303)


def test_overview_shows_branch_metrics(app):
    with app.app_context():
        b = Branch.query.filter_by(name='OvB').first() or Branch(name='OvB', is_active=True)
        if b.id is None:
            db.session.add(b); db.session.commit()
        if not Student.query.filter_by(student_id='OVB1').first():
            db.session.add(Student(student_id='OVB1', first_name='O', surname='V',
                                   gender='Male', is_active=True, branch_id=b.id))
            db.session.commit()
    html = _legacy_admin(app).get('/branch-overview').get_data(as_text=True)
    assert 'OvB' in html
    assert 'Branch Overview' in html


def test_sales_receipt_shows_branch(app):
    c = _legacy_admin(app)
    tok = _ptoken(c)
    c.post('/sales/products/add',
           data={'name': 'Crest Badge', 'unit_price': 500, 'stock_qty': 10,
                 '_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        pid = Product.query.filter_by(name='Crest Badge').first().id
    r = c.post('/sales/new', data={'product_id': pid, 'quantity': 1,
                                   '_csrf_token': tok}, follow_redirects=True)
    # default branch name appears on the receipt header
    with app.app_context():
        bname = Branch.get_default().name
    assert bname in r.get_data(as_text=True)
