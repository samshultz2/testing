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
    add(exam_date='2031-05-07', start_time='09:00', end_time='10:00', subject='__other', subject_other='Data Processing',
        paper='__other', paper_other='Paper 4 (Project)')
    with app.app_context():
        assert ExamTimetablePaper.query.filter_by(timetable_id=tid).count() == 3
        other = ExamTimetablePaper.query.filter_by(timetable_id=tid, subject='Data Processing').one()
        assert other.paper == 'Paper 4 (Project)'
    page = c.get(f'/tools/exam-timetable/{tid}').get_data(as_text=True)
    assert 'Clash' in page and 'Mathematics' in page and 'Physics' in page
    assert '<select class="xe-in" name="subject"' in page and '<select class="xe-in" name="paper"' in page
    assert '<option selected>Data Processing</option>' in page        # custom subject stays selected when editing
    assert 'Biology' in page and 'Subjects with no paper yet' in page          # Biology still needs a paper

    page = c.get(f'/tools/exam-timetable/{tid}/print?theme=gazette').get_data(as_text=True)
    assert 'data-theme="gazette"' in page and 'Download PDF' in page and 'School logo' in page
    for key in ('timeline', 'tickets', 'swiss', 'notebook', 'board', 'quiet', 'inline', 'print', 'mono', 'plain'):
        assert 'data-theme="%s"' % key in page                       # every designer theme offered
    assert 'Mathematics' in page and 'Paper 2 (Essay)' in page

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


def test_duration_wording_and_common_sessions(app):
    from utils.exam_timetable import fmt_dur
    assert [fmt_dur(m) for m in (45, 60, 90, 120, 165, 180)] == \
        ['45mins', '1hr', '1hr 30mins', '2hrs', '2hrs 45mins', '3hrs']
    c = _admin(app)
    for board, first in (('waec', '9:30am–12:30pm'), ('neco', '10am–1pm')):
        c.post('/tools/exam-timetable/create', data={'_csrf_token': auth_csrf(c), 'board': board, 'year': '2040'})
        with app.app_context():
            tid = ExamTimetable.query.filter_by(board=board, year=2040).order_by(ExamTimetable.id.desc()).first().id
        page = c.get(f'/tools/exam-timetable/{tid}').get_data(as_text=True)
        assert 'Common %s sessions' % board.upper() in page and first in page
        assert '<option value="90" >1hr 30mins</option>' in page or '>1hr 30mins</option>' in page


