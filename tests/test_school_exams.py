"""JSS3 (State / NECO BECE) and Basic 6 (State Common Entrance / NCEE) exams:
grading, level separation, entry flows (single, grid, paste), analytics and
the per-level pages."""
import uuid

from config import Config
from models import db, Student
from models.models_school_exams import (SchoolExamResult, SchoolExamCandidate, ExamScheme,
                                        normalise_bands, get_scheme)
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _enroll(app, class_name, level_no, student_id):
    from models import (AcademicSession, Term, SchoolClass, ClassArm,
                        ClassArmAssignment, StudentEnrollment)
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='ENR 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True))
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name=class_name).first() or SchoolClass(name=class_name, level=level_no)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(name='Gold').first() or ClassArm(name='Gold', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id))
        db.session.add(caa); db.session.flush()
        db.session.add(StudentEnrollment(student_id=student_id, class_arm_assignment_id=caa.id,
                                         is_active=True))
        db.session.commit()


def _student(app, first, gender='Female'):
    with app.app_context():
        s = Student(student_id='SX' + uuid.uuid4().hex[:6].upper(), first_name=first,
                    surname='Tester', gender=gender)
        db.session.add(s)
        db.session.commit()
        return s.id, s.student_id


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #
def test_default_state_bece_bands():
    sc = ExamScheme('jss3', 'state')
    assert [b['grade'] for b in sc.bands] == ['A', 'B', 'C', 'P', 'F']
    assert sc.grade_from_score(70) == 'A'
    assert sc.grade_from_score(69.5) == 'B'
    assert sc.grade_from_score(50) == 'C'
    assert sc.grade_from_score(40) == 'P'
    assert sc.grade_from_score(39) == 'F'
    assert sc.grade_from_score(None) is None
    assert sc.is_credit('B') and not sc.is_credit('P') and sc.is_pass('P')


def test_neco_bece_uses_four_bands():
    sc = ExamScheme('jss3', 'federal')
    assert sc.grades == ['A', 'C', 'P', 'F']
    assert sc.grade_from_score(65) == 'C'
    assert sc.kind_of('A') == 'distinction'


def test_band_normalisation_sorts_and_anchors_zero():
    bands = normalise_bands([{'grade': 'f', 'min': 5, 'kind': 'fail', 'label': 'Fail'},
                             {'grade': 'A', 'min': 80, 'kind': 'distinction'},
                             {'grade': '', 'min': 50, 'kind': 'credit'},          # dropped
                             {'grade': 'X', 'min': 'no', 'kind': 'credit'}])      # dropped
    assert [b['grade'] for b in bands] == ['A', 'F']
    assert bands[-1]['min'] == 0


def test_max_score_scales_banding():
    class Row:
        exam_name = 'NCEE'; subjects_json = None; bands_json = None
        max_score = 50; benchmark_credits = None; cutoff = None
    sc = ExamScheme('basic6', 'federal', Row())
    assert sc.grade_from_score(35) == 'A'     # 70% of 50
    assert sc.grade_from_score(19) == 'F'


# --------------------------------------------------------------------------- #
# Pages, entry and analytics
# --------------------------------------------------------------------------- #
def test_level_class_matching_is_tolerant(app):
    from utils.school_exams import find_level_class, _norm, _CLASS_NAMES
    _enroll(app, 'Primary 6', 90, _student(app, 'Pry')[0])
    with app.app_context():
        assert find_level_class('basic6').name == 'Primary 6'
        assert find_level_class('jss3') is not None
    for name in ('JSS 3', 'J.S.S. 3', 'Junior Secondary 3', 'JS3'):
        assert _norm(name) in _CLASS_NAMES['jss3'], name
    for name in ('Basic 6', 'Pry 6', 'PRIMARY 6', 'P6'):
        assert _norm(name) in _CLASS_NAMES['basic6'], name
    assert _norm('JSS 2') not in _CLASS_NAMES['jss3']


