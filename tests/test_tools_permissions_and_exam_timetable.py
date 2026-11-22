"""Tools menu: each tool is granted on its own (Exam halls, Study groups,
WAEC/NECO timetable), and the WAEC / NECO exam timetable designer itself."""
import io

from models import db, Student, ExamTimetable, ExamTimetablePaper
from tests.conftest import auth_csrf, enroll_sss3
from tests.test_subsections import _make, _login, _ptoken


def _admin(app):
    from config import Config
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_each_tool_is_granted_separately(app):
    _make(app, 'tool_halls_only', {'tools.exam_halls': 'edit'})
    c = _login(app, 'tool_halls_only')
    assert c.get('/tools/exam-halls/').status_code == 200
    assert c.get('/tools/study-groups/').status_code in (302, 303, 403)
    assert c.get('/tools/exam-timetable/').status_code in (302, 303, 403)
    nav = c.get('/tools/exam-halls/').get_data(as_text=True)
    assert 'Exam Hall Allocator' in nav and 'WAEC / NECO Timetable' not in nav


def test_view_only_tool_cannot_create(app):
    _make(app, 'tool_tt_view', {'tools.exam_timetable': 'view'})
    c = _login(app, 'tool_tt_view')
    page = c.get('/tools/exam-timetable/')
    assert page.status_code == 200 and 'New timetable' not in page.get_data(as_text=True)
    with app.app_context():
        before = ExamTimetable.query.count()
    c.post('/tools/exam-timetable/create', data={'_csrf_token': _ptoken(c), 'board': 'waec', 'year': '2027'})
    with app.app_context():
        assert ExamTimetable.query.count() == before


def test_whole_tools_module_grants_every_tool(app):
    _make(app, 'tool_all', {'tools': 'edit'})
    c = _login(app, 'tool_all')
    for url in ('/tools/exam-halls/', '/tools/study-groups/', '/tools/exam-timetable/'):
        assert c.get(url).status_code == 200, url


def test_teachers_keep_study_groups_by_default(app):
    from models import User
    with app.app_context():
        if not User.query.filter_by(username='tool_teacher').first():
            u = User(username='tool_teacher', role='teacher', scope='central', full_name='T')
            u.set_password('secret123'); db.session.add(u); db.session.commit()
    c = _login(app, 'tool_teacher')
    assert c.get('/tools/study-groups/').status_code == 200
    assert c.get('/tools/exam-halls/').status_code in (302, 303, 403)


def _cand(app, name, subjects):
    from models import Branch
    with app.app_context():
        s = Student(student_id=name, first_name=name, surname='Cand', gender='Female', is_active=True,
                    branch_id=Branch.get_default().id, waec_subjects=subjects)
        db.session.add(s); db.session.commit(); sid = s.id
    enroll_sss3(app, sid)
    return sid


def test_exam_timetable_flow(app):
    _cand(app, 'XTA1', 'English Language,Mathematics,Physics')
    _cand(app, 'XTA2', 'English Language,Mathematics,Biology')
    c = _admin(app)
    r = c.post('/tools/exam-timetable/create', data={'_csrf_token': auth_csrf(c), 'board': 'waec', 'year': '2031'})
    assert r.status_code in (302, 303)
    with app.app_context():
        tt = ExamTimetable.query.filter_by(year=2031).order_by(ExamTimetable.id.desc()).first()
        tid = tt.id
        assert tt.title == 'WAEC SSCE 2031 timetable'
    add = lambda **kw: c.post(f'/tools/exam-timetable/{tid}/papers', data=dict(_csrf_token=auth_csrf(c), **kw))
    add(exam_date='2031-05-05', start_time='09:00', end_time='11:00', subject='Mathematics', paper='Paper 2 (Essay)',
        kind='essay', venue='Main Hall')
    add(exam_date='2031-05-05', start_time='10:00', end_time='12:00', subject='Physics', paper='Paper 1 (Objective)')
    add(exam_date='2031-05-06', start_time='14:00', end_time='13:00', subject='Biology')   # ends before start
    with app.app_context():
        assert ExamTimetablePaper.query.filter_by(timetable_id=tid).count() == 2
    page = c.get(f'/tools/exam-timetable/{tid}').get_data(as_text=True)
    assert 'Clash' in page and 'Mathematics' in page and 'Physics' in page
    assert 'Biology' in page and 'Subjects with no paper yet' in page          # Biology still needs a paper

    pdf = c.get(f'/tools/exam-timetable/{tid}/export?format=pdf')
    assert pdf.status_code == 200 and pdf.data[:4] == b'%PDF'
    import fitz
    text = ''.join(p.get_text() for p in fitz.open(stream=pdf.data, filetype='pdf')).replace(' ', '')
    assert 'Mathematics' in text and 'Clashestoresolve' in text
    per = c.get(f'/tools/exam-timetable/{tid}/export?format=candidates')
    text = ''.join(p.get_text() for p in fitz.open(stream=per.data, filetype='pdf'))
    assert 'XTA1' in text and 'XTA2' in text
    xl = c.get(f'/tools/exam-timetable/{tid}/export?format=excel')
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xl.data))
    assert wb.sheetnames == ['Timetable', 'By candidate']

    with app.app_context():
        pid = ExamTimetablePaper.query.filter_by(timetable_id=tid, subject='Physics').first().id
    c.post(f'/tools/exam-timetable/{tid}/papers/{pid}', data={
        '_csrf_token': auth_csrf(c), 'exam_date': '2031-05-05', 'start_time': '14:00', 'end_time': '16:00',
        'subject': 'Physics'})
    assert 'No candidate has two papers at once' in c.get(f'/tools/exam-timetable/{tid}').get_data(as_text=True)
    c.post(f'/tools/exam-timetable/{tid}/delete', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert db.session.get(ExamTimetable, tid) is None
