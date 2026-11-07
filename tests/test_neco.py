"""NECO (SSCE) — a carbon copy of the WAEC pages on its own results table.

Every WAEC view is served again under /results/neco/… with the NECO table, so
these tests check the copy works end to end AND that WAEC and NECO figures
never mix."""
import uuid

from config import Config
from models import db, Student, WAECResult, NECOResult
from models.models import RateLimitHit
from tests.conftest import login_token, auth_csrf, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _student(app, surname, first, **kw):
    with app.app_context():
        s = Student(student_id='NC' + uuid.uuid4().hex[:6].upper(), first_name=first,
                    surname=surname, gender='Male', is_active=True, **kw)
        db.session.add(s); db.session.commit()
        return s.id


def _clear_export_hits(app):
    with app.app_context():
        RateLimitHit.query.filter(RateLimitHit.rkey.like('%export%')).delete(synchronize_session=False)
        db.session.commit()


def _seed(app, sid, model, year, grades):
    with app.app_context():
        for subj, g in grades.items():
            db.session.add(model(student_id=sid, exam_year=year, subject=subj, grade=g))
        db.session.commit()


def test_neco_add_saves_to_neco_table_only(app):
    sid = _student(app, 'Necoone', 'Ada')
    enroll_sss3(app, sid)
    c = _admin(app)
    html = c.get('/results/neco/add?year=2031').get_data(as_text=True)
    assert 'Add NECO Results' in html and 'ss-wrap' in html
    assert f'value="{sid}"' in html
    r = c.post('/results/neco/add', data={
        '_csrf_token': auth_csrf(c), 'student_id': sid, 'exam_year': 2031,
        'subject[]': ['Mathematics', 'English Language'], 'grade[]': ['A1', 'B3']})
    assert r.status_code == 302 and f'/results/neco/student/{sid}' in r.headers['Location']
    with app.app_context():
        assert {(x.subject, x.grade) for x in NECOResult.query.filter_by(student_id=sid)} == {
            ('Mathematics', 'A1'), ('English Language', 'B3')}
        assert WAECResult.query.filter_by(student_id=sid).count() == 0
    # Already entered → no longer offered for that year.
    html = c.get('/results/neco/add?year=2031').get_data(as_text=True)
    assert f'<option value="{sid}">' not in html


def test_neco_pages_show_neco_data_with_neco_links(app):
    _clear_export_hits(app)
    sid = _student(app, 'Necotwo', 'Bayo')
    enroll_sss3(app, sid)
    _seed(app, sid, NECOResult, 2032, {'Mathematics': 'A1', 'Physics': 'C4', 'Biology': 'F9'})
    _seed(app, sid, WAECResult, 2032, {'Mathematics': 'F9'})
    c = _admin(app)

    dash = c.get('/results/neco?year=2032').get_data(as_text=True)
    assert 'NECO Results' in dash and 'Necotwo' in dash
    assert '/results/neco/add' in dash and '/results/neco/broadsheet' in dash
    assert '/results/waec/add' not in dash and 'Result Generator' not in dash

    sub = c.get('/results/neco/subject/Mathematics?year=2032').get_data(as_text=True)
    assert 'NECO' in sub and 'A1' in sub

    an = c.get('/results/neco/analytics?year=2032')
    assert an.status_code == 200 and b'NECO Analytics' in an.data

    st = c.get(f'/results/neco/student/{sid}').get_data(as_text=True)
    assert 'Physics' in st and f'/results/neco/student/{sid}/edit/2032' in st

    bs = c.get('/results/neco/broadsheet?year=2032').get_data(as_text=True)
    assert 'NECO Broadsheet' in bs and 'Necotwo' in bs

    x = c.get('/results/neco/export?year=2032')
    assert x.status_code == 200 and 'neco_results_2032.xlsx' in x.headers['Content-Disposition']
    x = c.get('/results/neco/broadsheet/export?year=2032')
    assert x.status_code == 200 and 'neco_broadsheet_2032' in x.headers['Content-Disposition']
    x = c.get('/results/neco/broadsheet/download?year=2032&format=csv')
    assert x.status_code == 200 and 'A1' in x.get_data(as_text=True)

    api = c.get('/results/api/neco/grade-distribution/2032').get_json()
    assert api['A1'] >= 1
    # The WAEC side is untouched by the NECO rows (and vice versa).
    waec = c.get('/results/waec/broadsheet/download?year=2032&format=csv').get_data(as_text=True)
    assert 'F9' in waec and 'A1' not in waec.split('\n', 1)[1]
    _clear_export_hits(app)


