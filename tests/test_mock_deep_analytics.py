"""Deep analytics for a single Mock JAMB / Mock WAEC exam — the engine's
per-subject / per-teacher / per-arm rollups, and the routes + exports."""
import uuid
from datetime import date

from config import Config
from models import db, Student, AcademicSession, Term, SchoolClass, ClassArm, Subject
from models.models.subjects import ClassSubject
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from tests.conftest import login_token, enroll_sss3

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _session_term(app):
    """Active session + term + SSS3 class, with a Maths & English teacher assigned."""
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='DA 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True))
        db.session.add(term); db.session.flush()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=6)
        db.session.add(sss3); db.session.flush()
        # Subjects + teacher attribution on the SSS3 class for this term.
        for subj_name, teacher in [('Mathematics', 'Mr Bello'), ('English Language', 'Mrs Coker')]:
            subj = Subject.query.filter_by(name=subj_name).first() or Subject(name=subj_name, is_active=True)
            db.session.add(subj); db.session.flush()
            if not ClassSubject.query.filter_by(subject_id=subj.id, class_id=sss3.id, term_id=term.id).first():
                db.session.add(ClassSubject(subject_id=subj.id, class_id=sss3.id, term_id=term.id,
                                            teacher_name=teacher, is_active=True))
        db.session.commit()
        return ssn.id


def _fresh_session_term(app):
    """A brand-new (inactive) session + term + SSS3 teacher assignments, isolated
    from other tests' mocks so trends aggregate only this test's exams."""
    with app.app_context():
        _SEQ[0] += 1
        ssn = AcademicSession(name=f'TR{_SEQ[0]} 25/26', is_active=False)
        db.session.add(ssn); db.session.flush()
        term = Term(session_id=ssn.id, term_number=1, name=f'T{_SEQ[0]}', is_active=False)
        db.session.add(term); db.session.flush()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=6)
        db.session.add(sss3); db.session.flush()
        for subj_name, teacher in [('Mathematics', 'Mr Bello'), ('English Language', 'Mrs Coker')]:
            subj = Subject.query.filter_by(name=subj_name).first() or Subject(name=subj_name, is_active=True)
            db.session.add(subj); db.session.flush()
            db.session.add(ClassSubject(subject_id=subj.id, class_id=sss3.id, term_id=term.id,
                                        teacher_name=teacher, is_active=True))
        db.session.commit()
        return ssn.id


def _students(app, n):
    ids = []
    with app.app_context():
        for _ in range(n):
            _SEQ[0] += 1
            s = Student(student_id=f'DA{_SEQ[0]:04d}', first_name='Cand', surname=f'N{_SEQ[0]}',
                        gender='Male' if _SEQ[0] % 2 else 'Female')
            db.session.add(s); db.session.flush()
            ids.append(s.id)
        db.session.commit()
    for sid in ids:
        enroll_sss3(app, sid)
    return ids


def _jamb_exam(app, session_id, num=None):
    with app.app_context():
        _SEQ[0] += 1
        n = num if num is not None else (_SEQ[0] % 4) + 1
        ex = MockJAMBExam(name=f'Mock J {_SEQ[0]}', exam_number=n,
                          session_id=session_id, exam_date=date(2025, 3, n))
        db.session.add(ex); db.session.commit()
        return ex.id


def _jamb_result(app, exam_id, student_id, maths, eng, phy, chem):
    with app.app_context():
        r = MockJAMBResult(student_id=student_id, mock_exam_id=exam_id,
                           total_score=maths + eng + phy + chem,
                           subject1='Mathematics', subject1_score=maths,
                           subject2='English Language', subject2_score=eng,
                           subject3='Physics', subject3_score=phy,
                           subject4='Chemistry', subject4_score=chem)
        db.session.add(r); db.session.commit()


def _seed_jamb(app):
    ssid = _session_term(app)
    exam_id = _jamb_exam(app, ssid)
    ids = _students(app, 4)
    # Maths strong, English weak (so teacher attribution separates them).
    _jamb_result(app, exam_id, ids[0], 85, 40, 70, 60)   # total 255
    _jamb_result(app, exam_id, ids[1], 80, 35, 55, 50)   # total 220
    _jamb_result(app, exam_id, ids[2], 75, 30, 45, 40)   # total 190
    _jamb_result(app, exam_id, ids[3], 70, 25, 30, 20)   # total 145 (critical)
    return exam_id, ids


