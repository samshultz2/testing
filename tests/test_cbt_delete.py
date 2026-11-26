"""CBT: delete exams (one or several) and several questions at once."""
import uuid

from models import db, CBTExam, CBTQuestion, CBTAttempt, QuestionBank, Student
from tests.conftest import auth_csrf


def _h(c):
    return {'X-Requested-With': 'fetch', 'Accept': 'application/json', 'X-CSRFToken': auth_csrf(c)}


def _exam(n_q=3, title=None):
    e = CBTExam(title=title or 'Del ' + uuid.uuid4().hex[:6])
    db.session.add(e); db.session.flush()
    for i in range(n_q):
        db.session.add(CBTQuestion(exam_id=e.id, question_text='Q%d' % i, option_a='a', option_b='b',
                                   option_c='c', option_d='d', correct_option='A', marks=1, order=i + 1))
    return e


def test_delete_one_and_several_exams(app, auth_client):
    with app.app_context():
        a, b, c = _exam(), _exam(), _exam()
        st = Student(student_id='CBDEL' + uuid.uuid4().hex[:5], first_name='Del', surname='Test', gender='Male')
        db.session.add(st); db.session.flush()
        db.session.add(CBTAttempt(exam_id=b.id, student_id=st.id, status='Submitted'))
        db.session.commit()
        ids = a.id, b.id, c.id
    r = auth_client.post('/cbt/exams/%d/delete' % ids[0], headers=_h(auth_client))
    assert r.status_code == 200 and r.get_json()['ok']
    r = auth_client.post('/cbt/exams/delete', data={'ids': '%d,%d' % ids[1:]},
                         headers=_h(auth_client))
    assert r.get_json()['ok'] and r.get_json()['deleted'] == 2
    with app.app_context():
        assert CBTExam.query.filter(CBTExam.id.in_(ids)).count() == 0
        assert CBTQuestion.query.filter(CBTQuestion.exam_id.in_(ids)).count() == 0
        assert CBTAttempt.query.filter(CBTAttempt.exam_id.in_(ids)).count() == 0
    # nothing ticked
    r = auth_client.post('/cbt/exams/delete', data={}, headers=_h(auth_client))
    assert r.status_code == 400 and not r.get_json()['ok']


def test_delete_several_questions_of_one_exam_only(app, auth_client):
    with app.app_context():
        e, other = _exam(4), _exam(2)
        db.session.commit()
        qs = [q.id for q in e.questions.order_by(CBTQuestion.order)]
        other_q = other.questions.first().id
        eid, oid = e.id, other.id
    r = auth_client.post('/cbt/exams/%d/questions/delete' % eid, data={'ids': [qs[0], qs[2], other_q], '_csrf_token': auth_csrf(auth_client)})
    assert r.status_code == 302
    with app.app_context():
        left = {q.id for q in CBTQuestion.query.filter_by(exam_id=eid)}
        assert left == {qs[1], qs[3]}
        assert db.session.get(CBTQuestion, other_q) is not None      # another exam's question is untouched
        for x in (eid, oid):
            db.session.delete(db.session.get(CBTExam, x))
        db.session.commit()


def test_remove_several_bank_questions(app, auth_client):
    with app.app_context():
        rows = [QuestionBank(question_text='BD %d %s' % (i, uuid.uuid4().hex[:4]), option_a='a', option_b='b',
                             correct_option='A', marks=1, is_active=True) for i in range(3)]
        db.session.add_all(rows); db.session.commit()
        ids = [r.id for r in rows]
    r = auth_client.post('/cbt/bank/delete', data={'ids': ids[:2], '_csrf_token': auth_csrf(auth_client)})
    assert r.status_code == 302
    with app.app_context():
        got = {q.id: q.is_active for q in QuestionBank.query.filter(QuestionBank.id.in_(ids))}
        assert got == {ids[0]: False, ids[1]: False, ids[2]: True}
        QuestionBank.query.filter(QuestionBank.id.in_(ids)).delete(synchronize_session=False); db.session.commit()


def test_exam_page_and_overview_offer_delete(app, auth_client):
    with app.app_context():
        e = _exam(2); db.session.commit(); eid = e.id
    html = auth_client.get('/cbt/exams/%d' % eid).get_data(as_text=True)
    assert 'Delete exam' in html and 'data-qsel="exQsel"' in html
    data = auth_client.get('/cbt/', headers=_h(auth_client)).get_json()
    assert data['urls']['delete_many'].endswith('/cbt/exams/delete')
    assert any(x['id'] == eid and x['delete_url'].endswith('/cbt/exams/%d/delete' % eid) for x in data['exams']) or not data['exams']
    with app.app_context():
        db.session.delete(db.session.get(CBTExam, eid)); db.session.commit()
