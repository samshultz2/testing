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
               or AcademicSession(name='2025/2026', is_active=True))
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
    _enroll(app, 'Primary 6', 0, _student(app, 'Pry')[0])
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
    _enroll(app, 'Primary 6', 0, sid)
    tok = auth_csrf(c)
    text = ('Student ID\tExam Number\tMathematics\tEnglish Studies\tVerbal Reasoning\tTotal\n'
            f'{code}\tNCEE/9\t81\tB\t44\t190\n'
            'NOPE\t\t50\t50\t50\t\n')
    r = c.post('/basic6-exams/federal/import',
               data={'_csrf_token': tok, 'year': 2026, 'data': text, 'action': 'preview'})
    html = r.get_data(as_text=True)
    assert 'Tester Chi' in html and 'no BASIC6 student matches' in html
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
    assert subsection_for_endpoint('jss3_exams.dashboard') == ('external_exams', 'jss3')
    assert subsection_for_endpoint('basic6_exams.analytics') == ('external_exams', 'basic6')
    assert BLUEPRINT_MODULE['exam_levels'] == 'external_exams'
