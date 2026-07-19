"""ALOC importer: subject-slug mapping, HTML-cleaning normaliser, batch import
with de-duplication (network mocked), and the import route."""
from config import Config
from models import db, Subject, MockJAMBQuestion, SchoolSettings
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    import re
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', c.get('/students').get_data(as_text=True))
    return m.group(1) if m else None


def _subject(app, name):
    with app.app_context():
        s = Subject.query.filter_by(name=name).first() or Subject(name=name, is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _raw(qid, q, a, b, c, d, ans, e=''):
    return {'id': qid, 'question': q, 'option': {'a': a, 'b': b, 'c': c, 'd': d, 'e': e},
            'answer': ans, 'image': '', 'examtype': 'utme', 'examyear': '2010'}


def test_slug_mapping_and_normalise():
    from utils.aloc import aloc_slug, normalise_item
    assert aloc_slug('English Language') == 'english'
    assert aloc_slug('Maths') == 'mathematics'
    assert aloc_slug('Christian Religious Studies') == 'crk'
    assert aloc_slug('Fine Art') is None            # ALOC has no slug for it
    # HTML is stripped/unescaped
    n = normalise_item(_raw(5, 'What is <b>H&sup2;O</b>?', 'air', 'water', 'gold', 'iron', 'B'))
    assert n['question'] == 'What is H²O?' and n['correct'] == 'B' and n['ext_id'] == '5'
    # a genuine 5th option is skipped (our model holds 4)
    assert normalise_item(_raw(6, 'q', 'a', 'b', 'c', 'd', 'e', e='fifth')) is None
    # bad answer / missing text skipped
    assert normalise_item(_raw(7, '', 'a', 'b', 'c', 'd', 'a')) is None


def test_import_dedupes(app, monkeypatch):
    import utils.aloc as aloc
    sid = _subject(app, 'Physics')
    batch = [_raw(i, f'Q{i}?', 'a', 'b', 'c', 'd', 'a') for i in range(1, 6)]

    def fake_fetch(token, slug, examtype='utme', year=None, timeout=20):
        return list(batch), None
    monkeypatch.setattr(aloc, 'fetch_batch', fake_fetch)

    with app.app_context():
        res = aloc.import_questions(sid, 'Physics', 'ALOC-test', target=5, default_section='mechanics')
        assert res['added'] == 5 and res['error'] is None
        assert MockJAMBQuestion.query.filter_by(subject_id=sid, source='aloc').count() == 5
        one = MockJAMBQuestion.query.filter_by(subject_id=sid, source='aloc').first()
        assert one.section == 'mechanics' and one.mock_exam_id is None and one.exam_body == 'JAMB'
        # a second run imports nothing new (deduped by ALOC id)
        res2 = aloc.import_questions(sid, 'Physics', 'ALOC-test', target=5)
        assert res2['added'] == 0 and res2['duplicates'] >= 1


def test_import_reports_token_error(app, monkeypatch):
    import utils.aloc as aloc
    sid = _subject(app, 'Chemistry')
    monkeypatch.setattr(aloc, 'fetch_batch',
                        lambda *a, **k: ([], 'ALOC rejected the access token (check it is correct and active).'))
    with app.app_context():
        res = aloc.import_questions(sid, 'Chemistry', 'bad', target=10)
        assert res['added'] == 0 and 'token' in res['error'].lower()


def test_import_route_and_token_save(app, monkeypatch):
    import utils.aloc as aloc
    sid = _subject(app, 'Biology')
    batch = [_raw(100 + i, f'Bio Q{i}?', 'a', 'b', 'c', 'd', 'c') for i in range(4)]
    monkeypatch.setattr(aloc, 'fetch_batch', lambda *a, **k: (list(batch), None))
    c = _admin(app); tok = _csrf(c)
    r = c.post('/mock-jamb/bank/import-aloc', data={
        '_csrf_token': tok, 'subject_id': sid, 'token': 'ALOC-remember-me',
        'examtype': 'utme', 'count': '4', 'remember': '1'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert MockJAMBQuestion.query.filter_by(subject_id=sid, source='aloc').count() == 4
        assert SchoolSettings.get('aloc_access_token') == 'ALOC-remember-me'