def test_pages_render_for_both_levels(app):
    c = _admin(app)
    for level in ('jss3', 'basic6'):
        for path in ('/', '/?body=federal', '/analytics', '/analytics?body=federal', '/compare',
                     '/state/grid', '/federal/grid?mode=grade', '/state/add', '/federal/import',
                     '/settings', '/settings?body=federal'):
            r = c.get(f'/{level}-exams{path}')
            assert r.status_code == 200, (level, path, r.status_code)
    r = c.get('/exam-levels/')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'JSS3' in html and 'Basic 6' in html and 'SSS3' in html


def test_entry_analytics_and_level_separation(app):
    c = _admin(app)
    ada, _ = _student(app, 'Ada')
    bola, _ = _student(app, 'Bola', gender='Male')
    for sid in (ada, bola):
        _enroll(app, 'JSS3', 3, sid)
    tok = auth_csrf(c)
    subjects = ['English Studies', 'Mathematics', 'Basic Science', 'Social Studies',
                'Civic Education', 'Business Studies']
    # Ada: credits everywhere (meets the 6-credit benchmark); Bola: fails Maths.
    r = c.post('/jss3-exams/state/add', data={
        '_csrf_token': tok, 'student_id': ada, 'exam_year': 2026,
        'subject[]': subjects, 'score[]': ['75', '66', '58', '52', '50', '71'],
        'grade[]': [''] * 6, 'exam_number': 'BECE/01', 'placement': 'SSS1 Science',
        'admitted': 'yes'})
    assert r.status_code == 302
    r = c.post('/jss3-exams/state/grid', data={
        '_csrf_token': tok, 'year': 2026, 'mode': 'score',
        'col': ['English Studies', 'Mathematics', 'Basic Science'],
        f'v_{bola}_0': '55', f'v_{bola}_1': '30', f'v_{bola}_2': '45',
        f'exam_number_{bola}': 'BECE/02'})
    assert r.status_code == 302
    with app.test_request_context():
        from flask import session
        session['role'] = 'super_admin'          # central: every branch in view
        rows = SchoolExamResult.query.filter_by(student_id=bola, level='jss3').all()
        assert {r.subject: r.grade for r in rows} == {
            'English Studies': 'C', 'Mathematics': 'F', 'Basic Science': 'P'}
        from utils.school_exams import year_stats
        st = year_stats('jss3', 'state', 2026)
        k = st['kpis']
        assert k['candidates'] == 2
        assert k['core_credit'] == 1 and k['benchmark'] == 1
        assert k['admitted'] == 1
        assert st['candidates'][0]['id'] == ada
        maths = next(r for r in st['subjects'] if r['subject'] == 'Mathematics')
        assert maths['entries'] == 2 and maths['credit_rate'] == 50.0
        assert {g['group'] for g in st['by_gender']} == {'Female', 'Male'}
        assert st['by_arm'][0]['group'] == 'Gold'
        # Nothing leaks into Basic 6 or into the federal exam.
        assert year_stats('basic6', 'state', 2026)['kpis']['candidates'] == 0
        assert year_stats('jss3', 'federal', 2026)['kpis']['candidates'] == 0

    html = c.get('/jss3-exams/?body=state&year=2026').get_data(as_text=True)
    assert 'BECE/01' in html and 'Tester Ada' in html
    assert 'Tester Ada' not in c.get('/basic6-exams/?year=2026').get_data(as_text=True)
    for path in ('/analytics?body=state&year=2026', '/compare?year=2026',
                 '/subject/state/Mathematics?year=2026', f'/state/student/{ada}'):
        assert c.get('/jss3-exams' + path).status_code == 200, path
    r = c.get('/jss3-exams/state/export?year=2026')
    assert r.status_code == 200 and r.data[:2] == b'PK'


