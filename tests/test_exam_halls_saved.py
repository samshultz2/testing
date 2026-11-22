"""Exam halls: saving an allocation, per-hall class counts on the page and in
the exports, reopening / renaming / deleting a saved plan."""
import io
import json

from config import Config
from models import db, ExamHallPlan
from tests.conftest import login_token, auth_csrf
from tests.test_exam_halls_route import _seed


def _client(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _form(c, caa_id, seed='12345'):
    return {'_csrf_token': auth_csrf(c), 'assignments': str(caa_id),
            'hall_name': ['Main Hall', 'Hall B'], 'hall_capacity': ['100000', '50000'],
            'main_hall': '0', 'balance_gender': 'on', 'seats_per_row': '5', 'seed': seed}


def test_result_page_shows_class_counts_per_hall(app):
    _ids, caa = _seed(app, 12)
    c = _client(app)
    body = c.post('/tools/exam-halls/allocate', data=_form(c, caa)).get_data(as_text=True)
    assert 'Candidates per hall' in body and 'SSS3' in body
    assert 'name="plan_name"' in body                       # save form offered


def test_save_reopen_export_rename_delete(app):
    _ids, caa = _seed(app, 12)
    c = _client(app)
    r = c.post('/tools/exam-halls/save', data=dict(_form(c, caa), plan_name='Mock week halls'))
    assert r.status_code in (302, 303)
    with app.app_context():
        plan = ExamHallPlan.query.filter_by(name='Mock week halls').order_by(ExamHallPlan.id.desc()).first()
        assert plan and plan.hall_count == 2 and plan.total_students >= 12
        snap = json.loads(plan.snapshot)
        assert sum(h['by_class'].get('SSS3', 0) for h in snap['halls']) == snap['total_students']
        assert snap['classes'] == ['SSS3']
        pid = plan.id
    page = c.get(f'/tools/exam-halls/plans/{pid}').get_data(as_text=True)
    assert 'Mock week halls' in page and 'Saved' in page and 'FRONT OF HALL' in page
    assert 'Mock week halls' in c.get('/tools/exam-halls/').get_data(as_text=True)   # listed

    pdf = c.get(f'/tools/exam-halls/plans/{pid}/export?format=pdf')
    assert pdf.status_code == 200 and pdf.data[:4] == b'%PDF'
    import fitz
    text = ''.join(pg.get_text() for pg in fitz.open(stream=pdf.data, filetype='pdf')).replace(' ', '')
    assert 'Candidatesperhall,byclass' in text and 'Attendanceroster' in text and 'SSS3' in text

    xl = c.get(f'/tools/exam-halls/plans/{pid}/export?format=excel')
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xl.data))
    assert wb.sheetnames[0] == 'Summary' and 'Main Hall' in wb.sheetnames
    head = [cell.value for cell in wb['Summary'][4]]
    assert 'SSS3' in head and 'Total' in head

    c.post(f'/tools/exam-halls/plans/{pid}/rename', data={'_csrf_token': auth_csrf(c), 'plan_name': 'Renamed'})
    with app.app_context():
        assert db.session.get(ExamHallPlan, pid).name == 'Renamed'
    c.post(f'/tools/exam-halls/plans/{pid}/delete', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert db.session.get(ExamHallPlan, pid) is None


def test_saved_plan_matches_screen(app):
    """Same seed → the saved seats are the ones that were on screen."""
    _ids, caa = _seed(app, 10)
    c = _client(app)
    body = c.post('/tools/exam-halls/allocate', data=_form(c, caa, seed='777')).get_data(as_text=True)
    c.post('/tools/exam-halls/save', data=dict(_form(c, caa, seed='777'), plan_name='Seed check'))
    with app.app_context():
        snap = ExamHallPlan.query.filter_by(name='Seed check').first().result
    first = next(cell for row in snap['halls'][0]['seating']['rows'] for cell in row if cell)
    assert first['student']['student_id'] in body


def test_live_excel_export(app):
    _ids, caa = _seed(app, 6)
    c = _client(app)
    r = c.post('/tools/exam-halls/pdf', data=dict(_form(c, caa), format='excel'))
    assert r.status_code == 200 and r.data[:2] == b'PK'