def test_jamb_deep_engine(app):
    from utils.mock_deep_analytics import deep_analytics
    exam_id, ids = _seed_jamb(app)
    with app.app_context():
        d = deep_analytics('jamb', exam_id)
        assert d['meta']['students'] == 4
        assert not d['meta']['empty']
        assert len(d['kpis']) == 4
        # subject league: English (all sub-50) is weaker than Mathematics (all >=70)
        by = {s['subject']: s for s in d['subjects']}
        assert by['Mathematics']['pass_rate'] == 100.0
        assert by['English Language']['pass_rate'] == 0.0
        assert d['subjects'][0]['subject'] == 'English Language'   # weakest first
        assert by['Mathematics']['band'] == 'strong'
        # teacher attribution: Maths -> Mr Bello, English -> Mrs Coker
        tby = {t['teacher']: t for t in d['teachers']}
        assert 'Mr Bello' in tby and 'Mrs Coker' in tby
        assert tby['Mr Bello']['pass_rate'] == 100.0
        assert tby['Mrs Coker']['pass_rate'] == 0.0
        assert tby['Mrs Coker']['flag'] in ('watch', 'support', 'insufficient')
        # arms present, segments flag the 145 candidate as critical
        assert d['arms'] and d['arms'][0]['students'] >= 1
        assert any(x['metric'] == '145' for x in d['segments']['critical'])
        # recommendations bucketed
        assert set(d['recommendations']) == {'students', 'teachers', 'management'}
        assert d['recommendations']['management']


def test_jamb_deep_route_and_exports(app):
    exam_id, ids = _seed_jamb(app)
    c = _admin(app)
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep')
    assert r.status_code == 200 and b'Deep Analytics' in r.data
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep/export?format=excel')
    assert r.status_code == 200 and r.get_data()[:2] == b'PK'
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep/export?format=pdf')
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep/export?format=image')
    assert r.status_code == 200 and r.get_data()[:8] == b'\x89PNG\r\n\x1a\n'


# ---------------------------------------------------------------------------
# WAEC
# ---------------------------------------------------------------------------

def _waec_exam(app, session_id, num=None):
    with app.app_context():
        _SEQ[0] += 1
        n = num if num is not None else (_SEQ[0] % 4) + 1
        ex = MockWAECExam(name=f'Mock W {_SEQ[0]}', exam_number=n,
                          session_id=session_id, exam_date=date(2025, 4, n))
        db.session.add(ex); db.session.commit()
        return ex.id


def _waec_row(app, exam_id, student_id, subject, score):
    with app.app_context():
        db.session.add(MockWAECResult(student_id=student_id, mock_exam_id=exam_id,
                                      subject=subject, score=score,
                                      grade=waec_grade_from_score(score)))
        db.session.commit()


def _seed_waec(app):
    ssid = _session_term(app)
    exam_id = _waec_exam(app, ssid)
    ids = _students(app, 4)
    # Maths strong (credits), English weak (fails) -> teacher separation.
    for i, sid in enumerate(ids):
        _waec_row(app, exam_id, sid, 'Mathematics', 75 - i * 3)     # 75,72,69,66 all credit
        _waec_row(app, exam_id, sid, 'English Language', 42 - i * 3)  # 42,39,36,33 all fail
        _waec_row(app, exam_id, sid, 'Biology', 60 - i * 5)
    return exam_id, ids


def test_waec_deep_engine(app):
    from utils.mock_deep_analytics import deep_analytics
    exam_id, ids = _seed_waec(app)
    with app.app_context():
        d = deep_analytics('waec', exam_id)
        assert d['meta']['students'] == 4
        by = {s['subject']: s for s in d['subjects']}
        assert by['Mathematics']['pass_rate'] == 100.0
        assert by['English Language']['pass_rate'] == 0.0
        tby = {t['teacher']: t for t in d['teachers']}
        assert 'Mr Bello' in tby and 'Mrs Coker' in tby
        assert tby['Mr Bello']['pass_rate'] == 100.0
        assert tby['Mrs Coker']['pass_rate'] == 0.0
        # WAEC KPIs include avg credits + core credit rates (5 cards)
        assert len(d['kpis']) == 5
        # grade distribution present
        assert d['distribution'] and any(g['grade'] == 'F9' for g in d['distribution'])
        # everyone is missing a core credit (English) -> at_risk / critical, none honour
        assert d['segments']['honour'] == []


def test_waec_deep_route_and_exports(app):
    exam_id, ids = _seed_waec(app)
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/deep')
    assert r.status_code == 200 and b'Deep Analytics' in r.data
    r = c.get(f'/mock-waec/exam/{exam_id}/deep/export?format=excel')
    assert r.status_code == 200 and r.get_data()[:2] == b'PK'
    r = c.get(f'/mock-waec/exam/{exam_id}/deep/export?format=pdf')
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'


