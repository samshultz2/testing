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


# ---------------------------------------------------------------------------
# Extended coverage: financial/audit/asset records are PRESERVED (detached,
# not deleted) on purge; pure student-activity records are CASCADE-DELETED.
# ---------------------------------------------------------------------------

def _seed_preserve_records(app, tag):
    """One row in each table that should survive a purge with its student_id
    set to NULL — financial records, audit trails, and independently-issued
    assets/applications. Returns (student_id, {table_name: row_id})."""
    from models import (FeePayment, FeeDiscount, AdditionalCharge, ContributionPayment,
                        Sale, Applicant, Message, MessageRecipient, ScratchCard,
                        ResultCheckLog, CBTLoginEvent)
    from models.models_graduate import (GraduateAudit, GraduateDocument, AlumniProfile,
                                        DocumentVerification, DocumentRequest)
    with app.app_context():
        bid = Branch.get_default().id
        ssn = AcademicSession(name=f'ZzPreserveSsn{tag}', is_active=False)
        db.session.add(ssn); db.session.flush()
        term = Term(session_id=ssn.id, term_number=1, name=f'ZzPreserveTerm{tag}', is_active=False)
        db.session.add(term); db.session.flush()

        student = Student(student_id=Student.generate_student_id(), surname='ZzPreserve',
                          first_name=tag, gender='Male', is_active=False, branch_id=bid)
        db.session.add(student); db.session.flush()
        sid = student.id

        fp = FeePayment(student_id=sid, term_id=term.id, amount=1000)
        fd = FeeDiscount(student_id=sid, term_id=term.id, amount=100)
        ac = AdditionalCharge(student_id=sid, term_id=term.id, amount=50)
        cp = ContributionPayment(student_id=sid, amount=200, payment_date=date.today())
        sale = Sale(student_id=sid)
        applicant = Applicant(first_name='Zz', surname='Applied', admitted_student_id=sid)
        msg = Message(body='Hello')
        db.session.add_all([fp, fd, ac, cp, sale, applicant, msg])
        db.session.flush()
        mr = MessageRecipient(message_id=msg.id, student_id=sid)
        sc = ScratchCard.generate_unique(student_id=sid)
        db.session.add_all([mr, sc])
        db.session.flush()
        rcl = ResultCheckLog(card_id=sc.id, student_id=sid)
        clev = CBTLoginEvent(student_id=sid)
        gaud = GraduateAudit(student_id=sid, field='graduate_status', new_value='Graduated')
        gdoc = GraduateDocument(student_id=sid, doc_type='transcript',
                                document_number=f'ZzDOC{tag}', verification_code=f'ZzVER{tag}')
        alum = AlumniProfile(student_id=sid, occupation='Engineer')
        dverif = DocumentVerification(student_id=sid, result='valid')
        dreq = DocumentRequest(student_id=sid, doc_type='transcript')
        db.session.add_all([rcl, clev, gaud, gdoc, alum, dverif, dreq])
        db.session.commit()

        ids = {'fee_payment': fp.id, 'fee_discount': fd.id, 'additional_charge': ac.id,
              'contribution_payment': cp.id, 'sale': sale.id, 'applicant': applicant.id,
              'message_recipient': mr.id, 'scratch_card': sc.id, 'result_check_log': rcl.id,
              'cbt_login_event': clev.id, 'graduate_audit': gaud.id, 'graduate_document': gdoc.id,
              'alumni_profile': alum.id, 'document_verification': dverif.id,
              'document_request': dreq.id}
        return sid, ids


