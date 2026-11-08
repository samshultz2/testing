"""Exam Trends page (utils.exam_yoy): per-year measures, the year-over-year
comparison with its "real change or chance" test, subject movement, the
action list, and the page itself for every exam."""
import uuid

from config import Config
from models import db, Branch, Student, WAECResult, NECOResult, JAMBResult
from tests.conftest import login_token

Y1, Y2, Y3 = 2391, 2392, 2393


def _branch():
    b = Branch(name='YoY ' + uuid.uuid4().hex[:6], code='Y' + uuid.uuid4().hex[:5].upper(), is_active=True)
    db.session.add(b); db.session.flush()
    return b.id


def _pupil(bid, gender):
    s = Student(student_id='YY' + uuid.uuid4().hex[:7].upper(), first_name='P', surname='Q',
                gender=gender, is_active=True, branch_id=bid)
    db.session.add(s); db.session.flush()
    return s.id


GOOD = {'English Language': 'B3', 'Mathematics': 'C4', 'Physics': 'C5', 'Chemistry': 'C6', 'Biology': 'B2'}
WEAK = {'English Language': 'D7', 'Mathematics': 'C6', 'Physics': 'F9', 'Chemistry': 'E8', 'Biology': 'C5'}


def _seed(app, model=WAECResult):
    """30 candidates a year: Y1 10 meet the benchmark, Y2 15, Y3 27 (a real rise)."""
    with app.app_context():
        bid = _branch()
        for yr, n_good in ((Y1, 10), (Y2, 15), (Y3, 27)):
            for i in range(30):
                sid = _pupil(bid, 'Female' if i % 2 else 'Male')
                for subj, g in (GOOD if i < n_good else WEAK).items():
                    db.session.add(model(student_id=sid, exam_year=yr, subject=subj, grade=g))
            for i in range(30):
                sid = _pupil(bid, 'Female' if i % 2 else 'Male')
                db.session.add(JAMBResult(student_id=sid, exam_year=yr, total_score=150 + (yr - Y1) * 40 + i,
                                          subject1='Use of English', subject1_score=50 + (yr - Y1) * 5,
                                          subject2='Physics', subject2_score=60))
        db.session.commit()
        return bid


def test_waec_comparison_measures_significance_and_ranks(app):
    bid = _seed(app)
    with app.app_context():
        from utils import exam_yoy
        t = exam_yoy.build('waec', bid)
        assert t['years'] == [Y1, Y2, Y3] and t['year_b'] == Y3 and t['year_a'] == Y2
        rows = {r['key']: r for r in t['compare']}
        bm = rows['benchmark_rate']
        assert (bm['a'], bm['b']) == (50.0, 90.0) and bm['delta'] == 40.0
        assert bm['mood'] == 'good' and bm['sig']['real'] and bm['rank'] == 1 and bm['of'] == 3
        assert bm['streak'] == 2 and bm['best'] == (Y3, 90.0)
        assert rows['fail_rate']['mood'] == 'good'              # fewer F9s is better
        assert rows['near_rate']['good_up'] is False
        assert t['verdict']['tone'] == 'good' and t['verdict']['head']['key'] == 'benchmark_rate'
        assert t['projection'] and t['projection']['next_year'] == Y3 + 1
        # Subjects: Physics went from mostly F9 to mostly credit.
        phys = next(s for s in t['subjects'] if s['subject'] == 'Physics')
        assert phys['delta'] > 0 and phys['sig'] == 'Real change' and phys['trend'] == 'rising'
        assert [h[0] for h in phys['history']] == [Y1, Y2, Y3]
        assert any('Physics' in w[2] for w in t['wins'])
        # Grade shift covers every WAEC grade.
        assert [g['grade'] for g in t['grade_shift']] == ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']

        # Compare against an earlier year, and the reverse direction is ignored (A must be < B).
        t2 = exam_yoy.build('waec', bid, year_a=Y1, year_b=Y3)
        assert t2['year_a'] == Y1
        bm2 = next(r for r in t2['compare'] if r['key'] == 'benchmark_rate')
        assert (bm2['a'], bm2['b']) == (33.3, 90.0)


def test_declines_land_in_the_action_list(app):
    bid = _seed(app)
    with app.app_context():
        from utils import exam_yoy
        t = exam_yoy.build('waec', bid, year_a=Y3, year_b=Y2)        # A later than B → previous year used
        assert (t['year_a'], t['year_b']) == (Y1, Y2)
        # Make Y3 → a weaker Y4 to get a real decline.
        sids = [s.id for s in Student.query.filter_by(branch_id=bid).limit(30)]
        for i, sid in enumerate(sids):
            for subj, g in (GOOD if i < 5 else WEAK).items():
                db.session.add(WAECResult(student_id=sid, exam_year=Y3 + 1, subject=subj, grade=g))
        db.session.commit()
        t = exam_yoy.build('waec', bid)
        assert t['year_b'] == Y3 + 1 and t['verdict']['tone'] == 'bad'
        head = t['actions'][0]
        assert head[0] == 'bad' and head[2].startswith('Met the benchmark fell')


