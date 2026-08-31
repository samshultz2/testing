"""CBT syllabus topics & sub-topics: model, CRUD routes, seed, the topic tree
API, and the topic drop-downs on the question-authoring page."""
from config import Config
from models import db, Subject, SyllabusTopic, CBTExam, Branch
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    import re
    html = c.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _subject(app, name):
    with app.app_context():
        s = Subject.query.filter_by(name=name).first() or Subject(name=name, is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def test_add_topic_and_subtopic(app):
    sid = _subject(app, 'Mathematics')
    c = _admin(app); tok = _csrf(c)
    # add a topic
    r = c.post('/cbt/syllabus/add', data={'_csrf_token': tok, 'subject_id': sid,
               'title': 'Algebra', 'exam_body': 'JAMB'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        t = SyllabusTopic.query.filter_by(subject_id=sid, title='Algebra', parent_id=None).first()
        assert t is not None and t.exam_body == 'JAMB'
        tid = t.id
    # add a sub-topic under it
    r = c.post('/cbt/syllabus/add', data={'_csrf_token': tok, 'subject_id': sid,
               'title': 'Polynomials', 'parent_id': tid}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        sub = SyllabusTopic.query.filter_by(subject_id=sid, title='Polynomials').first()
        assert sub is not None and sub.parent_id == tid
        assert sub.exam_body == 'JAMB'          # inherits the parent's exam body


def test_topic_tree_and_api(app):
    sid = _subject(app, 'Physics')
    with app.app_context():
        t = SyllabusTopic(subject_id=sid, title='Mechanics', order=1); db.session.add(t); db.session.flush()
        db.session.add(SyllabusTopic(subject_id=sid, parent_id=t.id, title='Motion', order=1))
        db.session.add(SyllabusTopic(subject_id=sid, parent_id=t.id, title='Newton laws', order=2))
        db.session.commit()
    from routes.cbt import _subject_topic_tree
    with app.app_context():
        tree = _subject_topic_tree(sid)
        assert len(tree) == 1 and tree[0]['title'] == 'Mechanics'
        assert [s['title'] for s in tree[0]['subtopics']] == ['Motion', 'Newton laws']
    c = _admin(app)
    r = c.get(f'/cbt/api/subjects/{sid}/topics')
    assert r.status_code == 200
    data = r.get_json()
    assert data['topics'][0]['title'] == 'Mechanics'
    assert len(data['topics'][0]['subtopics']) == 2


def test_seed_starter_syllabus(app):
    sid = _subject(app, 'Chemistry')
    c = _admin(app); tok = _csrf(c)
    r = c.post('/cbt/syllabus/seed', data={'_csrf_token': tok, 'subject_id': sid},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        tops = SyllabusTopic.query.filter_by(subject_id=sid, parent_id=None).count()
        subs = SyllabusTopic.query.filter(SyllabusTopic.subject_id == sid,
                                          SyllabusTopic.parent_id.isnot(None)).count()
        assert tops >= 4 and subs >= 8


def test_full_syllabus_covers_core_and_main_subjects(app):
    """The bundled syllabus is complete for the core UTME subjects and covers the
    main electives — every entry has topics, and every topic has sub-topics."""
    from utils.syllabus_data import FULL_SYLLABUS
    expected = {'mathematics', 'english language', 'physics', 'chemistry', 'biology',
                'economics', 'government', 'commerce', 'accounting', 'literature in english',
                'agricultural science', 'geography', 'christian religious studies', 'civic education'}
    assert expected <= set(FULL_SYLLABUS)
    for subj, topics in FULL_SYLLABUS.items():
        assert topics, subj
        for topic, subs in topics:
            assert topic and subs, (subj, topic)      # no empty topic or sub-topic list
    # the core science/maths blueprints are genuinely detailed
    assert len(FULL_SYLLABUS['mathematics']) >= 5
    assert sum(len(s) for _t, s in FULL_SYLLABUS['physics']) >= 30


def test_seed_all_subjects(app):
    """One click seeds the full syllabus for every matching subject with no topics.
    (Uses electives untouched by other tests, since the test DB is shared.)"""
    com = _subject(app, 'Commerce'); civ = _subject(app, 'Civic Education')
    c = _admin(app); tok = _csrf(c)
    r = c.post('/cbt/syllabus/seed-all', data={'_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        for sid in (com, civ):
            assert SyllabusTopic.query.filter_by(subject_id=sid, parent_id=None).count() >= 4
        # a subject already seeded is not duplicated on a second run
        before = SyllabusTopic.query.filter_by(subject_id=com, parent_id=None).count()
    c.post('/cbt/syllabus/seed-all', data={'_csrf_token': tok}, follow_redirects=True)
    with app.app_context():
        after = SyllabusTopic.query.filter_by(subject_id=com, parent_id=None).count()
        assert after == before


def test_delete_topic_cascades_subtopics(app):
    # A subject with no bundled syllabus, so seed-all in another test can't add a
    # colliding 'Ecology' topic (the DB is shared across tests).
    sid = _subject(app, 'Further Mathematics')
    with app.app_context():
        t = SyllabusTopic(subject_id=sid, title='Ecology'); db.session.add(t); db.session.flush()
        db.session.add(SyllabusTopic(subject_id=sid, parent_id=t.id, title='Food chains'))
        db.session.commit(); tid = t.id
    c = _admin(app); tok = _csrf(c)
    r = c.post(f'/cbt/syllabus/{tid}/delete', data={'_csrf_token': tok}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(SyllabusTopic, tid) is None            # topic gone
        assert SyllabusTopic.query.filter_by(subject_id=sid, title='Food chains').first() is None


def test_exam_detail_shows_topic_dropdown(app):
    """The question-authoring page renders the subject's topics as a <select>."""
    sid = _subject(app, 'Government')
    with app.app_context():
        db.session.add(SyllabusTopic(subject_id=sid, title='Political Ideologies'))
        bid = Branch.get_default().id
        ex = CBTExam(title='Gov Test', subject_id=sid, branch_id=bid, access_password='x')
        db.session.add(ex); db.session.commit()
        eid = ex.id
    c = _admin(app)
    html = c.get(f'/cbt/exams/{eid}').get_data(as_text=True)
    assert 'id="qtopic"' in html and 'Political Ideologies' in html
    assert 'id="qsubtopic"' in html


def test_add_question_saves_topic_and_subtopic(app):
    sid = _subject(app, 'Economics')
    with app.app_context():
        bid = Branch.get_default().id
        ex = CBTExam(title='Econ Test', subject_id=sid, branch_id=bid, access_password='x')
        db.session.add(ex); db.session.commit()
        eid = ex.id
    c = _admin(app); tok = _csrf(c)
    r = c.post(f'/cbt/exams/{eid}/questions/add', data={
        '_csrf_token': tok, 'question_text': 'What is demand?', 'correct_option': 'A',
        'option_a': 'x', 'option_b': 'y', 'option_c': 'z', 'option_d': 'w',
        'topic': 'Demand and Supply', 'subtopic': 'Law of demand', 'marks': '1',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        from models import CBTQuestion
        q = CBTQuestion.query.filter_by(exam_id=eid).first()
        assert q.topic == 'Demand and Supply' and q.subtopic == 'Law of demand'
