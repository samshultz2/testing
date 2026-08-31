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
        # register the student for exactly this subject, so the drawn paper is
        # deterministic even when a shared test DB holds other subjects too.
        st = Student(first_name='Test', surname='Sitter', student_id=name + '-STU',
                     gender='Female', is_active=True, jamb_subjects=name)
        st.set_portal_password('pass123'); db.session.add(st); db.session.commit()
        return q.id, ex.id, st.student_id


def _portal_login(c, student_id):
    lp = c.get('/exam/login').get_data(as_text=True)
    m = (re.search(r'name="_csrf_token"[^>]*value="([0-9a-f]+)"', lp)
         or re.search(r'csrf-token" content="([0-9a-f]+)"', lp))
    c.post('/exam/login', data={'student_id': student_id, 'password': 'pass123',
                                '_csrf_token': m.group(1) if m else ''})


def test_calculation_subject_detection():
    from utils.mock_jamb_sitting import is_calculation_subject as ic
    for s in ('Mathematics', 'Physics', 'Chemistry', 'Economics',
              'Principles of Accounts', 'Geography', 'Further Mathematics'):
        assert ic(s), s
    for s in ('English Language', 'Literature in English', 'Government', 'Biology', 'CRS'):
        assert not ic(s), s


def test_calculator_offered_only_for_calc_subjects(app):
    from models import db, Student
    # a calc subject → calculator button + panel present
    _qid, exid, student_id = _setup(app, 'Mathematics')   # subject name IS a calc subject
    c = app.test_client()
    _portal_login(c, student_id)
    html = c.get(f'/exam/mock-jamb/{exid}').get_data(as_text=True)
    assert 'id="calcToggle"' in html and 'id="mjCalc"' in html
    assert 'data-k="="' in html and 'data-k="ac"' in html                # basic keys
    low = html.lower()
    assert not any(fn in low for fn in ('sqrt', 'sin(', 'cos(', 'tan(', 'log(', '√'))  # no sci fns

    # a student registered for a non-calc subject only → no calculator
    _qid2, exid2, sid2 = _setup(app, 'Literature in English')
    with app.app_context():
        st = Student.query.filter_by(student_id=sid2).first()
        st.jamb_subjects = 'Literature in English'
        db.session.commit()
    c2 = app.test_client()
    _portal_login(c2, sid2)
    html2 = c2.get(f'/exam/mock-jamb/{exid2}').get_data(as_text=True)
    assert 'id="calcToggle"' not in html2


def test_batch_save_persists_all_answers(app):
    from models import db, MockJAMBQuestion, Subject
    qid, exid, student_id = _setup(app, 'SitBatch')
    # add two more bank questions in the same subject
    with app.app_context():
        sub_id = db.session.get(MockJAMBQuestion, qid).subject_id
        more = []
        for i in range(2):
            q = MockJAMBQuestion(mock_exam_id=None, subject_id=sub_id, question_text=f'More {i}?',
                                 option_a='a', option_b='b', option_c='c', option_d='d',
                                 correct_option='C', marks=1, source='myschool')
            db.session.add(q); db.session.flush(); more.append(q.id)
        db.session.commit()
    c = app.test_client()
    _portal_login(c, student_id)
    page = c.get(f'/exam/mock-jamb/{exid}').get_data(as_text=True)
    csrf = re.search(r'name="csrf-token" content="([0-9a-f]+)"', page).group(1)

    answers = f'{qid}:B,{more[0]}:C,{more[1]}:A'
    r = c.post(f'/exam/mock-jamb/{exid}/save-batch', data={'_csrf_token': csrf, 'answers': answers})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True and body['saved'] == 3

    from models import MockJAMBAnswer
    with app.app_context():
        by_q = {a.question_id: a for a in MockJAMBAnswer.query.all()}
        assert by_q[qid].selected_option == 'B' and by_q[qid].is_correct is True
        assert by_q[more[0]].selected_option == 'C' and by_q[more[0]].is_correct is True
        assert by_q[more[1]].selected_option == 'A' and by_q[more[1]].is_correct is False


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
    seg = re.search(r'<input[^>]*name="q%d"[^>]*value="B"[^>]*>' % qid, page2)
    assert seg and 'checked' in seg.group(0)
