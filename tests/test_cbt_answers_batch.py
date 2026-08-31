"""CBT scalable autosave: the batch endpoint saves many answers in one request."""
from models import db, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer, Student
import routes.cbt as cbt


def _exam(app, sid='BATCH1'):
    with app.app_context():
        s = Student(student_id=sid, first_name='B', surname='Atch',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        e = CBTExam(title='Batch Exam'); db.session.add(e); db.session.flush()
        q1 = CBTQuestion(exam_id=e.id, question_text='q1', correct_option='A', marks=1)
        q2 = CBTQuestion(exam_id=e.id, question_text='q2', correct_option='B', marks=1)
        db.session.add_all([q1, q2]); db.session.flush()
        db.session.add(CBTAttempt(exam_id=e.id, student_id=s.id, status='In progress'))
        db.session.commit()
        return e.id, s.id, q1.id, q2.id


def test_answers_batch_saves_all_in_one_request(app):
    eid, sid, q1, q2 = _exam(app, sid="BATCH1")
    c = app.test_client()
    with c.session_transaction() as sess:
        sess[cbt.PORTAL_KEY] = sid
        sess['_csrf_token'] = 'tok'
    r = c.post(f'/exam/{eid}/answers',
               data={f'q_{q1}': 'A', f'q_{q2}': 'C', '_csrf_token': 'tok'})
    assert r.status_code == 200 and r.get_json()['saved'] == 2
    with app.app_context():
        att = CBTAttempt.query.filter_by(exam_id=eid, student_id=sid).first()
        ans = {a.question_id: a for a in att.answers}
        assert ans[q1].selected_option == 'A' and ans[q1].is_correct is True
        assert ans[q2].selected_option == 'C' and ans[q2].is_correct is False


def test_answers_batch_rejected_after_submit(app):
    eid, sid, q1, q2 = _exam(app, sid="BATCHSUB")
    with app.app_context():
        att = CBTAttempt.query.filter_by(exam_id=eid, student_id=sid).first()
        att.status = 'Submitted'; db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess[cbt.PORTAL_KEY] = sid
        sess['_csrf_token'] = 'tok'
    r = c.post(f'/exam/{eid}/answers', data={f'q_{q1}': 'A', '_csrf_token': 'tok'})
    assert r.status_code == 400
