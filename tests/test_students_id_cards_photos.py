"""Whole-class ID-card sheet + bulk passport-photo import.

The bulk ID-card route returns one printable PDF for a selection; the bulk photo
import matches images in an uploaded .zip to students by admission number and
stores them in the tenant DB, scoped to the caller's students.
"""
import io
import zipfile

from config import Config
from models import db, Student, Branch, StudentPhoto
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


def _png_bytes(color=(200, 120, 40)):
    from PIL import Image
    im = Image.new('RGB', (300, 400), color)
    buf = io.BytesIO(); im.save(buf, 'PNG'); buf.seek(0)
    return buf.getvalue()


def _mk_student(app, sid, surname):
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id=sid, first_name='T', surname=surname,
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add(s); db.session.commit()
        return s.id


def test_bulk_id_cards_returns_pdf(app):
    c = _admin(app)
    token = _csrf(c)
    a = _mk_student(app, 'IDC-001', 'ZzIdcA')
    b = _mk_student(app, 'IDC-002', 'ZzIdcB')
    r = c.post('/students/id-cards',
               data={'_csrf_token': token, 'student_ids': [a, b]})
    assert r.status_code == 200
    assert r.mimetype == 'application/pdf'
    assert r.get_data()[:4] == b'%PDF'


def test_bulk_id_cards_needs_selection(app):
    c = _admin(app)
    token = _csrf(c)
    r = c.post('/students/id-cards', data={'_csrf_token': token},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_import_photos_matches_by_admission_number(app):
    c = _admin(app)
    token = _csrf(c)
    sid = _mk_student(app, 'PIC-777', 'ZzPhotoMatch')

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w') as zf:
        zf.writestr('PIC-777.png', _png_bytes())        # matches
        zf.writestr('PIC-999.png', _png_bytes((10, 20, 30)))  # no such student
        zf.writestr('notes.txt', b'ignore me')          # not an image
    zbuf.seek(0)

    r = c.post('/students/import-photos',
               data={'_csrf_token': token,
                     'file': (zbuf, 'photos.zip')},
               content_type='multipart/form-data')
    assert r.status_code == 200
    j = r.get_json()
    assert j['matched'] == 1
    assert j['unmatched_count'] == 1
    assert 'PIC-999.png' in j['unmatched']

    with app.app_context():
        row = StudentPhoto.query.filter_by(student_id=sid).first()
        assert row is not None and row.data and row.bytes > 0
        assert row.mime == 'image/jpeg'


def test_import_photos_rejects_non_zip(app):
    c = _admin(app)
    token = _csrf(c)
    r = c.post('/students/import-photos',
               data={'_csrf_token': token,
                     'file': (io.BytesIO(b'nope'), 'photos.txt')},
               content_type='multipart/form-data')
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_import_photos_matches_ignoring_case_and_separators(app):
    c = _admin(app)
    token = _csrf(c)
    sid = _mk_student(app, 'ADM/2024/050', 'ZzPhotoNorm')
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w') as zf:
        # nested dir, different case + separators than the stored id
        zf.writestr('class/adm2024050.JPG', _png_bytes((5, 5, 5)))
    zbuf.seek(0)
    r = c.post('/students/import-photos',
               data={'_csrf_token': token, 'file': (zbuf, 'p.zip')},
               content_type='multipart/form-data')
    j = r.get_json()
    assert j['matched'] == 1
    with app.app_context():
        assert StudentPhoto.query.filter_by(student_id=sid).first() is not None
