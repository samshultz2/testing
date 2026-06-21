"""Projected admission readiness combining Mock WAEC + Mock JAMB."""
import uuid
from datetime import date

from models import db, AcademicSession, Student
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from utils import exam_insights as EI


def _session(app):
    with app.app_context():
        s = AcademicSession(name='EI ' + uuid.uuid4().hex[:5], is_active=False)
        db.session.add(s); db.session.commit()
        return s.id


def _student(app, jamb_subjects=None):
    with app.app_context():
        s = Student(student_id='EI' + uuid.uuid4().hex[:7].upper(), first_name='E',
                    surname='Insight', gender='Male', jamb_subjects=jamb_subjects)
        db.session.add(s); db.session.commit()
        return s.id


def _waec_exam(app, ssid, n):
    with app.app_context():
        ex = MockWAECExam(name=f'MW{n}', exam_number=n, session_id=ssid,
                          exam_date=date(2025, 1, n))
        db.session.add(ex); db.session.commit()
        return ex.id


def _jamb_exam(app, ssid, n):
    with app.app_context():
        ex = MockJAMBExam(name=f'MJ{n}', exam_number=n, session_id=ssid,
                          exam_date=date(2025, 1, n))
        db.session.add(ex); db.session.commit()
        return ex.id


def _add_waec(app, sid, exam_id, scores):
    with app.app_context():
        for subj, sc in scores.items():
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id, subject=subj,
                                          score=sc, grade=waec_grade_from_score(sc)))
        db.session.commit()


def _add_jamb(app, sid, exam_id, total):
    with app.app_context():
        db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=exam_id, total_score=total,
                                      subject1='English Language', subject1_score=total // 4))
        db.session.commit()


FIVE_CORE = {'Mathematics': 70, 'English Language': 62, 'Biology': 60,
             'Chemistry': 58, 'Physics': 55, 'Economics': 30}
FOUR_NO_ENGLISH = {'Mathematics': 70, 'Biology': 60, 'Chemistry': 58,
                   'Physics': 55, 'English Language': 30}
TWO_CREDITS = {'Mathematics': 60, 'English Language': 55, 'Biology': 30, 'Physics': 20}


def _ready_setup(app):
    """A session with shared mock exams and a fixture builder."""
    ssid = _session(app)
    we = _waec_exam(app, ssid, 1)
    je1, je2 = _jamb_exam(app, ssid, 1), _jamb_exam(app, ssid, 2)
    return ssid, we, je1, je2


def test_projected_waec_from_mock_flags_core(app):
    ssid, we, *_ = _ready_setup(app)
    sid = _student(app)
    _add_waec(app, sid, we, FOUR_NO_ENGLISH)
    with app.app_context():
        st = db.session.get(Student, sid)
        w = EI.projected_waec(st, ssid)
        assert w['source'] == 'mock'
        assert w['missing_core'] == ['English Language']
        assert w['meets_ssc'] is False
        assert 'Mathematics' in w['credited_subjects']


def test_readiness_ready(app):
    ssid, we, je1, je2 = _ready_setup(app)
    sid = _student(app)
    _add_waec(app, sid, we, FIVE_CORE)
    _add_jamb(app, sid, je1, 220); _add_jamb(app, sid, je2, 230)
    with app.app_context():
        r = EI.admission_readiness(db.session.get(Student, sid), ssid)
        assert r['status'] == 'READY'
        assert r['blockers'] == []
        assert r['waec']['meets_ssc'] and r['jamb']['score'] >= EI.JAMB_BASELINE
        # eligible for at least the low-cutoff science categories
        assert any('Sciences' in c or 'Education' in c for c in r['eligible_categories'])


def test_readiness_conditional_low_jamb(app):
    ssid, we, je1, je2 = _ready_setup(app)
    sid = _student(app)
    _add_waec(app, sid, we, FIVE_CORE)
    _add_jamb(app, sid, je1, 160); _add_jamb(app, sid, je2, 160)
    with app.app_context():
        r = EI.admission_readiness(db.session.get(Student, sid), ssid)
        assert r['status'] == 'CONDITIONAL'
        assert any('below 180' in b for b in r['blockers'])


