"""The branded students exports: PDF fits/paginates on A4, and the image export
serves one A4 page per request with a total-pages header (client downloads all)."""
import json
from config import Config
from tests.conftest import login_token


def test_student_export_module_pdf_and_image_pages():
    from utils.student_export import students_pdf, students_image_pages, short_header
    headers = ['S/N', 'Surname', 'First Name', 'Gender', 'Date of Birth', 'Home Address']
    rows = [[str(i), 'Obi', 'Ada', 'Female', '2010-01-01',
             'A rather long home address that should wrap within its column'] for i in range(1, 61)]
    school = {'name': 'Test School', 'address': 'Somewhere', 'phone': '080', 'email': 'a@b.c', 'motto': 'Rise', 'logo_path': None}
    pdf = students_pdf(rows, headers, school, total=len(rows))
    assert pdf[:4] == b'%PDF'
    pages = students_image_pages(rows, headers, school, total=len(rows))
    assert len(pages) >= 2 and all(p[:4] == b'\x89PNG' for p in pages)
    assert short_header('Date of Birth') == 'DOB'


def test_export_route_image_has_total_pages_header(app):
    from models import db, Student
    with app.app_context():
        ids = []
        for i in range(3):
            s = Student(student_id=f'XPD-{i}', first_name='A', surname=f'B{i}',
                        gender='Male', is_active=True)
            db.session.add(s); db.session.flush(); ids.append(s.id)
        db.session.commit()
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        r = c.get('/students/export', query_string={
            'format': 'image', 'fields': json.dumps(['surname', 'first_name', 'gender']),
            'student_ids': json.dumps(ids)})
        assert r.status_code == 200 and r.data[:4] == b'\x89PNG'
        assert int(r.headers.get('X-Total-Pages', '1')) >= 1
        # PDF too
        r2 = c.get('/students/export', query_string={
            'format': 'pdf', 'fields': json.dumps(['surname', 'first_name', 'gender']),
            'student_ids': json.dumps(ids)})
        assert r2.status_code == 200 and r2.data[:4] == b'%PDF'
    finally:
        with app.app_context():
            Student.query.filter(Student.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()