def test_paste_import_preview_and_confirm(app):
    c = _admin(app)
    sid, code = _student(app, 'Chi')
    _enroll(app, 'Primary 6', 90, sid)
    tok = auth_csrf(c)
    text = ('Student ID\tExam Number\tMathematics\tEnglish Studies\tVerbal Reasoning\tTotal\n'
            f'{code}\tNCEE/9\t81\tB\t44\t190\n'
            'NOPE\t\t50\t50\t50\t\n')
    r = c.post('/basic6-exams/federal/import',
               data={'_csrf_token': tok, 'year': 2026, 'data': text, 'action': 'preview'})
    html = r.get_data(as_text=True)
    assert 'Tester Chi' in html and 'needs at least a surname and a first name' in html
    r = c.post('/basic6-exams/federal/import',
               data={'_csrf_token': tok, 'year': 2026, 'data': text, 'action': 'confirm'})
    assert r.status_code == 302
    with app.app_context():
        got = {r.subject: (r.grade, r.score) for r in SchoolExamResult.query.filter_by(
            student_id=sid, level='basic6', body='federal').all()}
        assert got == {'Mathematics': ('A', 81.0), 'English Studies': ('B', None),
                       'Verbal Reasoning': ('P', 44.0)}
        cand = SchoolExamCandidate.query.filter_by(student_id=sid, level='basic6').one()
        assert cand.exam_number == 'NCEE/9' and cand.total_score == 190


def test_settings_change_grading_and_cutoff(app):
    c = _admin(app)
    tok = auth_csrf(c)
    r = c.post('/basic6-exams/settings', data={
        '_csrf_token': tok, 'body': 'state', 'exam_name': 'Lagos Placement Exam',
        'max_score': '100', 'benchmark_credits': '3', 'cutoff': '150',
        'subjects': 'Mathematics\nEnglish Studies\nmathematics',
        'band_grade': ['A', 'C', 'F', ''], 'band_label': ['Excellent', 'Good', 'Fail', ''],
        'band_min': ['80', '50', '0', ''], 'band_kind': ['distinction', 'credit', 'fail', 'credit']})
    assert r.status_code == 302
    with app.app_context():
        sc = get_scheme('basic6', 'state')
        assert sc.exam_name == 'Lagos Placement Exam'
        assert sc.subjects == ['Mathematics', 'English Studies']
        assert sc.grades == ['A', 'C', 'F'] and sc.grade_from_score(79) == 'C'
        assert sc.cutoff == 150 and sc.benchmark_credits == 3
        # The JSS3 module's settings are untouched.
        assert get_scheme('jss3', 'state').exam_name == 'State BECE'
    c.post('/basic6-exams/settings', data={'_csrf_token': tok, 'body': 'state', 'action': 'reset'})
    with app.app_context():
        assert get_scheme('basic6', 'state').exam_name == 'State Common Entrance'


def test_each_level_is_its_own_permission_subsection():
    from utils.access_control import subsection_for_endpoint, BLUEPRINT_MODULE
    assert subsection_for_endpoint('jss3_exams.dashboard') == ('external_exams', 'jss3_view')
    assert subsection_for_endpoint('jss3_exams.grid_entry') == ('external_exams', 'jss3_create')
    assert subsection_for_endpoint('basic6_exams.analytics') == ('external_exams', 'basic6_view')
    assert subsection_for_endpoint('basic6_exams.delete_student_year') == ('external_exams', 'basic6_delete')
    assert subsection_for_endpoint('basic6_exams.settings') == ('external_exams', 'basic6_settings')
    assert BLUEPRINT_MODULE['exam_levels'] == 'external_exams'


def test_candidate_sorting_helper():
    from utils.school_exams import sort_candidates
    c = [dict(name='Bello Ada', position=2, distinctions=3, credits=8, avg_pct=70.0, total=600),
         dict(name='Adams Wealth', position=3, distinctions=5, credits=7, avg_pct=65.0, total=None),
         dict(name='Okafor Jide', position=1, distinctions=5, credits=9, avg_pct=80.0, total=700)]
    names = lambda key: [x['name'] for x in sort_candidates(c, key)[0]]
    assert names('position') == ['Okafor Jide', 'Bello Ada', 'Adams Wealth']
    assert names('name') == ['Adams Wealth', 'Bello Ada', 'Okafor Jide']
    assert names('name_desc') == ['Okafor Jide', 'Bello Ada', 'Adams Wealth']
    # most distinctions first; tie (5 each) broken by credits
    assert names('distinctions') == ['Okafor Jide', 'Adams Wealth', 'Bello Ada']
    assert names('total')[-1] == 'Adams Wealth'                  # no total sorts last
    assert sort_candidates(c, 'bogus')[1] == 'position'


