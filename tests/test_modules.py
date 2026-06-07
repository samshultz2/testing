"""Tests for the modules added in this branch: finance, comms, HR, admissions,
library, events, CBT and the import parsers."""
import datetime as dt

from tests.conftest import page_token


# ---------------------------------------------------------------------------
# Pure parsers (no DB)
# ---------------------------------------------------------------------------

def test_calendar_parse_dates():
    from utils import calendar_import as ci
    assert ci.parse_dates('28/04/2025') == (dt.date(2025, 4, 28), None)
    s, e = ci.parse_dates('02 - 06/06/2025')
    assert s == dt.date(2025, 6, 2) and e == dt.date(2025, 6, 6)
    s, e = ci.parse_dates('26 – 30/05/26')           # 2-digit year
    assert s == dt.date(2026, 5, 26) and e == dt.date(2026, 5, 30)
    assert ci.parse_dates('no date here') == (None, None)


def test_calendar_category_inference():
    from utils import calendar_import as ci
    assert ci._infer_category("Workers' Day (Public Holiday)") == 'Holiday'
    assert ci._infer_category('Resumption Examination') == 'Exam'
    assert ci._infer_category('Spelling Bee Competition') == 'Activity'
    # 'Holiday Assignment' must NOT be tagged Holiday
    assert ci._infer_category('Submission of Holiday Assignment') == 'General'


def test_cbt_import_parser():
    from utils import cbt_import
    csv = (b'Question,A,B,C,D,Correct,Marks,Topic\n'
           b'What is 2+2?,3,4,5,6,B,1,Math\n'
           b'Capital?,Lagos,Kano,Abuja,Jos,Abuja,2,Geo\n')   # 'Correct' as text
    rows = cbt_import.parse_csv(csv)
    assert len(rows) == 2
    assert rows[0]['correct_option'] == 'B'
    assert rows[1]['correct_option'] == 'C'      # matched the answer text
    assert rows[1]['marks'] == 2


def test_phone_normalisation():
    from utils.comms import normalise_phone
    assert normalise_phone('08031234567') == '2348031234567'
    assert normalise_phone('+2348031234567') == '2348031234567'


# ---------------------------------------------------------------------------
# Logic with the DB
# ---------------------------------------------------------------------------

def _seed_term(app):
    from models import db, AcademicSession, Term
    with app.app_context():
        s = AcademicSession(name='9999/0000', is_active=False)
        db.session.add(s)
        db.session.flush()
        t = Term(session_id=s.id, term_number=1, name='Mod Term')
        db.session.add(t)
        db.session.commit()
        return t.id


def test_cbt_scaling(app):
    from models import db, CBTExam, CBTQuestion
    with app.app_context():
        e = CBTExam(title='Scale', exam_date=dt.date.today(), max_score=30, access_password='x')
        db.session.add(e)
        db.session.flush()
        for i in range(4):
            db.session.add(CBTQuestion(exam_id=e.id, question_text=f'q{i}',
                                       correct_option='A', marks=1, order=i))
        db.session.commit()
        assert e.raw_total == 4
        assert e.total_marks == 30
        assert e.scale(4) == 30.0     # all correct -> full scaled
        assert e.scale(2) == 15.0     # half


def test_hr_lateness(app):
    from utils import hr
    with app.app_context():
        s = {'late_time': '07:30', 'late_rate': 10.0, 'absence_deduction': 5000.0}
        assert hr.compute_attendance('Present', '07:45', s) == ('Late', 15, 150.0)
        assert hr.compute_attendance('Late', None, s) == ('Late', 0, 0)
        assert hr.compute_attendance('Absent', None, s) == ('Absent', 0, 5000.0)
        assert hr.compute_attendance('Present', '07:20', s) == ('Present', 0, 0)


def test_student_id_generation_robust(app):
    from models import db, Student
    with app.app_context():
        db.session.add(Student(student_id='LEGACY-XYZ', first_name='A', surname='B', gender='Male'))
        db.session.commit()
        # must not crash on the non-STU id
        assert Student.generate_student_id().startswith('STU')


# ---------------------------------------------------------------------------
# Route smoke tests (authenticated)
# ---------------------------------------------------------------------------

def test_module_dashboards_load(auth_client):
    for path in ['/finance/', '/finance/items', '/finance/collections',
                 '/communication/', '/communication/compose', '/communication/templates',
                 '/hr/', '/hr/staff', '/hr/payroll', '/hr/attendance',
                 '/admissions/', '/admissions/applicants',
                 '/library/', '/library/books', '/library/issue',
                 '/events/', '/events/list', '/events/import',
                 '/cbt/', '/cbt/bank', '/cbt/settings', '/cbt/lab-setup',
                 '/search', '/audit']:
        assert auth_client.get(path).status_code == 200, path


def test_exam_portal_login_page(client):
    assert client.get('/exam/login').status_code == 200


def test_global_search_finds_student(auth_client, app):
    from models import db, Student
    with app.app_context():
        db.session.add(Student(student_id='STU09111', first_name='Zenith', surname='Searcher', gender='Male'))
        db.session.commit()
    r = auth_client.get('/search?q=Zenith')
    assert r.status_code == 200 and b'Zenith' in r.data


def test_csrf_on_new_module_post(auth_client):
    # finance fee item add is a state-changing POST -> needs CSRF
    assert auth_client.post('/finance/items/add', data={'name': 'X'}).status_code == 400
    token = page_token(auth_client)
    r = auth_client.post('/finance/items/add', data={'name': 'Test Levy'},
                         headers={'X-CSRFToken': token})
    assert r.status_code in (302, 303)