def test_neco_edit_and_bulk_delete(app):
    sid = _student(app, 'Necothree', 'Chi')
    sid2 = _student(app, 'Necofour', 'Dayo')
    for s in (sid, sid2):
        enroll_sss3(app, s)
        _seed(app, s, NECOResult, 2033, {'Mathematics': 'C6'})
    _seed(app, sid, WAECResult, 2033, {'Mathematics': 'B2'})
    c = _admin(app)
    r = c.post(f'/results/neco/student/{sid}/edit/2033', data={
        '_csrf_token': auth_csrf(c), 'subject[]': ['Mathematics'], 'grade[]': ['B2']})
    assert r.status_code == 302
    with app.app_context():
        assert NECOResult.query.filter_by(student_id=sid, exam_year=2033).one().grade == 'B2'
    r = c.post('/results/neco/delete-bulk', data={
        '_csrf_token': auth_csrf(c), 'year': 2033, 'ids': [sid, sid2]})
    assert r.status_code == 302 and '/results/neco' in r.headers['Location']
    with app.app_context():
        assert NECOResult.query.filter(NECOResult.student_id.in_([sid, sid2])).count() == 0
        assert WAECResult.query.filter_by(student_id=sid).count() == 1   # WAEC kept


def test_neco_quick_entry_saves_neco_rows(app):
    sid = _student(app, 'Necofive', 'Efe')
    enroll_sss3(app, sid)
    c = _admin(app)
    line = 'Necofive Efe, Eng A1, Maths B2'
    r = c.post('/results/neco/quick?year=2034', data={'_csrf_token': auth_csrf(c), 'data': line})
    assert r.status_code == 200 and b'NECO Quick Entry' in r.data
    r = c.post('/results/neco/quick?year=2034', data={
        '_csrf_token': auth_csrf(c), 'data': line, 'action': 'confirm', 'approve_roster': '1'})
    assert r.status_code == 302 and '/results/neco' in r.headers['Location']
    with app.app_context():
        assert NECOResult.query.filter_by(student_id=sid, exam_year=2034).count() == 2
        assert WAECResult.query.filter_by(student_id=sid).count() == 0


def test_neco_paste_preview_posts_to_neco_save(app):
    sid = _student(app, 'Necosix', 'Femi')
    enroll_sss3(app, sid)
    c = _admin(app)
    r = c.post('/results/neco/paste', data={
        '_csrf_token': auth_csrf(c), 'exam_year': 2035,
        'data': 'Necosix Femi\nEnglish Language, B3\nMathematics, C4'})
    body = r.get_data(as_text=True)
    assert '/results/neco/paste/save' in body and '/waec/paste/save' not in body


def test_student_neco_fields_are_saved(app):
    sid = _student(app, 'Necoseven', 'Gbenga', neco_reg_number='NECO123', neco_epin='TOK9')
    with app.app_context():
        st = db.session.get(Student, sid)
        assert st.neco_reg_number == 'NECO123' and st.has_identity


def test_neco_permissions_are_their_own_subsection():
    from utils.access_control import MODULE_SUBSECTIONS
    subs = MODULE_SUBSECTIONS['external_exams']
    for k in ('neco_view', 'neco_create', 'neco_edit', 'neco_delete', 'neco_export'):
        assert k in subs


def test_exam_report_shows_neco_and_offers_missing_neco(app):
    from datetime import date
    from utils.helpers import session_exam_year, get_active_session
    sid = _student(app, 'Necoeight', 'Halima')
    other = _student(app, 'Neconine', 'Ike')
    enroll_sss3(app, sid); enroll_sss3(app, other)
    with app.app_context():
        year = session_exam_year(get_active_session()) or date.today().year
    _seed(app, sid, NECOResult, year, {'Mathematics': 'A1'})
    c = _admin(app)
    html = c.get(f'/results/student/{sid}/report').get_data(as_text=True)
    assert '<!-- NECO' in html and 'Add NECO result' not in html
    # The school records NECO, so a candidate without this year's NECO gets the button.
    html = c.get(f'/results/student/{other}/report').get_data(as_text=True)
    assert 'Add NECO result' in html
    assert f'/results/neco/add?student_id={other}' in html.replace('&amp;', '&')


