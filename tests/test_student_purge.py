"""Permanently deleting a soft-deleted student (/students/<id>/purge) must
actually delete "the student and their related records" as its own docstring
promises — not crash with a NotNullViolation because some child table's
Student relationship lacks a delete cascade.

Regression coverage for a real production bug: a student with a
StudentRiskAssessment row failed to purge because that relationship (and
several siblings with the same shape: AcademicPrediction, MockJAMBResult,
MockWAECResult, PromotionRecord, StudentScore, TermResult, TermSummary) had
no cascade, so SQLAlchemy tried to null out the NOT NULL student_id on
delete instead of deleting the row.
"""
from datetime import date

from config import Config
from models import (
    db, Student, Branch, AcademicSession, Term, SchoolClass, ClassArm,
    ClassArmAssignment, StudentEnrollment, Subject, ClassSubject, AssessmentType,
)
from models.analytics_models import StudentRiskAssessment, AcademicPrediction
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from models.mock_waec import MockWAECExam, MockWAECResult
from models.models.promotion import PromotionRecord
from models.models.scores import StudentScore, TermResult, TermSummary
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _seed_student_with_every_related_record(app, tag):
    """A single soft-deleted student with one row in every table whose
    Student relationship this fix touched, plus the FK scaffolding each of
    those rows needs. Returns the student's id."""
    with app.app_context():
        bid = Branch.get_default().id

        ssn = AcademicSession(name=f'ZzPurgeSsn{tag}', is_active=False)
        db.session.add(ssn); db.session.flush()
        term = Term(session_id=ssn.id, term_number=1, name=f'ZzPurgeTerm{tag}', is_active=False)
        db.session.add(term); db.session.flush()

        sc1 = SchoolClass(name=f'ZzPurgeC1{tag}', level=1)
        sc2 = SchoolClass(name=f'ZzPurgeC2{tag}', level=2)
        arm = ClassArm(name=f'ZzPurgeArm{tag}', is_active=True)
        db.session.add_all([sc1, sc2, arm]); db.session.flush()
        caa = ClassArmAssignment(class_id=sc1.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()

        subj = Subject(name=f'ZzPurgeSubj{tag}')
        db.session.add(subj); db.session.flush()
        csub = ClassSubject(subject_id=subj.id, class_id=sc1.id, term_id=term.id)
        atype = AssessmentType(name=f'ZzPurgeAT{tag}', max_score=100)
        db.session.add_all([csub, atype]); db.session.flush()

        jexam = MockJAMBExam(name=f'ZzPurgeJExam{tag}', exam_number=1, session_id=ssn.id,
                             exam_date=date.today(), branch_id=bid)
        wexam = MockWAECExam(name=f'ZzPurgeWExam{tag}', exam_number=1, session_id=ssn.id,
                             exam_date=date.today(), branch_id=bid)
        db.session.add_all([jexam, wexam]); db.session.flush()

        student = Student(student_id=Student.generate_student_id(), surname='ZzPurgeTest',
                          first_name=tag, gender='Male', is_active=False, branch_id=bid)
        db.session.add(student); db.session.flush()
        sid = student.id

        enr = StudentEnrollment(student_id=sid, class_arm_assignment_id=caa.id, is_active=True)
        db.session.add(enr); db.session.flush()

        db.session.add(StudentRiskAssessment(student_id=sid, overall_risk_score=10,
                                             risk_level='GREEN'))
        db.session.add(AcademicPrediction(student_id=sid, prediction_type='JAMB_SCORE'))
        db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=jexam.id, total_score=250))
        db.session.add(MockWAECResult(student_id=sid, mock_exam_id=wexam.id, subject='Maths', score=80))
        db.session.add(PromotionRecord(student_id=sid, from_session_id=ssn.id, to_session_id=ssn.id,
                                       from_class_id=sc1.id, to_class_id=sc2.id, status='promoted'))
        db.session.add(StudentScore(student_id=sid, class_subject_id=csub.id,
                                    assessment_type_id=atype.id, score=45))
        db.session.add(TermResult(student_id=sid, term_id=term.id, class_subject_id=csub.id,
                                  total_score=78))
        db.session.add(TermSummary(student_id=sid, term_id=term.id, enrollment_id=enr.id))
        db.session.commit()
        return sid


def test_purge_deletes_student_with_risk_assessment(app):
    """The exact reported bug: a student with a StudentRiskAssessment row
    could not be permanently deleted."""
    with app.app_context():
        student = Student(student_id=Student.generate_student_id(), surname='ZzPurgeRisk',
                          first_name='Solo', gender='Male', is_active=False)
        db.session.add(student); db.session.flush()
        sid = student.id
        db.session.add(StudentRiskAssessment(student_id=sid, overall_risk_score=50,
                                             risk_level='AMBER'))
        db.session.commit()

    c = _admin(app)
    r = c.post(f'/students/{sid}/purge', data={'_csrf_token': _csrf(c)})
    assert r.status_code in (302, 200)
    with app.app_context():
        assert Student.query.get(sid) is None
        assert StudentRiskAssessment.query.filter_by(student_id=sid).count() == 0


def test_purge_deletes_student_and_every_related_record(app):
    sid = _seed_student_with_every_related_record(app, 'A')

    c = _admin(app)
    r = c.post(f'/students/{sid}/purge', data={'_csrf_token': _csrf(c)})
    assert r.status_code in (302, 200)

    with app.app_context():
        assert Student.query.get(sid) is None
        assert StudentRiskAssessment.query.filter_by(student_id=sid).count() == 0
        assert AcademicPrediction.query.filter_by(student_id=sid).count() == 0
        assert MockJAMBResult.query.filter_by(student_id=sid).count() == 0
        assert MockWAECResult.query.filter_by(student_id=sid).count() == 0
        assert PromotionRecord.query.filter_by(student_id=sid).count() == 0
        assert StudentScore.query.filter_by(student_id=sid).count() == 0
        assert TermResult.query.filter_by(student_id=sid).count() == 0
        assert TermSummary.query.filter_by(student_id=sid).count() == 0
        assert StudentEnrollment.query.filter_by(student_id=sid).count() == 0


def test_bulk_purge_deletes_students_with_related_records(app):
    sid1 = _seed_student_with_every_related_record(app, 'B')
    sid2 = _seed_student_with_every_related_record(app, 'C')

    c = _admin(app)
    r = c.post('/students/bulk-purge', data={'_csrf_token': _csrf(c),
                                             'student_ids': [str(sid1), str(sid2)]})
    assert r.status_code in (302, 200)
    with app.app_context():
        assert Student.query.get(sid1) is None
        assert Student.query.get(sid2) is None