def test_dashboard_sorts_alphabetically_and_by_distinction(app):
    c = _admin(app)
    zed, _ = _student(app, 'Zed', gender='Male')
    amy, _ = _student(app, 'Amy')
    for sid in (zed, amy):
        _enroll(app, 'JSS3', 3, sid)
    tok = auth_csrf(c)
    # Zed: 2 distinctions; Amy: none — but "Tester Amy" < "Tester Zed" alphabetically.
    for sid, scores in ((zed, ['80', '75']), (amy, ['55', '52'])):
        c.post('/jss3-exams/state/add', data={'_csrf_token': tok, 'student_id': sid, 'exam_year': 2037,
               'subject[]': ['Mathematics', 'English Studies'], 'score[]': scores, 'grade[]': ['', '']})

    def order(sort):
        html = c.get(f'/jss3-exams/?body=state&year=2037&sort={sort}').get_data(as_text=True)
        assert 'id="sxSort"' in html
        html = html[html.index('Candidates ('):]        # the table, not flash messages
        return html.index('Tester Amy') < html.index('Tester Zed')
    assert order('name') is True
    assert order('name_desc') is False
    assert order('distinctions') is False
    html = c.get('/jss3-exams/?body=state&year=2037&sort=distinctions').get_data(as_text=True)
    assert '<option value="distinctions" selected>' in html and 'aria-sort=' in html


def test_entered_students_are_hidden_from_add_and_grid(app):
    c = _admin(app)
    done, _ = _student(app, 'Doneentry')
    todo, _ = _student(app, 'Todoentry')
    for sid in (done, todo):
        _enroll(app, 'JSS3', 3, sid)
    tok = auth_csrf(c)
    c.post('/jss3-exams/state/add', data={'_csrf_token': tok, 'student_id': done, 'exam_year': 2039,
           'subject[]': ['Mathematics'], 'score[]': ['60'], 'grade[]': ['']})
    opt = lambda sid: f'<option value="{sid}"'
    html = c.get('/jss3-exams/state/add?year=2039').get_data(as_text=True)
    assert opt(todo) in html and opt(done) not in html and 'are not listed' in html
    # Another exam body or year still lists them.
    assert opt(done) in c.get('/jss3-exams/federal/add?year=2039').get_data(as_text=True)
    assert opt(done) in c.get('/jss3-exams/state/add?year=2040').get_data(as_text=True)
    # Opening them via Edit keeps them selectable.
    assert opt(done) in c.get(f'/jss3-exams/state/add?year=2039&student_id={done}').get_data(as_text=True)
    # Grid: hidden by default, back with ?show=all.
    grid = c.get('/jss3-exams/state/grid?year=2039').get_data(as_text=True)
    assert f'exam_number_{todo}' in grid and f'exam_number_{done}' not in grid and 'are hidden' in grid
    assert f'exam_number_{done}' in c.get('/jss3-exams/state/grid?year=2039&show=all').get_data(as_text=True)


