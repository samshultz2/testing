"""Mock JAMB portal: the candidate's record (history, best, latest, change,
weakest subject) shown on the landing page."""
import uuid
from datetime import date

from models import db, Student, AcademicSession
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from routes.mock_jamb import _portal_record


def test_record_orders_history_and_summarises(app):
    with app.app_context():
        st = Student(student_id='PR' + uuid.uuid4().hex[:6].upper(), first_name='Rec', surname='Ord',
                     gender='Male', is_active=True)
        sess = AcademicSession.query.first() or AcademicSession(name='PR 1', is_active=True)
        db.session.add_all([st, sess]); db.session.flush()
        e1 = MockJAMBExam(name='PR A', exam_number=1, session_id=sess.id, exam_date=date(2090, 1, 5))
        e2 = MockJAMBExam(name='PR B', exam_number=2, session_id=sess.id, exam_date=date(2090, 3, 5))
        db.session.add_all([e1, e2]); db.session.flush()
        db.session.add_all([
            MockJAMBResult(student_id=st.id, mock_exam_id=e2.id, total_score=210, subject1='Use of English',
                           subject1_score=60, subject2='Physics', subject2_score=40),
            MockJAMBResult(student_id=st.id, mock_exam_id=e1.id, total_score=180, subject1='Use of English',
                           subject1_score=50)])
        db.session.commit()
        r = _portal_record(st)
        assert [x['total'] for x in r['items']] == [180, 210]          # oldest first
        assert r['last']['total'] == 210 and r['best']['total'] == 210 and r['change'] == 30
        assert r['weakest']['name'] == 'Physics'
        assert r['top'] >= 240
        assert _portal_record(Student(id=-1)) is None