def test_student_profile_payload_has_neco_card(app):
    sid = _student(app, 'Necoten', 'Jide', neco_reg_number='N-77')
    with app.app_context():
        from routes.main import _student_neco_card
        with app.test_request_context():
            card = _student_neco_card(db.session.get(Student, sid))
    assert card and card['count'] == 0 and '/results/neco/add' in card['add_url']


def test_exam_analytics_overview_includes_neco_and_waec_vs_neco(app):
    from utils import waec_neco
    year = 2036
    combo = _student(app, 'Neconcombo', 'Kola')        # qualifies only by combining
    single = _student(app, 'Necosingle', 'Lara')       # qualifies in WAEC alone
    _seed(app, combo, WAECResult, year, {'English Language': 'C6', 'Mathematics': 'B3',
                                         'Biology': 'C5', 'Chemistry': 'C4', 'Physics': 'F9'})
    _seed(app, combo, NECOResult, year, {'English Language': 'D7', 'Mathematics': 'C6',
                                         'Physics': 'C6', 'Biology': 'E8'})
    _seed(app, single, WAECResult, year, {'English Language': 'B2', 'Mathematics': 'A1',
                                          'Biology': 'B3', 'Chemistry': 'C4', 'Physics': 'C5'})
    _seed(app, single, NECOResult, year, {'English Language': 'C4', 'Mathematics': 'F9'})
    with app.app_context():
        cmp = waec_neco.compare(year)
    assert cmp['both'] == 2 and cmp['waec_ok'] == 1 and cmp['neco_ok'] == 0
    assert cmp['either_ok'] == 1 and cmp['combined_ok'] == 2
    assert cmp['gained_by_combining'] == ['Neconcombo Kola']
    phys = next(x for x in cmp['subjects'] if x['subject'] == 'Physics')
    assert phys['waec']['credit_rate'] == 50.0 and phys['neco']['credit_rate'] == 100.0
    h = cmp['head_to_head']
    assert h['pairs'] == 6 and h['waec_better'] + h['neco_better'] + h['same'] == 6

    c = _admin(app)
    html = c.get(f'/results/analytics?year={year}').get_data(as_text=True)
    assert 'id="sec-neco"' in html and 'NECO pass rate' in html
    assert 'id="sec-waec-neco"' in html and 'Combining both sittings' in html
    assert 'Neconcombo Kola' in html and 'id="necoGenderCmp"' in html
    # A year with WAEC only shows no NECO section (schools that don't sit NECO).
    other = _student(app, 'Waeconly', 'Musa')
    _seed(app, other, WAECResult, 2037, {'Mathematics': 'A1'})
    html = c.get('/results/analytics?year=2037').get_data(as_text=True)
    assert 'id="sec-neco"' not in html and 'id="sec-waec-neco"' not in html


def test_waec_and_neco_subject_extras_and_best_overall(app):
    """Subjects view: entries, average points, change vs last year, totals row
    and more sort options; Top performers: Best overall — on WAEC and NECO."""
    star = _student(app, 'Extrastar', 'Ola')
    weak = _student(app, 'Extraweak', 'Tobi')
    for model in (WAECResult, NECOResult):
        _seed(app, star, model, 2040, {'Mathematics': 'C6', 'Physics': 'A1'})
        _seed(app, weak, model, 2040, {'Mathematics': 'F9', 'Physics': 'B3'})
        _seed(app, star, model, 2041, {'Mathematics': 'A1', 'Physics': 'A1'})
        _seed(app, weak, model, 2041, {'Mathematics': 'C5', 'Physics': 'F9'})
    c = _admin(app)
    for board in ('waec', 'neco'):
        html = c.get(f'/results/{board}?year=2041&view=subjects&sort=subject_name&order=asc').get_data(as_text=True)
        assert 'All subjects' in html and 'Avg pts' in html and 'vs 2040' in html
        assert 'Entries' in html and 'Name A–Z' in html
        table = html[html.index('<table class="subject-table">'):]
        maths = table[table.index('Mathematics'):]
        assert 'fa-arrow-up' in maths[:2500]            # Maths 50% → 100%: up 50
        assert table.index('Mathematics') < table.index('Physics')   # sorted by name
        html = c.get(f'/results/{board}?year=2041&view=top').get_data(as_text=True)
        assert 'Best Overall' in html
        best = html[html.index('Best Overall'):]
        assert best.index('Extrastar Ola') < best.index('Extraweak Tobi')