def test_jamb_and_neco_and_small_cohorts(app):
    bid = _seed(app, NECOResult)
    with app.app_context():
        from utils import exam_yoy
        keys = [k for k, _l, _g in exam_yoy.available(bid)]
        assert keys[:2] == ['neco', 'jamb']                       # only exams with results here
        j = exam_yoy.build('jamb', bid)
        rows = {r['key']: r for r in j['compare']}
        assert rows['avg_score']['delta'] == 40.0 and rows['avg_score']['sig']['real']
        assert rows['above_200']['b'] > rows['above_200']['a']
        assert [g['grade'] for g in j['grade_shift']] == ['<160', '160–199', '200–249', '250–299', '300+']
        assert any(s['subject'] == 'Use of English' for s in j['subjects'])
        n = exam_yoy.build('neco', bid)
        assert n['label'] == 'NECO' and n['verdict']['tone'] == 'good'
        # A tiny branch: verdict says too few to judge, no projection.
        bid2 = _branch()
        for yr in (Y1, Y2, Y3):
            sid = _pupil(bid2, 'Male')
            for subj, g in GOOD.items():
                db.session.add(WAECResult(student_id=sid, exam_year=yr, subject=subj, grade=g))
        db.session.commit()
        s = exam_yoy.build('waec', bid2)
        assert s['verdict']['small'] and s['verdict']['title'].startswith('Too few') and s['projection'] is None


def test_page_renders_every_exam_and_phone_safe_markup(app):
    _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    html = c.get('/results/analytics/trends').get_data(as_text=True)
    assert 'Exam Trends' in html and 'Year-over-year comparison' in html and 'What it means' in html
    for k in ('waec', 'jamb'):
        r = c.get('/results/analytics/trends?exam=%s&a=%d&b=%d' % (k, Y1, Y3))
        assert r.status_code == 200, k
        body = r.get_data(as_text=True)
        assert 'Real change' in body or 'Could be chance' in body
    assert c.get('/results/analytics/trends?exam=nonsense&a=x').status_code == 200


def test_mock_waec_and_mock_jamb_sittings(app):
    import datetime as dt
    from models import AcademicSession
    from models.mock_waec import MockWAECExam, MockWAECResult
    from models.mock_jamb import MockJAMBExam, MockJAMBResult
    with app.app_context():
        bid = _branch()
        old = AcademicSession(name='YoY-OLD ' + uuid.uuid4().hex[:4], is_active=False)
        new = AcademicSession(name='YoY-NEW ' + uuid.uuid4().hex[:4], is_active=False)
        db.session.add_all([old, new]); db.session.flush()
        sittings = [(old, 1, dt.date(2390, 3, 1), 8), (new, 1, dt.date(2391, 3, 1), 12), (new, 2, dt.date(2391, 5, 1), 24)]
        pupils = [_pupil(bid, 'Female' if i % 2 else 'Male') for i in range(30)]
        ids = []
        for sess, num, day, n_good in sittings:
            mw = MockWAECExam(name='Mock WAEC %d' % num, exam_number=num, session_id=sess.id, exam_date=day)
            mj = MockJAMBExam(name='Mock %d' % num, exam_number=num, session_id=sess.id, exam_date=day)
            db.session.add_all([mw, mj]); db.session.flush()
            ids.append(mw.id)
            for i, sid in enumerate(pupils):
                for subj, g in (GOOD if i < n_good else WEAK).items():
                    db.session.add(MockWAECResult(student_id=sid, mock_exam_id=mw.id, subject=subj, score=60, grade=g))
                db.session.add(MockWAECResult(student_id=sid, mock_exam_id=mw.id, subject='Economics', score=None,
                                              grade=None, is_absent=True))            # absent papers are ignored
                db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=mj.id, total_score=140 + n_good * 5 + i,
                                              subject1='Use of English', subject1_score=55))
        db.session.commit()
        from utils import exam_yoy
        keys = [k for k, _l, _g in exam_yoy.available(bid)]
        assert 'mock_waec' in keys and 'mock_jamb' in keys
        t = exam_yoy.build('mock_waec', bid)
        assert t['mock'] and t['period'] == 'sitting' and t['years'] == ids          # date order
        assert t['year_b'] == ids[2] and t['year_a'] == ids[1]
        assert t['labels'][ids[2]].endswith('Mock WAEC 2') and t['projection'] is None
        bm = next(r for r in t['compare'] if r['key'] == 'benchmark_rate')
        assert (bm['a'], bm['b']) == (40.0, 80.0) and bm['sig']['real']
        assert t['verdict']['title'] == 'A stronger sitting'
        assert 'Economics' not in [s['subject'] for s in t['subjects']]
        assert [lab for lab, _y in t['quick']][:2] == ['previous sitting', 'first on record']
        # Mock 1 this session vs Mock 1 last session.
        t1 = exam_yoy.build('mock_waec', bid, year_b=ids[1])
        assert ('same mock last session', ids[0]) in t1['quick']
        j = exam_yoy.build('mock_jamb', bid)
        assert j['kind'] == 'jamb' and len(j['years']) == 3
        avg = next(r for r in j['compare'] if r['key'] == 'avg_score')
        assert avg['delta'] == 60.0 and avg['sig']['real']
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    for k in ('mock_waec', 'mock_jamb'):
        body = c.get('/results/analytics/trends?exam=' + k).get_data(as_text=True)
        assert 'Mock-to-mock comparison' in body and 'All 3 sittings' in body, k
