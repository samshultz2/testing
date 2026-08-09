"""Cross-year WAEC/JAMB trend aggregation + the Trends page (roadmap #4)."""
from config import Config
from models import db, Branch, Student, WAECResult, JAMBResult
from utils.analytics_service import AcademicAnalytics

_Y1, _Y2 = 2481, 2482      # sentinel years owned solely by this test
_SEQ = [0]


def _student(bid):
    _SEQ[0] += 1
    s = Student(student_id=f'MYT-{_SEQ[0]}', first_name='T', surname=f'S{_SEQ[0]}',
                gender='Male', is_active=True, branch_id=bid)
    db.session.add(s); db.session.flush()
    return s


def _seed(app):
    with app.app_context():
        bid = Branch.get_default().id
        # Year 1: one candidate with 5 credits incl. core.
        a = _student(bid)
        for subj, g in {'English Language': 'B3', 'Mathematics': 'C4', 'Physics': 'C5',
                        'Chemistry': 'C6', 'Biology': 'B2'}.items():
            db.session.add(WAECResult(student_id=a.id, exam_year=_Y1, subject=subj, grade=g))
        # Year 2: one candidate who fails core (0 credits incl. core, an F9 present).
        b = _student(bid)
        for subj, g in {'English Language': 'F9', 'Mathematics': 'D7', 'Physics': 'E8'}.items():
            db.session.add(WAECResult(student_id=b.id, exam_year=_Y2, subject=subj, grade=g))
        # JAMB across both years.
        for yr, score in ((_Y1, 260), (_Y2, 180)):
            st = _student(bid)
            db.session.add(JAMBResult(student_id=st.id, exam_year=yr, total_score=score,
                                      subject1='English Language', subject1_score=60))
        db.session.commit()


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_waec_multiyear_trend_points(app):
    _seed(app)
    with app.app_context():
        tr = AcademicAnalytics.get_waec_multiyear_trends()
    pts = {p['year']: p for p in tr['points']}
    assert _Y1 in pts and _Y2 in pts
    # Ratios are stable even though the shared-DB fixture may seed twice.
    assert pts[_Y1]['with_5_incl_core_pct'] == 100.0
    assert pts[_Y2]['with_5_incl_core_pct'] == 0
    assert pts[_Y2]['f9_rate'] > 0                    # the F9 shows up as a fail
    # oldest → newest ordering
    yrs = [p['year'] for p in tr['points']]
    assert yrs == sorted(yrs)


def test_jamb_multiyear_trend_points(app):
    _seed(app)
    with app.app_context():
        tr = AcademicAnalytics.get_jamb_multiyear_trends()
    pts = {p['year']: p for p in tr['points']}
    assert pts[_Y1]['avg_score'] == 260.0 and pts[_Y1]['above_200_pct'] == 100.0
    assert pts[_Y2]['avg_score'] == 180.0 and pts[_Y2]['above_200_pct'] == 0


def test_trends_page_renders(app):
    _seed(app)
    c = _admin(app)
    r = c.get('/results/analytics/trends')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Exam Trends' in body
    assert 'WAEC' in body and 'JAMB' in body
