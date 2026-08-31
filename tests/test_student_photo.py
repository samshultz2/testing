import base64, io
from config import Config
from models import db, Student, StudentPhoto
from tests.conftest import login_token


def _png_data_url():
    from PIL import Image
    im = Image.new('RGB', (300, 380), (40, 120, 90))
    buf = io.BytesIO(); im.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def _csrf(c):
    with c.session_transaction() as sess:
        sess['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def test_photo_upload_store_serve_and_on_id_card(app):
    with app.app_context():
        s = Student(student_id='PIC001', first_name='Ada', surname='Okoro',
                    gender='Female', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    tok = _csrf(c)
    r = c.post(f'/students/{sid}/edit',
               data={'_csrf_token': tok, 'form_complete': '1', 'first_name': 'Ada', 'surname': 'Okoro',
                     'gender': 'Female', 'photo': _png_data_url()},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200, r.status_code
    with app.app_context():
        row = StudentPhoto.query.filter_by(student_id=sid).first()
        assert row is not None and row.data and row.mime == 'image/jpeg'
    rp = c.get(f'/students/{sid}/photo')
    assert rp.status_code == 200 and rp.data[:3] == b'\xff\xd8\xff'
    import fitz
    rc = c.get(f'/students/{sid}/id-card')
    assert rc.status_code == 200 and rc.data[:4] == b'%PDF'
    d = fitz.open(stream=rc.data, filetype='pdf')
    assert d.page_count == 1
    assert d[0].get_images()
    d.close()
    r2 = c.post(f'/students/{sid}/edit',
                data={'_csrf_token': tok, 'form_complete': '1', 'first_name': 'Ada', 'surname': 'Okoro',
                      'gender': 'Female', 'photo': ''},
                headers={'X-Requested-With': 'fetch'})
    assert r2.status_code == 200
    with app.app_context():
        assert StudentPhoto.query.filter_by(student_id=sid).first() is None
