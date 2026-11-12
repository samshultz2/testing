"""Mock WAEC → term results: a /100 mock score becomes CBT + Theory on the
school results — out of 70 with a mid-term / practical, 80 without — in whole
numbers within each column's maximum."""
import uuid
from datetime import date

from config import Config
from models import db, Student, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, waec_grade_from_score
from tests.conftest import login_token, auth_csrf, enroll_sss3
from utils.mock_to_term import split


def test_split_rules():
    assert split(64, [30, 40]) == (45, [19, 26])      # 64% of 70
    assert split(64, [30, 50]) == (51, [19, 32])      # 64% of 80
    assert split(100, [30, 40]) == (70, [30, 40])
    assert split(0, [30, 50]) == (0, [0, 0])
    for maxes in ([30, 40], [30, 50], [20, 40], [25, 45], [30, 0]):
        for s in range(101):
            total, parts = split(s, maxes)
            assert sum(parts) == total <= sum(maxes)
            assert all(0 <= p <= m and p == int(p) for p, m in zip(parts, maxes))


def _types():
    from models import AssessmentType
    def get(short, name, mx, order):
        at = AssessmentType.query.filter_by(short_name=short).first()
        if not at:
            at = AssessmentType(name=name, short_name=short, max_score=mx, order=order, is_active=True)
            db.session.add(at); db.session.flush()
        return at
    return get('MID', 'Midterm', 10, 3), get('CBT', 'CBT', 30, 5), get('EXAM', 'Theory', 40, 6)


def test_send_mock_scores_to_term_results(app):
    from models import (Subject, ClassSubject, StudentEnrollment, ClassArmAssignment, StudentScore,
                        SubjectAssessmentOverride)
    from utils.mock_to_term import _exam_columns
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        s = Student(student_id='MT' + tag, first_name='Ada', surname='Term' + tag, gender='Female')
        db.session.add(s); db.session.commit(); sid = s.id
    with app.app_context():
        from models import Term, SchoolClass, ClassArm
        mid, cbt, exam_t = _types()
        # Its own session with a first and a third term (mocks only go into 1st / 2nd).
        sess = AcademicSession(name='MTT ' + tag); db.session.add(sess); db.session.flush()
        t1 = Term(session_id=sess.id, term_number=1, name='First ' + tag)
        t3 = Term(session_id=sess.id, term_number=3, name='Third ' + tag)
        db.session.add_all([t1, t3]); db.session.flush()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=12)
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add_all([sss3, arm]); db.session.flush()
        asg = ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=t1.id)
        db.session.add(asg); db.session.flush()
        db.session.add(StudentEnrollment(student_id=sid, class_arm_assignment_id=asg.id, is_active=True))
        db.session.commit()
        term_id, session_id, third_id = t1.id, sess.id, t3.id
        prac = Subject(name='Physics ' + tag, short_name='P' + tag)
        nopr = Subject(name='Literature ' + tag, short_name='L' + tag)
        db.session.add_all([prac, nopr]); db.session.flush()
        # Physics keeps the mid-term column; Literature drops it and Theory is worth 10 more.
        db.session.add(SubjectAssessmentOverride(subject_id=nopr.id, assessment_type_id=mid.id, max_score=0))
        # Whatever Theory column the feature picks, Literature's is worth 10 more.
        th_at, th_p = _exam_columns(prac, term_id)[-1]
        db.session.add(SubjectAssessmentOverride(subject_id=nopr.id, assessment_type_id=th_at.id, max_score=th_p + 10))
        for sub in (prac, nopr):
            db.session.add(ClassSubject(subject_id=sub.id, class_id=asg.class_id, term_id=term_id, is_active=True))
        ex = MockWAECExam(name='Mock T', exam_number=77, session_id=session_id, exam_date=date(2026, 2, 1))
        db.session.add(ex); db.session.flush()
        for subj, sc in ((prac.name, 64), (nopr.name, 64), ('Geography ' + tag, 50)):
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ex.id, subject=subj, score=sc,
                                          grade=waec_grade_from_score(sc)))
        db.session.commit()
        ex_id, prac_id, nopr_id = ex.id, prac.id, nopr.id
        cols = {sub_id: [(at.id, mx) for at, mx in _exam_columns(db.session.get(Subject, sub_id), term_id)]
                for sub_id in (prac_id, nopr_id)}

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    html = c.get(f'/mock-waec/exam/{ex_id}/to-term-results?term_id={term_id}').get_data(as_text=True)
    assert 'Send to term results' in html and 'Subject not set for class' in html
    total_p = sum(mx for _, mx in cols[prac_id]); total_n = sum(mx for _, mx in cols[nopr_id])
    assert total_n == total_p + 10                      # e.g. 70 vs 80
    assert f'out of {total_p}' in html and f'out of {total_n}' in html

    tok = auth_csrf(c)
    # Third term (WAEC time) is not offered and can't be written to.
    assert f'value="{third_id}"' not in html
    r = c.post(f'/mock-waec/exam/{ex_id}/to-term-results', data={'_csrf_token': tok, 'term_id': third_id})
    assert r.status_code == 302
    with app.app_context():
        assert not StudentScore.query.filter_by(student_id=sid).count()
    r = c.post(f'/mock-waec/exam/{ex_id}/to-term-results', data={'_csrf_token': tok, 'term_id': term_id})
    assert r.status_code == 302

    def stored(sub_id):
        with app.app_context():
            cs = ClassSubject.query.filter_by(subject_id=sub_id, term_id=term_id).first()
            return {s.assessment_type_id: s.score for s in StudentScore.query.filter_by(
                student_id=sid, class_subject_id=cs.id)}
    for sub_id in (prac_id, nopr_id):
        want_total, parts = split(64, [mx for _, mx in cols[sub_id]])
        got = stored(sub_id)
        assert [got[at_id] for at_id, _ in cols[sub_id]] == parts
        assert sum(parts) == want_total and all(float(p).is_integer() for p in parts)

    # Change the mock score: without "replace" existing scores are kept, with it they're updated.
    with app.app_context():
        MockWAECResult.query.filter_by(mock_exam_id=ex_id, subject=db.session.get(Subject, prac_id).name).first().score = 90
        db.session.commit()
    before = stored(prac_id)
    c.post(f'/mock-waec/exam/{ex_id}/to-term-results', data={'_csrf_token': tok, 'term_id': term_id})
    assert stored(prac_id) == before
    c.post(f'/mock-waec/exam/{ex_id}/to-term-results', data={'_csrf_token': tok, 'term_id': term_id, 'replace': '1'})
    _, parts = split(90, [mx for _, mx in cols[prac_id]])
    assert [stored(prac_id)[at_id] for at_id, _ in cols[prac_id]] == parts