def test_exam_window_board_papers_and_crud(app):
    c = _admin(app)
    c.post('/tools/exam-timetable/create', data={'_csrf_token': auth_csrf(c), 'board': 'neco', 'year': '',
                                                 'start_date': '2041-06-16', 'end_date': '2041-07-25'})
    with app.app_context():
        tt = ExamTimetable.query.filter_by(board='neco').order_by(ExamTimetable.id.desc()).first()
        tid = tt.id
        assert (tt.start_date.isoformat(), tt.end_date.isoformat(), tt.year) == ('2041-06-16', '2041-07-25', 2041)
    page = c.get(f'/tools/exam-timetable/{tid}').get_data(as_text=True)
    assert 'min="2041-06-16"' in page and 'max="2041-07-25"' in page
    assert 'data-kind="practical" >Paper I: Practical' in page or '>Paper I: Practical</option>' in page
    assert 'Papers III &amp; II: Objective &amp; Essay' in page and 'Paper 1 (Objective)' not in page
    add = lambda d: c.post(f'/tools/exam-timetable/{tid}/papers', data={
        '_csrf_token': auth_csrf(c), 'exam_date': d, 'start_time': '10:00', 'end_time': '12:00',
        'subject': 'Chemistry', 'paper': 'Paper I: Practical', 'kind': 'practical'}, follow_redirects=True)
    assert 'after the exam ends' in add('2041-08-01').get_data(as_text=True)
    assert 'before the exam starts' in add('2041-06-01').get_data(as_text=True)
    add('2041-06-20')
    with app.app_context():
        assert ExamTimetablePaper.query.filter_by(timetable_id=tid).count() == 1
    # update details, including the window and the exam body
    r = c.post(f'/tools/exam-timetable/{tid}/details', data={
        '_csrf_token': auth_csrf(c), 'title': 'Renamed', 'board': 'waec', 'year': '2041',
        'start_date': '2041-06-25', 'end_date': '2041-07-25', 'notes': ''}, follow_redirects=True)
    assert 'fall outside the new exam dates' in r.get_data(as_text=True)
    with app.app_context():
        tt = db.session.get(ExamTimetable, tid)
        assert tt.title == 'Renamed' and tt.board == 'waec'
    # copy, then delete the copy
    c.post(f'/tools/exam-timetable/{tid}/duplicate', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        cp = ExamTimetable.query.filter_by(title='Renamed (copy)').one()
        assert len(cp.papers) == 1 and cp.start_date == tt.start_date
        cid = cp.id
    listing = c.get('/tools/exam-timetable/').get_data(as_text=True)
    assert 'Edit details' in listing and 'Make a copy' in listing
    c.post(f'/tools/exam-timetable/{cid}/delete', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        assert db.session.get(ExamTimetable, cid) is None


def test_subject_specific_papers_and_types(app):
    from routes.exam_timetable import papers_for
    from utils.exam_timetable import KIND_LABEL
    waec = [l for l, _k in papers_for('waec', 'Literature in English')]
    assert waec[:4] == ['Paper 1 (Objective)', 'Paper 2 (Prose)', 'Papers 2 & 1 (Prose & Objective)',
                        'Paper 3 (Drama & Poetry)']
    neco = dict(papers_for('neco', 'Literature-in-English'))
    assert neco['Paper II: Drama & Poetry'] == 'drama_poetry'
    assert neco['Papers III & IV: Objective & Prose'] == 'objective_prose'
    assert papers_for('waec', 'Mathematics')[0][0] == 'Paper 1 (Objective)'      # usual list otherwise
    assert {'Drama & Poetry', 'Objective & Prose', 'Prose', 'Alternative to Practical'} <= set(KIND_LABEL.values())
    c = _admin(app)
    c.post('/tools/exam-timetable/create', data={'_csrf_token': auth_csrf(c), 'board': 'waec', 'year': '2042'})
    with app.app_context():
        tid = ExamTimetable.query.filter_by(year=2042).order_by(ExamTimetable.id.desc()).first().id
    c.post(f'/tools/exam-timetable/{tid}/papers', data={
        '_csrf_token': auth_csrf(c), 'exam_date': '2042-05-05', 'start_time': '14:00', 'end_time': '16:30',
        'subject': 'Literature in English', 'paper': 'Paper 3 (Drama & Poetry)', 'kind': 'drama_poetry'})
    page = c.get(f'/tools/exam-timetable/{tid}').get_data(as_text=True)
    assert 'Drama &amp; Poetry' in page and 'k-drama_poetry' in page
    assert c.get(f'/tools/exam-timetable/{tid}/print').status_code == 200


def test_paste_many_papers_and_kept_fields(app):
    from routes.exam_timetable import papers_for
    neco_en = [l for l, _k in papers_for('neco', 'English Language')]
    assert 'Paper IV: Test of Orals' in neco_en and 'Paper I: Test of Orals' not in neco_en
    assert papers_for('waec', 'Geography')[3] == ('Paper 3 (Practical and Physical Geography)', 'practical_physical')
    assert ('Papers III & I: Objective & Practical / Physical', 'objective_practical') in papers_for('neco', 'Geography')
    c = _admin(app)
    c.post('/tools/exam-timetable/create', data={'_csrf_token': auth_csrf(c), 'board': 'waec', 'year': '2043',
                                                 'start_date': '2043-05-01', 'end_date': '2043-06-30'})
    with app.app_context():
        tid = ExamTimetable.query.filter_by(year=2043).order_by(ExamTimetable.id.desc()).first().id
    page = c.get(f'/tools/exam-timetable/{tid}/paste').get_data(as_text=True)
    assert 'Copy prompt' in page and 'date, start, end, subject, paper' in page
    data = ("2043-06-05, 9:30am, 11:30am, Geography, Paper 2 (Essay), Main Hall\n"
            "Friday, 5 June 2043, 11:30am - 12:30pm, Geo, Paper 1 (Objective)\n"
            "2043-06-05 | 3:30pm | 1hr 50mins | Geography | Paper 3 (Practical and Physical Geography)\n"
            "2043-07-09, 9:30am, 12:30pm, Maths, Paper 2 (Essay)\n"
            "nonsense line")
    prev = c.post(f'/tools/exam-timetable/{tid}/paste', data={'_csrf_token': auth_csrf(c), 'data': data,
                                                             'action': 'preview'}).get_data(as_text=True)
    assert '3 ready' in prev and '2 to fix' in prev and 'Outside the exam dates' in prev
    r = c.post(f'/tools/exam-timetable/{tid}/paste', data={'_csrf_token': auth_csrf(c), 'data': data, 'action': 'save'})
    assert r.status_code in (302, 303)
    with app.app_context():
        ps = ExamTimetablePaper.query.filter_by(timetable_id=tid).order_by(ExamTimetablePaper.start_time).all()
        assert [(p.subject, p.kind) for p in ps] == [('Geography', 'essay'), ('Geography', 'objective'),
                                                     ('Geography', 'practical_physical')]
        assert ps[2].end_time.strftime('%H:%M') == '17:20' and ps[0].venue == 'Main Hall'
    again = c.post(f'/tools/exam-timetable/{tid}/paste', data={'_csrf_token': auth_csrf(c), 'data': data,
                                                              'action': 'preview'}).get_data(as_text=True)
    assert '3 already added' in again                        # pasting twice doesn't double up
    # single add keeps date / times / hall / subject for the next paper
    r = c.post(f'/tools/exam-timetable/{tid}/papers', data={
        '_csrf_token': auth_csrf(c), 'exam_date': '2043-06-08', 'start_time': '09:30', 'end_time': '11:30',
        'subject': 'Literature in English', 'paper': 'Paper 2 (Prose)', 'venue': 'Hall B'})
    loc = r.headers['Location']
    assert 's=09:30' in loc and 'subj=Literature' in loc and 'v=Hall' in loc
    nxt = c.get(loc).get_data(as_text=True)
    assert '<option selected>Literature in English</option>' in nxt and 'value="Hall B"' in nxt
