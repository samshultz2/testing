"""Tier-2 polish: graduation review screen, receipt WhatsApp link, SMS balance."""
import re
from config import Config
from models import (db, Student, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def test_graduate_preview_lists_then_commits(app):
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='T2 24/25').first() or AcademicSession(name='T2 24/25')
        db.session.add(sess); db.session.flush()
        AcademicSession.query.update({AcademicSession.is_active: False}); sess.is_active = True
        term = Term.query.filter_by(session_id=sess.id, term_number=1).first() or Term(
            session_id=sess.id, term_number=1, name='First Term')
        db.session.add(term); db.session.flush()
        Term.query.update({Term.is_active: False}); term.is_active = True
        sc = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=6)
        db.session.add(sc); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=sc.id, arm_id=arm.id, term_id=term.id).first() or \
            ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id)
        db.session.add(caa); db.session.flush()
        s = Student.query.filter_by(student_id='GRADT2').first() or Student(
            student_id='GRADT2', first_name='Grad', surname='Two', gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        if not StudentEnrollment.query.filter_by(student_id=s.id, class_arm_assignment_id=caa.id).first():
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit(); sid = s.id

    c = _admin(app)
    body = c.get('/promotion/graduate-sss3/preview').get_data(as_text=True)
    # React shell: the student is in the embedded payload + the page marker is present.
    assert 'GRADT2' in body and '"page": "graduate_preview"' in body
    tok = re.search(r'name="csrf-token" content="([0-9a-f]+)"', body).group(1)
    c.post('/promotion/graduate-sss3', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Student, sid).is_graduated is True


def test_receipt_pdf_downloads(app):
    from datetime import date
    from models import FeePayment, AcademicSession, Term, Student
    with app.app_context():
        s = Student(student_id='RCPTDL', first_name='Pay', surname='Dl', gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        sess = AcademicSession.query.first() or AcademicSession(name='RD 24/25', is_active=True)
        db.session.add(sess); db.session.flush()
        term = Term.query.filter_by(session_id=sess.id, term_number=1).first() or Term(
            session_id=sess.id, term_number=1, name='First Term')
        db.session.add(term); db.session.flush()
        p = FeePayment(student_id=s.id, term_id=term.id, amount=1000, payment_date=date.today(),
                       method='Cash', receipt_no='DL-1')
        db.session.add(p); db.session.commit(); pid = p.id
    r = _admin(app).get(f'/finance/payments/{pid}/receipt.pdf')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    assert r.get_data()[:4] == b'%PDF'
