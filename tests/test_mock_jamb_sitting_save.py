"""Online Mock JAMB sitting: a bank-drawn question's answer must save (it draws
from the shared bank, so its questions are owned by no exam), and a refresh must
resume the paper with the saved answer pre-selected."""
import datetime
import re


def _setup(app, name):
    from models import (db, Subject, MockJAMBQuestion, MockJAMBExam, Student,
                        AcademicSession)
    with app.app_context():
        sess = (AcademicSession.query.filter_by(is_active=True).first()
                or AcademicSession(name='SitSess', is_active=True))
        if sess.id is None:
            db.session.add(sess)
        db.session.flush()
        sub = Subject(name=name, is_active=True); db.session.add(sub); db.session.flush()
        q = MockJAMBQuestion(mock_exam_id=None, subject_id=sub.id, question_text='Bank q?',
                             option_a='a', option_b='b', option_c='c', option_d='d',
                             correct_option='B', marks=1, source='myschool')
        db.session.add(q)
        ex = MockJAMBExam(name=name + ' Mock', exam_number=1, session_id=sess.id,
                          exam_date=datetime.date.today(), is_published=True, is_active=True,
                          source_mode='bank', duration_minutes=90)
        db.session.add(ex); db.session.flush()
        st = Student(first_name='Test', surname='Sitter', student_id=name + '-STU',
                     gender='Female', is_active=True)
        st.set_portal_password('pass123'); db.session.add(st); db.session.commit()
        return q.id, ex.id, st.student_id


def _portal_login(c, student_id):
    lp = c.get('/exam/login').get_data(as_text=True)
    m = (re.search(r'name="_csrf_token"[^>]*value="([0-9a-f]+)"', lp)
         or re.search(r'csrf-token" content="([0-9a-f]+)"', lp))
    c.post('/exam/login', data={'student_id': student_id, 'password': 'pass123',
                                '_csrf_token': m.group(1) if m else ''})


def test_bank_drawn_answer_saves_and_resumes(app):
    qid, exid, student_id = _setup(app, 'SitBankSave')
    c = app.test_client()
    _portal_login(c, student_id)
    page = c.get(f'/exam/mock-jamb/{exid}').get_data(as_text=True)     # creates the attempt
    csrf = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page).group(1)

    r = c.post(f'/exam/mock-jamb/{exid}/save',
               data={'_csrf_token': csrf, 'question_id': qid, 'option': 'B'})
    assert r.status_code == 200 and r.get_json().get('ok') is True     # bank answer accepted

    from models import MockJAMBAnswer, MockJAMBAttempt
    with app.app_context():
        ans = MockJAMBAnswer.query.filter_by(question_id=qid).first()
        assert ans and ans.selected_option == 'B' and ans.is_correct is True
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=exid).first()
        assert att.started_at is not None and att.status != 'Submitted'   # timer base for resume

    # refresh → the saved option is pre-checked, so the student continues where they left off
    page2 = c.get(f'/exam/mock-jamb/{exid}').get_data(as_text=True)
    seg = re.search(r'<input[^>]*value="B"[^>]*>', page2)
    assert seg and 'checked' in seg.group(0)
