"""SSS3 term averages divide by the WAEC subjects on the student's profile, and
deleted students drop off a term's class lists — except for sessions that had
ended before they were deleted."""
import uuid
from datetime import date, datetime

from config import Config
from models import (db, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    ClassSubject, Subject, AssessmentType, Student, StudentEnrollment,
                    StudentScore, Branch)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _class(app, class_name, sess_end):
    """A session (ending ``sess_end``) + term + arm assignment of ``class_name``
    with three subjects and one assessment type."""
    tag = uuid.uuid4().hex[:6]
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name='T' + tag, start_date=date(sess_end.year - 1, 9, 1), end_date=sess_end)
        db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term', end_date=sess_end)
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.filter_by(name=class_name).first() or SchoolClass(name=class_name, level=6)
        db.session.add(sc); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        at = AssessmentType.query.filter_by(name='AV-Exam').first() or AssessmentType(
            name='AV-Exam', short_name='EX', max_score=100, order=95, is_active=True)
        db.session.add(at); db.session.flush()
        cs = []
        for n in ('English Language', 'Mathematics', 'Biology'):
            sub = Subject.query.filter_by(name=n).first() or Subject(name=n, is_active=True)
            db.session.add(sub); db.session.flush()
            c = ClassSubject(subject_id=sub.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
            db.session.add(c); db.session.flush(); cs.append(c.id)
        db.session.commit()
        return dict(term=term.id, asg=caa.id, cs=cs, at=at.id)


def _pupil(app, ids, name, scores, waec='', active=True, deleted_at=None):
    with app.app_context():
        s = Student(student_id=name + uuid.uuid4().hex[:4], first_name=name, surname='Zed', gender='Male',
                    is_active=active, deleted_at=deleted_at, waec_subjects=waec,
                    branch_id=Branch.get_default().id)
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=ids['asg'], is_active=True))
        for csid, v in zip(ids['cs'], scores):
            db.session.add(StudentScore(student_id=s.id, class_subject_id=csid,
                                        assessment_type_id=ids['at'], score=v))
        db.session.commit()
        return s.id


def _broadsheet(c, ids):
    return c.get(f"/subjects/broadsheet?term_id={ids['term']}&assignment_id={ids['asg']}",
                 headers={'Accept': 'application/json'}).get_json()


def test_sss3_average_uses_waec_subjects_on_profile(app):
    ids = _class(app, 'SSS3', date(2099, 7, 31))
    sid = _pupil(app, ids, 'Waec', [60, 80, 0], waec='English Language,Mathematics')
    plain = _pupil(app, ids, 'Plain', [60, 80, 0])                # no WAEC subjects saved
    j = _broadsheet(_admin(app), ids)
    by = {r['student_id']: r for r in j['rows']}
    assert by[sid]['average'] == 70.0                             # 140 / 2 WAEC subjects
    assert round(by[plain]['average'], 2) == 46.67                # 140 / 3 class subjects
    from utils.report_card import build_report_card, compute_term_summaries
    with app.app_context():
        _e, rc = build_report_card(sid, ids['term'])
        assert rc['average'] == 70.0
        cls = db.session.get(ClassArmAssignment, ids['asg']).class_id
        compute_term_summaries(ids['term'], cls)
        from models import TermSummary
        assert TermSummary.query.filter_by(student_id=sid, term_id=ids['term']).first().average_score == 70.0


def test_other_classes_still_average_over_class_subjects(app):
    ids = _class(app, 'JSS1', date(2099, 7, 31))
    sid = _pupil(app, ids, 'Junior', [60, 80, 0], waec='English Language,Mathematics')
    row = next(r for r in _broadsheet(_admin(app), ids)['rows'] if r['student_id'] == sid)
    assert round(row['average'], 2) == 46.67


def test_deleted_students_hidden_from_current_term(app):
    ids = _class(app, 'JSS1', date(2099, 7, 31))                  # session still running
    keep = _pupil(app, ids, 'Kept', [50, 50, 50])
    gone = _pupil(app, ids, 'Gone', [50, 50, 50], active=False, deleted_at=datetime(2026, 1, 5))
    c = _admin(app)
    sids = {r['student_id'] for r in _broadsheet(c, ids)['rows']}
    assert keep in sids and gone not in sids
    j = c.get(f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}"
              f"&class_subject_id={ids['cs'][0]}&assessment_type_id={ids['at']}",
              headers={'Accept': 'application/json'}).get_json()
    got = {s['id'] for s in j['students_data']}
    assert keep in got and gone not in got


def test_deleted_students_kept_for_sessions_before_deletion(app):
    ids = _class(app, 'JSS1', date(2024, 7, 31))                  # ended before the deletion
    before = _pupil(app, ids, 'Left', [50, 50, 50], active=False, deleted_at=datetime(2025, 3, 1))
    during = _pupil(app, ids, 'Mid', [50, 50, 50], active=False, deleted_at=datetime(2024, 2, 1))
    legacy = _pupil(app, ids, 'Old', [50, 50, 50], active=False)   # deleted before times were kept
    sids = {r['student_id'] for r in _broadsheet(_admin(app), ids)['rows']}
    assert before in sids and legacy in sids and during not in sids
