"""Mock JAMB uses the coded syllabus everywhere: authoring pickers, saving,
the bank filter, analytics labels -- and keyword taggers are refused."""
import uuid

import pytest

from models import db, Subject, MockJAMBSyllabus, MockJAMBSyllabusNode, MockJAMBQuestion
from tests.conftest import auth_csrf


@pytest.fixture
def econ(app):
    from utils.jamb_syllabus_import import import_syllabus
    with app.app_context():
        s = Subject(name='Economics', is_active=True); db.session.add(s); db.session.commit()
        import_syllabus(s, open('data/jamb_syllabi/economics.json').read(), fmt='json')
        sid = s.id
    yield sid
    with app.app_context():
        y = MockJAMBSyllabus.query.filter_by(subject_id=sid).first()
        MockJAMBQuestion.query.filter_by(subject_id=sid).delete()
        MockJAMBSyllabusNode.query.filter_by(syllabus_id=y.id).delete()
        db.session.delete(y); db.session.delete(db.session.get(Subject, sid)); db.session.commit()


def test_labels_tree_and_codes(app, econ):
    from utils.coded_topics import label_maps, label, coded_tree, code_for, NOT_CODED
    with app.app_context():
        tree = coded_tree(econ)
        assert tree and tree[0]['title'] == 'Economics as a Science'
        dem = next(t for t in tree if t['title'] == 'The Theory of Demand')
        item = dem['subtopics'][0]
        code = code_for(econ, dem['title'], item['title'])
        assert code == item['id']
        maps, coded = label_maps({econ})
        assert label(econ, code, 'scraped text', None, maps, coded) == (dem['title'], item['title'])
        assert label(econ, None, 'Demand and Supply', None, maps, coded) == (NOT_CODED, None)
        assert label(999999, None, 'Free text', 'x', maps, coded) == ('Free text', 'x')   # no coded syllabus


def test_added_question_gets_code_and_section(app, auth_client, econ):
    from utils.coded_topics import coded_tree
    with app.app_context():
        dem = next(t for t in coded_tree(econ) if t['title'] == 'The Theory of Demand')
    r = auth_client.post('/mock-jamb/bank/question/add', data={
        '_csrf_token': auth_csrf(auth_client), 'subject_id': econ, 'question_text': 'Q ' + uuid.uuid4().hex[:6],
        'option_a': 'a', 'option_b': 'b', 'option_c': 'c', 'option_d': 'd', 'correct_option': 'A',
        'topic': dem['title'], 'subtopic': dem['subtopics'][0]['title']})
    assert r.status_code == 302
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(subject_id=econ).order_by(MockJAMBQuestion.id.desc()).first()
        assert q.syllabus_item_code == dem['subtopics'][0]['id'] and q.section == 'dem'


def test_bank_filter_by_syllabus_topic_and_not_coded(app, auth_client, econ):
    from utils.coded_topics import coded_tree, NOT_CODED
    with app.app_context():
        dem = next(t for t in coded_tree(econ) if t['title'] == 'The Theory of Demand')
        a = MockJAMBQuestion(mock_exam_id=None, subject_id=econ, question_text='CODED ' + uuid.uuid4().hex[:5],
                             option_a='a', option_b='b', correct_option='A', marks=1,
                             syllabus_item_code=dem['subtopics'][0]['id'], section='dem')
        b = MockJAMBQuestion(mock_exam_id=None, subject_id=econ, question_text='LOOSE ' + uuid.uuid4().hex[:5],
                             option_a='a', option_b='b', correct_option='A', marks=1, topic='Demand and Supply')
        db.session.add_all([a, b]); db.session.commit()
        ta, tb = a.question_text, b.question_text
    html = auth_client.get('/mock-jamb/bank', query_string={'subject_id': econ, 'topic': dem['title'], 'all': 1}).get_data(as_text=True)
    assert ta in html and tb not in html
    html = auth_client.get('/mock-jamb/bank', query_string={'subject_id': econ, 'topic': NOT_CODED, 'all': 1}).get_data(as_text=True)
    assert tb in html and ta not in html
    assert '>Demand and Supply<' not in html          # scraped free-text topics aren't offered


def test_keyword_taggers_refused_for_coded_subject(app, auth_client, econ):
    r = auth_client.post('/mock-jamb/bank/retag', data={'_csrf_token': auth_csrf(auth_client), 'subject_id': econ})
    assert r.status_code == 302 and '/bank/syllabus' in r.headers['Location']


def test_topic_picker_is_the_coded_syllabus(app, auth_client, econ):
    html = auth_client.get('/mock-jamb/bank', query_string={'subject_id': econ, 'all': 1}).get_data(as_text=True)
    assert 'The Theory of Demand' in html and 'Syllabus topics' not in html
