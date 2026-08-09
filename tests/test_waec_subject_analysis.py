"""Per-subject WAEC analysis page + reversed average grade points (A1=9…F9=1),
plus the JAMB (score-based) per-subject analysis."""
from models import db, Branch, Student, WAECResult, JAMBResult
from config import Config
from utils.analytics_service import AcademicAnalytics

_YR = 2471   # a sentinel year owned solely by this test
_JYR = 2288  # sentinel JAMB year
_SEQ = [0]


def _seed(app):
    with app.app_context():
        bid = Branch.get_default().id
        grades = ['A1', 'A1', 'B2', 'C4', 'F9']   # Mathematics distribution
        for g in grades:
            _SEQ[0] += 1
            st = Student(student_id=f'WSA-{_SEQ[0]}', first_name='S', surname=f'T{_SEQ[0]}',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            db.session.add(WAECResult(student_id=st.id, exam_year=_YR,
                                      subject='Mathematics', grade=g))
        db.session.commit()


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_subject_analysis_distribution_and_reversed_average(app):
    _seed(app)
    with app.app_context():
        d = AcademicAnalytics.get_waec_subject_analysis('Mathematics', _YR)
    assert d['total'] == 5
    assert d['counts']['A1'] == 2 and d['counts']['B2'] == 1 and d['counts']['F9'] == 1
    assert d['a1_count'] == 2
    assert d['credit_count'] == 4 and d['fail_count'] == 1   # A1,A1,B2,C4 credit; F9 fail
    # reversed scale: A1=9,A1=9,B2=8,C4=6,F9=1 → 33/5 = 6.6 (higher is better)
    assert d['average_points'] == 6.6
    # two A1 candidates are listed under the A1 bucket
    assert len(d['by_grade']['A1']) == 2


def test_subject_page_renders_and_links(app):
    _seed(app)
    c = _admin(app)
    r = c.get(f'/results/waec/subject/Mathematics?year={_YR}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Grade distribution' in body and 'Mathematics' in body
    # the WAEC dashboard subjects view links each subject to its analysis page
    r2 = c.get(f'/results/waec?year={_YR}&view=subjects')
    assert f'/results/waec/subject/Mathematics' in r2.get_data(as_text=True)


def _seed_jamb(app):
    with app.app_context():
        bid = Branch.get_default().id
        scores = [80, 60, 45, 20]   # Physics scores → 1 each of the top bands
        for sc in scores:
            _SEQ[0] += 1
            st = Student(student_id=f'JBA-{_SEQ[0]}', first_name='J', surname=f'T{_SEQ[0]}',
                         gender='Male', is_active=True, branch_id=bid)
            db.session.add(st); db.session.flush()
            db.session.add(JAMBResult(student_id=st.id, exam_year=_JYR, total_score=sc * 4,
                                      subject1='Physics', subject1_score=sc,
                                      subject2='English Language', subject2_score=50))
        db.session.commit()


def test_jamb_subject_score_analysis(app):
    _seed_jamb(app)
    with app.app_context():
        d = AcademicAnalytics.get_jamb_subject_analysis('Physics', _JYR)
    assert d['total'] == 4
    assert d['avg_score'] == 51.2 or round(d['avg_score']) == 51   # (80+60+45+20)/4
    assert d['above_70'] == 1 and d['above_50'] == 2
    # one candidate per band (Excellent/Good/Fair/Poor)
    bands = {b['label'][:4]: b['count'] for b in d['distribution']}
    assert bands['Exce'] == 1 and bands['Good'] == 1


def test_jamb_subject_page_renders_and_links(app):
    _seed_jamb(app)
    c = _admin(app)
    r = c.get(f'/results/jamb/subject/Physics?year={_JYR}')
    assert r.status_code == 200
    assert 'Score distribution' in r.get_data(as_text=True)
    r2 = c.get(f'/results/jamb?year={_JYR}&view=subjects')
    assert '/results/jamb/subject/Physics' in r2.get_data(as_text=True)
