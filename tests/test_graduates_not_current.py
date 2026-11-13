"""Graduates keep is_active (the graduate pages use them) but have left the
school: student counts, exports and "all students" actions are about current
students only, while look-ups that may still need a graduate (fees) keep them."""
import uuid

from config import Config
from models import db, Student
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_current_query_excludes_graduates(app):
    tag = uuid.uuid4().hex[:6].upper()
    with app.app_context():
        g = Student(student_id='GQ' + tag, surname='Gradq' + tag, first_name='A', gender='Male',
                    is_active=True, is_graduated=True)
        n = Student(student_id='NQ' + tag, surname='Nowq' + tag, first_name='B', gender='Female', is_active=True)
        db.session.add_all([g, n]); db.session.commit()
        ids = {s.id for s in Student.current_query().all()}
        assert n.id in ids and g.id not in ids


def test_counts_and_exports_skip_graduates_but_fee_search_keeps_them(app):
    from utils.comms import coverage_stats
    c = _admin(app)
    before = c.get('/api/dashboard/stats').get_json()['total_students']
    cov_before = None
    with app.app_context():
        cov_before = coverage_stats()['total']
    tag = uuid.uuid4().hex[:6].upper()
    with app.app_context():
        db.session.add(Student(student_id='GX' + tag, surname='Gradx' + tag, first_name='Old', gender='Male',
                               is_active=True, is_graduated=True, graduate_status='Graduated'))
        db.session.commit()
        assert coverage_stats()['total'] == cov_before
    assert c.get('/api/dashboard/stats').get_json()['total_students'] == before
    export = c.get('/reports/export/students')
    if export.status_code == 200 and export.data[:2] == b'PK':
        import io, openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(export.data))
        text = ' '.join(str(v) for ws in wb for row in ws.iter_rows(values_only=True) for v in row if v)
        assert 'Gradx' + tag not in text
    found = c.get(f'/finance/payments/search?q=Gradx{tag}').get_json()
    assert any('Gradx' + tag in str(x) for x in found)       # may still owe fees
