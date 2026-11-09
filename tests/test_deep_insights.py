"""Deeper exam insights: shared rules, sample-size safeguards and every
analysis on /results/analytics/insights against a seeded year with known
answers; plus freezing a year and the automatic cache refresh."""
import datetime
import itertools
import uuid

import pytest

from config import Config
from models import (db, Student, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Attendance, Week, WAECResult,
                    Subject, ClassSubject, TermResult)
from tests.conftest import login_token

_SEQ = itertools.count()
YEAR = 2071


# --------------------------------------------------------------------------- #
# Pure units
# --------------------------------------------------------------------------- #
def test_five_credit_rule_and_near_credit():
    from utils.exam_rules import five_credit_status
    ok = five_credit_status({'English Language': 'C6', 'Mathematics': 'B3', 'Biology': 'C4',
                             'Physics': 'C5', 'Economics': 'A1'})
    assert ok['meets'] and ok['credits'] == 5
    no_eng = five_credit_status({'English Language': 'F9', 'Mathematics': 'B3', 'Biology': 'C4',
                                 'Physics': 'C5', 'Economics': 'A1', 'Chemistry': 'C4'})
    assert not no_eng['meets'] and not no_eng['near']
    near = five_credit_status({'English Language': 'D7', 'Mathematics': 'B3', 'Biology': 'C4',
                               'Physics': 'C5', 'Economics': 'A1'})
    assert not near['meets'] and near['near']             # one D7 (English) short
    assert five_credit_status({'Eng': 'C6', 'Maths': 'C6', 'Bio': 'C6', 'Chem': 'C6', 'Phy': 'C6'})['meets']


def test_shared_grade_rules_are_used_everywhere():
    from utils import exam_rules as R
    from utils.analytics_service import AcademicAnalytics
    import models.mock_waec as mw
    import utils.admission as adm
    assert set(AcademicAnalytics.PASS_GRADES) == set(R.CREDIT_GRADES) == set(mw.PASS_GRADES) == set(adm.PASS_GRADES)
    assert set(AcademicAnalytics.DISTINCTION_GRADES) == set(R.DISTINCTION_GRADES)


def test_stats_safeguards():
    from utils.stats_guard import wilson, rate, projection, gap_verdict, correlation_ci
    lo, hi = wilson(8, 10)
    assert 44 < lo < 50 and 94 < hi < 98                  # 80% of 10 is very uncertain
    assert rate(3, 4)['small'] and not rate(30, 40)['small']
    p = projection([(2020, 180), (2021, 190)])
    assert p['confidence'] == 'low' and p['low'] < p['projected'] < p['high']
    assert projection([(2020, 100), (2021, 300)])['projected'] <= 300 + 25   # yearly change capped
    assert gap_verdict(9, 10, 1, 10)['real'] and not gap_verdict(3, 5, 2, 5)['real']
    lo, hi = correlation_ci(0.5, 50)
    assert lo < 0.5 < hi