def test_readiness_at_risk_missing_core(app):
    ssid, we, je1, je2 = _ready_setup(app)
    sid = _student(app)
    _add_waec(app, sid, we, FOUR_NO_ENGLISH)
    _add_jamb(app, sid, je1, 160); _add_jamb(app, sid, je2, 160)
    with app.app_context():
        r = EI.admission_readiness(db.session.get(Student, sid), ssid)
        assert r['status'] == 'AT_RISK'
        assert any('English Language' in b for b in r['blockers'])


def test_readiness_no_data(app):
    ssid, *_ = _ready_setup(app)
    sid = _student(app)
    with app.app_context():
        r = EI.admission_readiness(db.session.get(Student, sid), ssid)
        assert r['status'] == 'NO_DATA'


def test_post_utme_aggregate_math(app):
    agg = EI.post_utme_aggregate(320, ['A1', 'A1', 'A1', 'A1', 'A1'])
    assert agg['utme_component'] == 40.0       # 320/400*50
    assert agg['olevel_component'] == 50.0     # 5*6/30*50
    assert agg['aggregate'] == 90.0


def test_jamb_combo_detects_wrong_combination(app):
    # A student aiming science subjects but no Maths fits Medicine, not Engineering.
    sid = _student(app, jamb_subjects='English Language, Biology, Chemistry, Physics')
    with app.app_context():
        res = EI.jamb_subject_combo_check(db.session.get(Student, sid))
        fits = {c['name']: c['fits'] for c in res['categories']}
        assert fits['Medicine & Health Sciences'] is True
        assert fits['Engineering & Technology'] is False    # missing Mathematics


def test_cohort_funnel_counts(app):
    ssid, we, je1, je2 = _ready_setup(app)
    ready = _student(app); cond = _student(app); risk = _student(app); nodata = _student(app)
    _add_waec(app, ready, we, FIVE_CORE); _add_jamb(app, ready, je1, 220); _add_jamb(app, ready, je2, 230)
    _add_waec(app, cond, we, FIVE_CORE); _add_jamb(app, cond, je1, 160); _add_jamb(app, cond, je2, 160)
    _add_waec(app, risk, we, FOUR_NO_ENGLISH); _add_jamb(app, risk, je1, 160); _add_jamb(app, risk, je2, 160)
    with app.app_context():
        students = [db.session.get(Student, s) for s in (ready, cond, risk, nodata)]
        f = EI.cohort_readiness(students, ssid)
        assert f['total'] == 4
        assert f['counts']['READY'] == 1
        assert f['counts']['CONDITIONAL'] == 1
        assert f['counts']['AT_RISK'] == 1
        assert f['counts']['NO_DATA'] == 1
        assert f['projected_5_incl_core'] == 2     # ready + conditional
        assert f['projected_both'] == 1            # only ready clears both


def test_cohort_readiness_query_count_is_bounded(app):
    """The funnel must run a fixed number of queries regardless of cohort size."""
    from sqlalchemy import event
    from models import db

    def build(n):
        ssid, we, je1, je2 = _ready_setup(app)
        ids = []
        for _ in range(n):
            sid = _student(app)
            _add_waec(app, sid, we, FIVE_CORE)
            _add_jamb(app, sid, je1, 210); _add_jamb(app, sid, je2, 220)
            ids.append(sid)
        return ssid, ids

    def count(ssid, ids):
        with app.app_context():
            students = [db.session.get(Student, i) for i in ids]
            c = {'q': 0}
            eng = db.engine

            def before(*a, **k):
                c['q'] += 1
            event.listen(eng, 'before_cursor_execute', before)
            try:
                EI.cohort_readiness(students, ssid)
            finally:
                event.remove(eng, 'before_cursor_execute', before)
            return c['q']

    s1, ids1 = build(2)
    s2, ids2 = build(6)
    assert count(s1, ids1) == count(s2, ids2)     # constant in cohort size