def test_purge_preserves_financial_and_audit_records(app):
    """Financial payments, audit trails, and independently-issued
    assets/applications must survive a purge — only detached (student_id set
    to NULL), never deleted and never blocking the delete."""
    from models import (FeePayment, FeeDiscount, AdditionalCharge, ContributionPayment,
                        Sale, Applicant, MessageRecipient, ScratchCard, ResultCheckLog, CBTLoginEvent)
    from models.models_graduate import (GraduateAudit, GraduateDocument, AlumniProfile,
                                        DocumentVerification, DocumentRequest)
    sid, ids = _seed_preserve_records(app, 'P')

    c = _admin(app)
    r = c.post(f'/students/{sid}/purge', data={'_csrf_token': _csrf(c)})
    assert r.status_code in (302, 200)

    with app.app_context():
        assert Student.query.get(sid) is None

        assert FeePayment.query.get(ids['fee_payment']).student_id is None
        assert FeeDiscount.query.get(ids['fee_discount']).student_id is None
        assert AdditionalCharge.query.get(ids['additional_charge']).student_id is None
        assert ContributionPayment.query.get(ids['contribution_payment']).student_id is None
        assert Sale.query.get(ids['sale']).student_id is None
        assert Applicant.query.get(ids['applicant']).admitted_student_id is None
        assert MessageRecipient.query.get(ids['message_recipient']).student_id is None
        assert ScratchCard.query.get(ids['scratch_card']).student_id is None
        assert ResultCheckLog.query.get(ids['result_check_log']).student_id is None
        assert CBTLoginEvent.query.get(ids['cbt_login_event']).student_id is None
        assert GraduateAudit.query.get(ids['graduate_audit']).student_id is None
        assert GraduateDocument.query.get(ids['graduate_document']).student_id is None
        assert AlumniProfile.query.get(ids['alumni_profile']).student_id is None
        assert DocumentVerification.query.get(ids['document_verification']).student_id is None
        assert DocumentRequest.query.get(ids['document_request']).student_id is None


def test_purge_cascade_deletes_activity_records(app):
    """Pure student-activity data (exam attempts, live sessions, library
    loans/reservations, attendance interventions) has no independent meaning
    once the student is gone — it's deleted along with them."""
    from models import (CBTExam, CBTAttempt, CBTDeviceSession, Book, BookLoan,
                        BookReservation, AttendanceIntervention)
    from models.mock_jamb import MockJAMBExam, MockJAMBAttempt

    with app.app_context():
        bid = Branch.get_default().id
        ssn = AcademicSession(name='ZzCascadeSsn', is_active=False)
        db.session.add(ssn); db.session.flush()

        student = Student(student_id=Student.generate_student_id(), surname='ZzCascade',
                          first_name='Test', gender='Male', is_active=False, branch_id=bid)
        cbt_exam = CBTExam(title='ZzCBTExam')
        jexam = MockJAMBExam(name='ZzJExam', exam_number=1, session_id=ssn.id,
                             exam_date=date.today(), branch_id=bid)
        book = Book(title='ZzBook')
        db.session.add_all([student, cbt_exam, jexam, book]); db.session.flush()
        sid = student.id

        attempt = CBTAttempt(exam_id=cbt_exam.id, student_id=sid)
        dsess = CBTDeviceSession(student_id=sid, client_token='ZzTok')
        loan = BookLoan(book_id=book.id, student_id=sid)
        resv = BookReservation(book_id=book.id, student_id=sid)
        interv = AttendanceIntervention(student_id=sid)
        db.session.add_all([attempt, dsess, loan, resv, interv]); db.session.flush()
        jattempt = MockJAMBAttempt(mock_exam_id=jexam.id, student_id=sid)
        db.session.add(jattempt)
        db.session.commit()

        ids = {'attempt': attempt.id, 'dsess': dsess.id, 'loan': loan.id,
              'resv': resv.id, 'interv': interv.id, 'jattempt': jattempt.id}

    c = _admin(app)
    r = c.post(f'/students/{sid}/purge', data={'_csrf_token': _csrf(c)})
    assert r.status_code in (302, 200)

    with app.app_context():
        assert Student.query.get(sid) is None
        assert CBTAttempt.query.get(ids['attempt']) is None
        assert CBTDeviceSession.query.get(ids['dsess']) is None
        assert BookLoan.query.get(ids['loan']) is None
        assert BookReservation.query.get(ids['resv']) is None
        assert AttendanceIntervention.query.get(ids['interv']) is None
        assert MockJAMBAttempt.query.get(ids['jattempt']) is None
