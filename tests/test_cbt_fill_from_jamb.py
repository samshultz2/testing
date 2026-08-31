"""CBT: fill a test from the central Mock JAMB question bank by topic + count."""
from config import Config
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(client)})
    return client


def _csrf(client):
    import re
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                  client.get('/students').get_data(as_text=True))
    return m.group(1) if m else None


def _setup(app):
    from models import db, CBTExam, Subject, MockJAMBQuestion
    with app.app_context():
        subj = Subject(name='FillBankChemistry', is_active=True)
        db.session.add(subj); db.session.flush()
        for i in range(12):
            topic = 'Organic Chemistry' if i % 2 == 0 else 'Acids, Bases and Salts'
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=subj.id, section='organic',
                question_text=f'Bank Q{i} unique text', option_a='a', option_b='b',
                option_c='c', option_d='d', correct_option='A', marks=1,
                topic=topic, order=i))
        e = CBTExam(title='Chem Class Test', subject_id=subj.id)
        db.session.add(e); db.session.commit()
        return e.id, subj.id


def test_fill_from_jamb_draws_by_topic_and_count(app):
    from models import db, CBTExam
    eid, sid = _setup(app)
    c = _admin(app)

    # GET shows the topic picker
    r = c.get(f'/cbt/exams/{eid}/fill-from-jamb')
    assert r.status_code == 200
    assert b'Organic Chemistry' in r.data

    # POST: draw 4 from one topic only
    tok = _csrf(c)
    c.post(f'/cbt/exams/{eid}/fill-from-jamb',
           data={'_csrf_token': tok, 'topics': ['Organic Chemistry'], 'count': 4, 'marks': 2},
           follow_redirects=True)
    with app.app_context():
        e = db.session.get(CBTExam, eid)
        qs = e.questions.all()
        assert len(qs) == 4
        assert all(q.topic == 'Organic Chemistry' for q in qs)
        assert all(q.marks == 2 for q in qs)


def test_fill_from_jamb_dedupes_on_repeat(app):
    from models import db, CBTExam
    eid, sid = _setup(app)
    c = _admin(app)
    # Ask for more than exist in the single topic (6) twice — never duplicates.
    for _ in range(2):
        tok = _csrf(c)
        c.post(f'/cbt/exams/{eid}/fill-from-jamb',
               data={'_csrf_token': tok, 'topics': ['Organic Chemistry'], 'count': 50},
               follow_redirects=True)
    with app.app_context():
        e = db.session.get(CBTExam, eid)
        texts = [q.question_text for q in e.questions]
        assert len(texts) == len(set(texts))     # no duplicates
        assert len(texts) == 6                    # only the 6 organic ones exist
