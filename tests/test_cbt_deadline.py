"""CBT exam-integrity regression: the SERVER deadline is authoritative on writes.

A candidate must not be able to keep saving or submitting answers after their
time (plus the offline grace) is genuinely up — the browser timer is only a
display. See routes.cbt._past_deadline and the answer/answers/submit guards.
"""
from datetime import timedelta
from models import db, CBTExam, CBTQuestion, CBTAttempt, CBTAnswer, Student
import routes.cbt as cbt
from utils import timeutil


def _expired_exam(app, sid):
    """An exam whose attempt started long enough ago to be past deadline+grace."""
    with app.app_context():
        s = Student(student_id=sid, first_name='D', surname='Line',
                    gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        e = CBTExam(title='Timed Exam', duration_minutes=30)
        db.session.add(e); db.session.flush()
        q1 = CBTQuestion(exam_id=e.id, question_text='q1', correct_option='A', marks=1)
        q2 = CBTQuestion(exam_id=e.id, question_text='q2', correct_option='B', marks=1)
        db.session.add_all([q1, q2]); db.session.flush()
        # Started 2 hours ago with a 30-min duration → well past deadline + grace.
        att = CBTAttempt(exam_id=e.id, student_id=s.id, status='In progress',
                         started_at=timeutil.now() - timedelta(hours=2))
        db.session.add(att); db.session.commit()
        return e.id, s.id, q1.id, q2.id


def _client(app, sid):
    c = app.test_client()
    with c.session_transaction() as sess:
        sess[cbt.PORTAL_KEY] = sid
        sess['_csrf_token'] = 'tok'
    return c


def test_answers_batch_rejected_after_deadline(app):
    eid, sid, q1, q2 = _expired_exam(app, 'DEADBATCH')
    c = _client(app, sid)
    r = c.post(f'/exam/{eid}/answers', data={f'q_{q1}': 'A', '_csrf_token': 'tok'})
    assert r.status_code == 409 and r.get_json().get('expired') is True
    with app.app_context():
        att = CBTAttempt.query.filter_by(exam_id=eid, student_id=sid).first()
        assert att.status == 'Submitted'                # auto-finalised, not left open
        # The late answer was NOT saved.
        assert CBTAnswer.query.filter_by(attempt_id=att.id, question_id=q1).first() is None


def test_single_answer_rejected_after_deadline(app):
    eid, sid, q1, q2 = _expired_exam(app, 'DEADONE')
    c = _client(app, sid)
    r = c.post(f'/exam/{eid}/answer', data={'question_id': q1, 'option': 'A', '_csrf_token': 'tok'})
    assert r.status_code == 409 and r.get_json().get('expired') is True


def test_submit_ignores_late_answers_after_deadline(app):
    eid, sid, q1, q2 = _expired_exam(app, 'DEADSUB')
    c = _client(app, sid)
    # Try to submit fresh (correct) answers after time is up.
    c.post(f'/exam/{eid}/submit', data={f'q_{q1}': 'A', f'q_{q2}': 'B', '_csrf_token': 'tok'})
    with app.app_context():
        att = CBTAttempt.query.filter_by(exam_id=eid, student_id=sid).first()
        assert att.status == 'Submitted'
        # No late answers were persisted, so the score is 0 (nothing was saved
        # before the deadline) — the late picks did not count.
        assert (att.raw_score or 0) == 0