# --------------------------------------------------------------------------- #
# Seeded year
# --------------------------------------------------------------------------- #
@pytest.fixture(scope='module')
def seeded(app):
    """20 SSS3 students in session 2070/2071: internal scores that track WAEC,
    a mock WAEC one grade harsher in Mathematics, BECE results, attendance."""
    from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
    from models.models_school_exams import SchoolExamResult
    G = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name='%d/%d' % (YEAR - 1, YEAR), is_active=False)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term')
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=12)
        db.session.add(cls); db.session.flush()
        arms = [ClassArm(name='IXA%d' % next(_SEQ), is_active=True), ClassArm(name='IXB%d' % next(_SEQ), is_active=True)]
        db.session.add_all(arms); db.session.flush()
        caas = [ClassArmAssignment(class_id=cls.id, arm_id=a.id, term_id=term.id, branch_id=bid) for a in arms]
        db.session.add_all(caas); db.session.flush()
        subs = {}
        for name in ('Mathematics', 'English Language', 'Biology', 'Physics', 'Economics'):
            s = Subject.query.filter_by(name=name).first() or Subject(name=name)
            db.session.add(s); db.session.flush()
            subs[name] = ClassSubject(subject_id=s.id, class_id=cls.id, arm_id=None, term_id=term.id,
                                      teacher_name='Mr %s' % name.split()[0])
            db.session.add(subs[name])
        db.session.flush()
        d0 = datetime.date(YEAR - 1, 10, 6)
        wk = Week(term_id=term.id, week_number=1, start_date=d0, end_date=d0 + datetime.timedelta(days=4))
        db.session.add(wk); db.session.flush()
        mock = MockWAECExam(name='IX mock', exam_number=1, session_id=sess.id, exam_date=datetime.date(YEAR, 2, 1),
                            branch_id=bid)
        db.session.add(mock); db.session.flush()
        ids = []
        for i in range(20):
            st = Student(student_id='IX' + uuid.uuid4().hex[:6], first_name='Ix%02d' % i, surname='Insight',
                         gender='Male' if i % 2 else 'Female', branch_id=bid, is_active=True,
                         boarding_status='Boarding' if i < 10 else 'Day')
            db.session.add(st); db.session.flush()
            ids.append(st.id)
            en = StudentEnrollment(student_id=st.id, class_arm_assignment_id=caas[i % 2].id, is_active=True)
            db.session.add(en); db.session.flush()
            # Ability: strong (i small) → weak (i large).
            g_idx = min(8, i // 3)
            for name, cs in subs.items():
                grade = G[g_idx]
                if name == 'Economics' and i in (12, 13, 14):        # one D7 short of 5 credits
                    grade = 'C6'
                if name == 'English Language' and i in (12, 13, 14):
                    grade = 'D7'
                db.session.add(WAECResult(student_id=st.id, exam_year=YEAR, subject=name, grade=grade))
                db.session.add(TermResult(student_id=st.id, term_id=term.id, class_subject_id=cs.id,
                                          total_score=95 - i * 3))
                mock_score = 85 - i * 3 - (12 if name == 'Mathematics' else 0)
                db.session.add(MockWAECResult(student_id=st.id, mock_exam_id=mock.id, subject=name,
                                              score=max(0, mock_score), grade=waec_grade_from_score(max(0, mock_score))))
            db.session.add(SchoolExamResult(student_id=st.id, level='jss3', body='state', exam_year=YEAR - 3,
                                            subject='Mathematics', grade='A' if i < 7 else 'C' if i < 14 else 'F'))
            # Attendance: the strongest students attend every day, the weakest half the time.
            for k in range(5):
                present = i < 10 or k % 2 == 0
                db.session.add(Attendance(enrollment_id=en.id, week_id=wk.id, date=d0 + datetime.timedelta(days=k),
                                          morning_present=present, afternoon_present=present))
        db.session.commit()
        return {'ids': ids, 'bid': bid}


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_value_added_near_credit_and_mock_accuracy(app, seeded):
    from utils import exam_deep_insights as DI
    with app.app_context():
        va = DI.value_added(YEAR)
        assert va['enough'] and va['n'] >= 100 and va['r'] > 0.8
        assert {s['name'] for s in va['subjects']} >= {'Mathematics', 'English Language'}
        assert any('Mr Mathematics' in t['name'] for t in va['teachers'])

        nc = DI.near_credit(YEAR)
        assert nc['students_total'] >= 3
        assert any(s['subject'] == 'English Language' and s['d7'] >= 3 for s in nc['subjects'])

        mk = DI.mock_accuracy(YEAR)
        maths = next(s for s in mk['subjects'] if s['subject'] == 'Mathematics')
        bio = next(s for s in mk['subjects'] if s['subject'] == 'Biology')
        assert maths['bias'] > bio['bias']                 # the Maths mock was marked harsher
        assert maths['verdict'] == 'Mock harder than WAEC'


def test_bece_fairness_attendance_readiness(app, seeded):
    from utils import exam_deep_insights as DI
    with app.app_context():
        b = DI.bece_to_waec(YEAR)
        top = next(x for x in b['bands'] if x['band'].startswith('Top'))
        bottom = next(x for x in b['bands'] if x['band'].startswith('Bottom'))
        assert top['avg_points'] > bottom['avg_points'] and b['r'] is not None

        dims = {d['dimension']: d for d in DI.fairness(YEAR)}
        boarding = {r['group']: r for r in dims['Boarding']['rows']}
        assert boarding['Boarding']['rate']['pct'] > boarding['Day']['rate']['pct']
        assert 'Gender' in dims and 'Class arm' in dims

        att = DI.attendance_bands(YEAR)
        assert att['n'] >= 20 and att['threshold'] and att['threshold']['above']['pct'] > att['threshold']['below']['pct']

        pts = DI.readiness_over_time(YEAR)
        kinds = [p['kind'] for p in pts]
        assert 'Mock WAEC' in kinds and 'WAEC' in kinds

        combos = DI.combinations(YEAR)
        assert combos['students'] >= 20

        teach = DI.teachers([YEAR])
        assert any(t['teacher'] == 'Mr Mathematics' for t in teach)


def test_insights_page_freeze_and_health(app, seeded):
    c = _admin(app)
    html = c.get('/results/analytics/insights?year=%d' % YEAR).get_data(as_text=True)
    for sec in ('Data health', 'Value added', 'One grade short', 'Mock → real accuracy', 'BECE (JSS3)',
                'Subject choices', 'Teachers across the years', 'Fairness', 'Attendance and results',
                'Intake cohorts', 'Readiness through the session', 'Weakest topics', 'At-risk SSS3'):
        assert sec in html, sec
    assert 'Mr Mathematics' in html and 'small group' in html
    hub = c.get('/results/analytics?year=%d' % YEAR).get_data(as_text=True)
    assert 'Deeper insights' in hub

    tok = html.split('name="_csrf_token" value="')[1].split('"')[0]
    r = c.post('/results/analytics/insights/freeze', data={'_csrf_token': tok, 'year': YEAR}, follow_redirects=True)
    assert 'frozen' in r.get_data(as_text=True)
    with app.app_context():
        from utils.insights_snapshots import frozen
        f = frozen(YEAR, None)
        assert f and f['waec_students'] >= 20
    r = c.post('/results/analytics/insights/freeze', data={'_csrf_token': tok, 'year': YEAR, 'action': 'unfreeze'},
               follow_redirects=True)
    with app.app_context():
        from utils.insights_snapshots import frozen
        assert frozen(YEAR, None) is None


def test_data_health_flags_graduate_on_register_and_spellings(app, seeded, monkeypatch):
    from utils import data_health
    import utils.helpers as H
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='%d/%d' % (YEAR - 1, YEAR)).first()
        term = Term.query.filter_by(session_id=sess.id).first()
        monkeypatch.setattr(H, 'get_active_term', lambda: term)     # treat the seeded term as current
        bid = Branch.get_default().id
        old = AcademicSession(name='IX OLD %d' % next(_SEQ), is_active=False)
        db.session.add(old); db.session.flush()
        cls = SchoolClass(name='IXHCLS%d' % next(_SEQ), level=11)
        arm = ClassArm(name='IXH%d' % next(_SEQ), is_active=True)
        db.session.add_all([cls, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        g = Student(student_id='IXG' + uuid.uuid4().hex[:5], first_name='Old', surname='Graduate', gender='Male',
                    branch_id=bid, is_active=True, is_graduated=True, graduation_session_id=old.id)
        db.session.add(g); db.session.flush()
        db.session.add(StudentEnrollment(student_id=g.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.add(WAECResult(student_id=seeded['ids'][0], exam_year=YEAR - 30, subject='Maths', grade='C6'))
        db.session.add(WAECResult(student_id=seeded['ids'][0], exam_year=YEAR - 30, subject='Mathematics ', grade='C6'))
        db.session.commit()
        assert any('Old Graduate' in x or 'Graduate Old' in x for x in data_health.graduates_on_registers())
        assert any('Maths' in x and 'Mathematics' in x for x in data_health.subject_spellings())


def test_cache_is_dropped_when_results_change(app, seeded):
    from models.analytics_models import AnalyticsCache
    with app.app_context():
        AnalyticsCache.set('exam_hub:waec:%d:all' % YEAR, {'x': 1}, 3600)
        assert AnalyticsCache.get('exam_hub:waec:%d:all' % YEAR) is not None
        db.session.add(WAECResult(student_id=seeded['ids'][1], exam_year=YEAR, subject='Geography', grade='B2'))
        db.session.commit()
        db.session.expire_all()
        assert AnalyticsCache.get('exam_hub:waec:%d:all' % YEAR) is None


def test_neco_insights(app, seeded):
    """The same analyses run on NECO results (board switch on the page)."""
    from models import NECOResult
    from utils import exam_deep_insights as DI
    with app.app_context():
        for sid in seeded['ids']:
            for subj in ('Mathematics', 'English Language', 'Biology', 'Physics', 'Economics'):
                db.session.add(NECOResult(student_id=sid, exam_year=YEAR, subject=subj,
                                          grade='C4' if seeded['ids'].index(sid) < 12 else 'D7'))
        db.session.commit()
        nc = DI.near_credit(YEAR, model=NECOResult)
        assert any(s['subject'] == 'Mathematics' and s['d7'] == 8 for s in nc['subjects'])
        pts = DI.readiness_over_time(YEAR, model=NECOResult)
        assert any(p['kind'] == 'NECO' and p['label'] == 'NECO SSCE %d' % YEAR for p in pts)
        assert DI.value_added(YEAR, model=NECOResult)['enough']
    c = _admin(app)
    html = c.get('/results/analytics/insights?board=neco&year=%d' % YEAR).get_data(as_text=True)
    assert 'Deeper Insights — NECO %d' % YEAR in html and 'BECE (JSS3) → NECO' in html
    assert 'NECO SSCE %d' % YEAR in html and 'Freeze' not in html      # freezing is WAEC-only
    assert 'class="on">NECO' in html.replace("class=\"on\"", 'class="on"') or '>NECO</a>' in html
    hub = c.get('/results/analytics?year=%d' % YEAR).get_data(as_text=True)
    assert 'NECO insights' in hub


def test_jss3_and_basic_insights(app, seeded):
    """JSS3 BECE and Basic 5/6 Common Entrance run through the same page with
    their own grading; WAEC-only sections (mocks, at-risk, topics) are hidden."""
    from models.models_school_exams import SchoolExamResult
    from utils import exam_deep_insights as DI, insight_exams as IE
    with app.app_context():
        for i, sid in enumerate(seeded['ids']):
            for subj in ('Mathematics', 'English Studies', 'Basic Science', 'Business Studies',
                         'Basic Technology', 'Social Studies', 'French'):
                g = 'A' if i < 8 else 'C' if i < 14 else 'P'
                if subj == 'English Studies' and i in (9, 10):
                    g = 'P'                                  # one band short of the benchmark
                db.session.add(SchoolExamResult(student_id=sid, level='jss3', body='federal', exam_year=YEAR,
                                                subject=subj, grade=g))
            db.session.add(SchoolExamResult(student_id=sid, level='basic6', body='state', exam_year=YEAR - 3,
                                            subject='Mathematics', grade='A' if i < 8 else 'D' if i < 14 else 'F'))
        db.session.commit()
        X = IE.get('jss3')
        assert not X.has_mocks and X.earlier and X.years_from_jss1 == 2
        nc = DI.near_credit(YEAR, model=X)
        assert nc['near_label'] == 'P' and nc['students_total'] == 2       # P in English, 6 other credits
        assert DI.value_added(YEAR, model=X)['enough']
        e = DI.bece_to_waec(YEAR, model=X)
        top = next(b for b in e['bands'] if b['band'].startswith('Top'))
        assert top['five_credit']['pct'] == 100.0
        assert DI.mock_accuracy(YEAR, model=X)['applies'] is False
        pts = DI.readiness_over_time(YEAR, model=X)
        assert [p['kind'] for p in pts] == [X.name]
        B = IE.get('basic6')
        assert B.years() and B.years()[0] == YEAR - 3 and B.years_from_jss1 is None
        assert ('jss3', 'JSS3 BECE') in IE.choices()
    c = _admin(app)
    html = c.get('/results/analytics/insights?board=jss3&year=%d' % YEAR).get_data(as_text=True)
    assert 'Deeper Insights — BECE %d' % YEAR in html and 'Common Entrance (Basic 5/6) → BECE' in html
    assert 'Mock → real accuracy' not in html and 'At-risk SSS3' not in html and 'Weakest topics' not in html
    assert 'Ps by subject' in html and 'JSS3 BECE</a>' in html
    html = c.get('/results/analytics/insights?board=basic6&year=%d' % (YEAR - 3)).get_data(as_text=True)
    assert 'Common Entrance %d' % (YEAR - 3) in html and 'Intake cohorts' not in html
    dash = c.get('/jss3-exams/?body=federal&year=%d' % YEAR).get_data(as_text=True)
    assert 'board=jss3' in dash and 'Deeper insights' in dash


def _admin_client(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _form_token(c, url):
    import re
    html = c.get(url).get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ''


def test_not_the_same_person_hides_a_duplicate_pair_until_reset(app):
    """'Not the same person' stops a pair being suggested (and counted in Data
    health); resetting brings it back."""
    from utils.student_merge import find_groups, clear_not_duplicates
    tag = 'Dupx' + uuid.uuid4().hex[:4]
    with app.app_context():
        bid = Branch.get_default().id
        a = Student(student_id='DPA' + uuid.uuid4().hex[:5], first_name='Chinedu', middle_name='Paul',
                    surname=tag, gender='Male', branch_id=bid, is_active=True)
        b = Student(student_id='DPB' + uuid.uuid4().hex[:5], first_name='Chinedu', surname=tag,
                    gender='Male', branch_id=bid, is_active=True)
        db.session.add_all([a, b]); db.session.commit()
        ids = sorted([a.id, b.id])

    def flagged():
        from flask import session
        with app.test_request_context():
            session['role'] = 'super_admin'
            return any(sorted(m['student'].id for m in g['members']) == ids for g in find_groups())
    assert flagged()
    c = _admin_client(app)
    tok = _form_token(c, '/students/duplicates')
    r = c.post('/students/duplicates/not-same', data={'_csrf_token': tok, 'group': '%d-%d' % tuple(ids)})
    assert r.status_code in (302, 303)
    assert not flagged()
    with app.test_request_context():
        from flask import session
        session['role'] = 'super_admin'
        from utils import data_health
        assert not any(tag in x for x in data_health.duplicate_pupils())
    page = c.get('/students/duplicates').get_data(as_text=True)
    assert 'Not the same person' in page and 'already marked as different' in page
    r = c.post('/students/duplicates/not-same/reset', data={'_csrf_token': tok})
    assert r.status_code in (302, 303)
    assert flagged()
    with app.app_context():
        clear_not_duplicates()


def test_take_graduates_off_current_registers(app, seeded, monkeypatch):
    """The Data-health button closes graduates' leftover current-term
    enrolments (kept, just inactive) so they stop being flagged."""
    import utils.helpers as H
    from utils import data_health
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='%d/%d' % (YEAR - 1, YEAR)).first()
        term = Term.query.filter_by(session_id=sess.id).first()
        term_id = term.id
    monkeypatch.setattr(H, 'get_active_term', lambda: db.session.get(Term, term_id))
    with app.app_context():
        bid = Branch.get_default().id
        old = AcademicSession(name='IX OLD2 %d' % next(_SEQ), is_active=False)
        db.session.add(old); db.session.flush()
        cls = SchoolClass(name='IXGCLS%d' % next(_SEQ), level=11)
        arm = ClassArm(name='IXG%d' % next(_SEQ), is_active=True)
        db.session.add_all([cls, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term_id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        g = Student(student_id='IXO' + uuid.uuid4().hex[:5], first_name='Leftover', surname='Grad', gender='Female',
                    branch_id=bid, is_active=True, is_graduated=True, graduation_session_id=old.id)
        db.session.add(g); db.session.flush()
        en = StudentEnrollment(student_id=g.id, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(en); db.session.commit()
        en_id = en.id
        assert any('Leftover' in x for x in data_health.graduates_on_registers())
    c = _admin_client(app)
    tok = _form_token(c, '/students/duplicates')
    r = c.post('/students/graduates/close-enrolments', data={'_csrf_token': tok})
    assert r.status_code in (302, 303)
    with app.app_context():
        e = db.session.get(StudentEnrollment, en_id)
        assert e is not None and e.is_active is False          # closed, not deleted
        assert not any('Leftover' in x for x in data_health.graduates_on_registers())
