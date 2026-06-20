"""The contributions service batches per-student totals into one query, matching
the old per-student SUM results exactly."""
from datetime import date
from models import db, Student, ContributionPayment, AcademicSession
from utils.services.contributions import paid_by_student


def _goc_session(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(name='SVC-Sess').first()
        if not s:
            s = AcademicSession(name='SVC-Sess'); db.session.add(s); db.session.commit()
        return s.id


def _student(app, sid):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='S', surname=sid, gender='Male',
                        is_active=True)
            db.session.add(s); db.session.commit()
        return s.id


def test_paid_by_student_batches_totals(app):
    sess = _goc_session(app)
    a = _student(app, 'SVC_A'); b = _student(app, 'SVC_B'); c = _student(app, 'SVC_C')
    with app.app_context():
        for sid, amt in [(a, 500), (a, 250), (b, 1000)]:
            db.session.add(ContributionPayment(session_id=sess, student_id=sid,
                           amount=amt, payment_date=date.today()))
        db.session.commit()
    with app.app_context():
        m = paid_by_student(sess, [a, b, c])
        assert m.get(a) == 750.0      # 500 + 250, summed in one query
        assert m.get(b) == 1000.0
        assert c not in m             # no payments → absent (callers use .get(id, 0))
        # the per-student SUM equivalent matches
        from sqlalchemy import func
        for sid in (a, b):
            one = db.session.query(func.sum(ContributionPayment.amount)).filter_by(
                session_id=sess, student_id=sid).scalar()
            assert float(one) == m[sid]