def test_broadsheet_page_and_exports_like_waec(app):
    import fitz
    from models.models import RateLimitHit
    c = _admin(app)
    a, _ = _student(app, 'Bsheetada')
    b, _ = _student(app, 'Bsheetben', gender='Male')
    for sid in (a, b):
        _enroll(app, 'JSS3', 3, sid)
    tok = auth_csrf(c)
    for sid, scores in ((a, ['72', '66']), (b, ['48', '55'])):
        c.post('/jss3-exams/state/add', data={'_csrf_token': tok, 'student_id': sid, 'exam_year': 2049,
               'subject[]': ['Mathematics', 'English Studies'], 'score[]': scores, 'grade[]': ['', '']})
    with app.app_context():
        # Start from a clean export allowance (earlier tests share this admin).
        RateLimitHit.query.filter(RateLimitHit.rkey.like('%export%')).delete(synchronize_session=False)
        db.session.commit()
        top = db.session.query(db.func.max(RateLimitHit.id)).scalar() or 0
    try:
        html = c.get('/jss3-exams/state/broadsheet?year=2049').get_data(as_text=True)
        assert 'Tester Bsheetada' in html and 'Custom download' in html and 'id="bsSize"' in html
        pdf = c.get('/jss3-exams/state/broadsheet.pdf?year=2049&size=A3')
        assert pdf.status_code == 200 and pdf.data[:4] == b'%PDF'
        with fitz.open(stream=pdf.data, filetype='pdf') as d:
            txt = ' '.join(p.get_text() for p in d)
        assert 'Broadsheet' in txt and 'Tester Bsheetada' in txt and 'Avg %' in txt
        base = '/jss3-exams/state/broadsheet/download?year=2049'
        csv = c.get(base + '&format=csv&order=position&names=first').get_data(as_text=True)
        lines = csv.strip().splitlines()
        assert lines[0].startswith('S/N,Candidate,English Studies,Mathematics')
        assert 'Bsheetada' in lines[1] and 'A (72)' in lines[1]             # best first
        assert 'Tester' not in csv                                          # first name only
        assert c.get(base + '&format=excel').data[:2] == b'PK'
        assert c.get(base + '&format=pdf').data[:4] == b'%PDF'
        img = c.get(base + '&format=image')
        assert img.data[:4] == b'\x89PNG' and img.headers.get('X-Total-Pages')
        # Basic 6 has its own broadsheet too.
        assert c.get('/basic6-exams/federal/broadsheet').status_code == 200
    finally:
        with app.app_context():
            RateLimitHit.query.filter(RateLimitHit.id > top).delete(synchronize_session=False)
            db.session.commit()


def test_add_result_student_dropdown_is_searchable(app):
    c = _admin(app)
    for path in ('/jss3-exams/federal/add', '/jss3-exams/state/add', '/basic6-exams/state/add',
                 '/basic6-exams/federal/add'):
        html = c.get(path).get_data(as_text=True)
        if 'id="sxStudentSel"' not in html:          # no students on this roster yet
            continue
        assert '.ss-wrap' in html and 'Search name or admission no.' in html, path


def test_exam_report_shows_bece_for_a_jss3_pupil(app):
    from tests.conftest import enroll_sss3
    c = _admin(app)
    sid, _ = _student(app, 'Reportjss')
    _enroll(app, 'JSS3', 3, sid)
    tok = auth_csrf(c)
    subjects = ['English Studies', 'Mathematics', 'Basic Science', 'Basic Technology',
                'Social Studies', 'Business Studies']
    c.post('/jss3-exams/federal/add', data={
        '_csrf_token': tok, 'student_id': sid, 'exam_year': 2050, 'exam_number': 'NB/77',
        'subject[]': subjects, 'score[]': ['75', '45', '80', '72', '52', '58'], 'grade[]': [''] * 6,
        'placement': 'SSS1 Science'})
    html = c.get(f'/results/student/{sid}/report').get_data(as_text=True)
    assert 'NECO BECE 2050' in html and 'NB/77' in html
    assert 'SSS1 Readiness' in html and 'Below the benchmark' in html     # Maths only a pass
    assert 'No credit yet in Mathematics' in html
    assert 'Suggested SSS stream' in html
    assert '<h2><i class="fas fa-file-alt"></i> WAEC</h2>' not in html     # no SSS3 sections
    assert 'Admission Readiness' not in html

    # An SSS3 student keeps the WAEC report, with their BECE as history.
    s3, _ = _student(app, 'Reportsss')
    _enroll(app, 'JSS3', 3, s3)
    c.post('/jss3-exams/state/add', data={'_csrf_token': tok, 'student_id': s3, 'exam_year': 2048,
           'subject[]': ['Mathematics'], 'score[]': ['70'], 'grade[]': ['']})
    with app.app_context():
        from models import StudentEnrollment
        StudentEnrollment.query.filter_by(student_id=s3).update({'is_active': False})
        db.session.commit()
    enroll_sss3(app, s3)
    html = c.get(f'/results/student/{s3}/report').get_data(as_text=True)
    assert '<h2><i class="fas fa-file-alt"></i> WAEC</h2>' in html
    assert 'Earlier exams — BECE / Common Entrance' in html and 'State BECE 2048' in html