def test_jamb_trends_across_mocks(app):
    """Two mocks in one session -> a progress trajectory with subject trends."""
    from utils.mock_deep_analytics import deep_trends
    ssid = _fresh_session_term(app)
    # Mock 1: weaker; Mock 2: stronger — cohort should trend up.
    ex1 = _jamb_exam(app, ssid, num=1)
    ids = _students(app, 3)
    _jamb_result(app, ex1, ids[0], 60, 30, 40, 40)   # 170
    _jamb_result(app, ex1, ids[1], 55, 28, 35, 32)   # 150
    _jamb_result(app, ex1, ids[2], 50, 25, 30, 25)   # 130
    ex2 = _jamb_exam(app, ssid, num=2)
    _jamb_result(app, ex2, ids[0], 80, 55, 60, 60)   # 255
    _jamb_result(app, ex2, ids[1], 75, 50, 55, 52)   # 232
    _jamb_result(app, ex2, ids[2], 70, 45, 50, 45)   # 210
    with app.app_context():
        d = deep_trends('jamb', session_id=ssid)
        assert not d['meta'].get('insufficient')
        assert d['meta']['periods_count'] == 2
        assert d['headline']['primary_label'] == 'Mean score'
        # cohort mean rose from mock 1 to mock 2
        assert d['headline']['primary_direction'] == 'up'
        assert d['headline']['primary_delta'] > 0
        # English rose from 0% pass (mock 1) to a real pass rate (mock 2)
        sm = {s['name']: s for s in d['subject_trends']}
        assert sm['English Language']['direction'] == 'up'
        # improving movers non-empty, cohort series has 2 points
        assert d['movers']['improving']
        assert len(d['cohort']) == 2
    c = _admin(app)
    r = c.get(f'/mock-jamb/trends?session_id={ssid}')
    assert r.status_code == 200 and b'Progress Trends' in r.data
    r = c.get(f'/mock-jamb/trends/export?format=excel&session_id={ssid}')
    assert r.status_code == 200 and r.get_data()[:2] == b'PK'
    r = c.get(f'/mock-jamb/trends/export?format=pdf&session_id={ssid}')
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'


def test_waec_trends_and_all_sessions(app):
    from utils.mock_deep_analytics import deep_trends
    ssid = _fresh_session_term(app)
    ex1 = _waec_exam(app, ssid, num=1)
    ids = _students(app, 3)
    for i, sid in enumerate(ids):
        _waec_row(app, ex1, sid, 'Mathematics', 50 + i)     # around credit line
        _waec_row(app, ex1, sid, 'English Language', 40 + i)
    ex2 = _waec_exam(app, ssid, num=2)
    for i, sid in enumerate(ids):
        _waec_row(app, ex2, sid, 'Mathematics', 70 + i)     # improved
        _waec_row(app, ex2, sid, 'English Language', 60 + i)
    with app.app_context():
        d = deep_trends('waec', session_id=ssid)
        assert d['meta']['periods_count'] == 2
        assert d['headline']['primary_label'] == 'Avg credits'
        assert d['headline']['primary_direction'] == 'up'
        # all-sessions scope also works (may be one session here, still valid data)
        d2 = deep_trends('waec', session_id=None)
        assert d2['meta']['periods_count'] >= 2
    c = _admin(app)
    r = c.get(f'/mock-waec/trends?session_id={ssid}')
    assert r.status_code == 200 and b'Progress Trends' in r.data
    r = c.get('/mock-waec/trends?scope=all')
    assert r.status_code == 200
    r = c.get(f'/mock-waec/trends/export?format=pdf&session_id={ssid}')
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'


def test_trends_insufficient(app):
    """A single mock -> insufficient, renders guidance not a crash."""
    from utils.mock_deep_analytics import deep_trends
    ssid = _fresh_session_term(app)
    ex1 = _jamb_exam(app, ssid, num=1)
    ids = _students(app, 2)
    _jamb_result(app, ex1, ids[0], 60, 40, 50, 50)
    with app.app_context():
        d = deep_trends('jamb', session_id=ssid)
        assert d['meta'].get('insufficient') is True
    c = _admin(app)
    r = c.get(f'/mock-jamb/trends?session_id={ssid}')
    assert r.status_code == 200
    r = c.get(f'/mock-jamb/trends/export?format=pdf&session_id={ssid}', follow_redirects=True)
    assert r.status_code == 200


def test_deep_empty_exam(app):
    """An exam with no results renders the empty state, not a crash."""
    from utils.mock_deep_analytics import deep_analytics
    ssid = _session_term(app)
    exam_id = _jamb_exam(app, ssid)
    with app.app_context():
        d = deep_analytics('jamb', exam_id)
        assert d['meta']['empty'] is True
    c = _admin(app)
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep')
    assert r.status_code == 200
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep/export?format=pdf', follow_redirects=True)
    assert r.status_code == 200   # redirected to the page with a flash, no crash
