from config import Config
from models import db, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def test_student_id_card_downloads_pdf(app):
    with app.app_context():
        s = Student(student_id='IDC001', first_name='Ada', surname='Okoro',
                    gender='Female', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    r = c.get(f'/students/{sid}/id-card')
    assert r.status_code == 200, r.status_code
    assert r.data[:4] == b'%PDF'
    assert 'application/pdf' in r.headers.get('Content-Type', '')
