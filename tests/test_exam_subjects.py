"""External-exams unified subject scorecard + SSS3 teacher attribution."""
import uuid

from config import Config
from models import (db, Student, WAECResult, JAMBResult, SchoolClass, Subject,
                    ClassSubject, Term, AcademicSession)
from tests.conftest import login_token
from utils import exam_subjects as es


# --------------------------------------------------------------------------- #
# Pure scorecard
# --------------------------------------------------------------------------- #
_WAEC = {'subject_analysis': [
    {'subject': 'Mathematics', 'total_entries': 40, 'pass_rate': 48.0, 'a1_rate': 5.0},
    {'subject': 'English', 'total_entries': 40, 'pass_rate': 90.0, 'a1_rate': 30.0},
    {'subject': 'Biology', 'total_entries': 30, 'pass_rate': 66.0, 'a1_rate': 10.0}]}
_JAMB = {'subject_analysis': [
    {'subject': 'Mathematics', 'count': 20, 'mean_score': 38, 'above_50': 4},
    {'subject': 'English', 'count': 20, 'mean_score': 62, 'above_50': 16}]}


def test_scorecard_merges_waec_and_jamb_per_subject():
    rows = es.subject_scorecard(_WAEC, _JAMB, {'Mathematics': ['Mr A']})
    by = {r['subject']: r for r in rows}
    m = by['Mathematics']
    assert m['waec_pass_rate'] == 48.0 and m['jamb_mean'] == 38
    assert m['jamb_above_50_pct'] == 20.0            # 4/20
    assert m['teachers'] == ['Mr A']
    # a JAMB-only or WAEC-only subject still appears
    assert 'Biology' in by and by['Biology']['jamb_mean'] is None


def test_scorecard_flags_and_orders_worst_first():
    rows = es.subject_scorecard(_WAEC, _JAMB)
    # Mathematics (weak on both) must rank first; English (strong) last
    assert rows[0]['subject'] == 'Mathematics' and rows[0]['flag'] == 'weak'
    assert rows[-1]['subject'] == 'English' and rows[-1]['flag'] == 'strong'
    assert 'WAEC pass 48.0%' in rows[0]['reason']


def test_scorecard_summary_counts():
    rows = es.subject_scorecard(_WAEC, _JAMB, {'Mathematics': ['Mr A']})
    s = es.scorecard_summary(rows)
    assert s['total'] == 3 and s['weak'] == 1 and s['strong'] == 1
    assert s['with_teacher'] == 1


def test_scorecard_empty_when_no_subjects():
    assert es.subject_scorecard(None, None) == []
    assert es.scorecard_summary([]) == {'total': 0, 'weak': 0, 'watch': 0,
                                        'strong': 0, 'with_teacher': 0}


# --------------------------------------------------------------------------- #
# Teacher attribution (route helper)
# --------------------------------------------------------------------------- #
def test_sss3_subject_teachers_map(app):
    from routes.results import sss3_subject_teachers
    from utils.helpers import get_active_term, get_sss3_class
    uniq = 'Phys' + uuid.uuid4().hex[:5]
    with app.app_context():
        cls = get_sss3_class()
        if not cls:
            cls = SchoolClass(name='SSS3', level=6)
            db.session.add(cls); db.session.flush()
        term = get_active_term()
        if not term:
            sess = AcademicSession(name='SC-Sess ' + uniq)
            db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='SC-Term', is_active=True)
            db.session.add(term); db.session.flush()
        subj = Subject(name=uniq, is_active=True)
        db.session.add(subj); db.session.flush()
        db.session.add(ClassSubject(subject_id=subj.id, class_id=cls.id, term_id=term.id,
                                    teacher_name='Mr Attribution', is_active=True))
        db.session.commit()
        m = sss3_subject_teachers()
    assert m.get(uniq) == ['Mr Attribution']


def test_hub_renders_subject_scorecard(app):
    yr = 2079
    with app.app_context():
        s = Student(student_id='SC' + uuid.uuid4().hex[:7].upper(), first_name='Sub',
                    surname='Card', gender='Female')
        db.session.add(s); db.session.commit()
        db.session.add(JAMBResult(student_id=s.id, exam_year=yr, total_score=180,
                                  subject1='English', subject1_score=45,
                                  subject2='Mathematics', subject2_score=30))
        db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Mathematics', grade='D7'))
        db.session.commit()
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    html = c.get(f'/results/analytics?year={yr}').get_data(as_text=True)
    assert 'Subject Performance Scorecard' in html
    assert 'Teacher(s)' in html
