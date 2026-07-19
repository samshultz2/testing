"""ALOC importer: subject-slug mapping, HTML-cleaning normaliser, multi-token
fail-over, year capture, id + text de-duplication (network mocked), and the
import route."""
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


def _raw(qid, q, a, b, c, d, ans, e='', year='2015', image=''):
    return {'id': qid, 'question': q, 'option': {'a': a, 'b': b, 'c': c, 'd': d, 'e': e},
            'answer': ans, 'image': image, 'examtype': 'utme', 'examyear': year}


def test_slug_mapping_and_normalise():
    from utils.aloc import aloc_slug, normalise_item, parse_tokens
    assert aloc_slug('English Language') == 'english'
    assert aloc_slug('Maths') == 'mathematics'
    assert aloc_slug('Christian Religious Studies') == 'crk'
    assert aloc_slug('Fine Art') is None
    n = normalise_item(_raw(5, 'What is <b>H&sup2;O</b>?', 'air', 'water', 'gold', 'iron', 'B', year='2018'))
    assert n['question'] == 'What is H²O?' and n['correct'] == 'B'
    assert n['ext_id'] == '5' and n['exam_year'] == '2018'
    assert normalise_item(_raw(6, 'q', 'a', 'b', 'c', 'd', 'e', e='fifth')) is None
    assert normalise_item(_raw(7, '', 'a', 'b', 'c', 'd', 'a')) is None
    # token parsing splits on newlines/commas/spaces and de-dupes
    assert parse_tokens('ALOC-1\nALOC-2, ALOC-1  ALOC-3') == ['ALOC-1', 'ALOC-2', 'ALOC-3']


def test_import_captures_year_and_dedupes(app, monkeypatch):
    import utils.aloc as aloc
    sid = _subject(app, 'Physics')
    batch = [_raw(i, f'Q{i}?', 'a', 'b', 'c', 'd', 'a', year='201%d' % (i % 10)) for i in range(1, 6)]
    monkeypatch.setattr(aloc, 'fetch_batch', lambda *a, **k: (list(batch), None, False))
    monkeypatch.setattr(aloc, 'import_image', lambda url, **k: url)  # no network for images
    with app.app_context():
        res = aloc.import_questions(sid, 'Physics', ['ALOC-a'], target=5, default_section='mechanics')
        assert res['added'] == 5 and res['error'] is None
        q = MockJAMBQuestion.query.filter_by(subject_id=sid, source='aloc', source_ref='3').first()
        assert q.section == 'mechanics' and q.exam_year == '2013' and q.mock_exam_id is None
        # second run adds nothing (deduped by ALOC id) even though order is "random"
        res2 = aloc.import_questions(sid, 'Physics', ['ALOC-a'], target=5)
        assert res2['added'] == 0 and res2['duplicates'] >= 1


def test_dedupe_by_text_when_id_missing(app, monkeypatch):
    """Questions with no id are de-duped by their (normalised) text."""
    import utils.aloc as aloc
    sid = _subject(app, 'Government')
    dup = _raw('', 'Who   is the head of  state?', 'a', 'b', 'c', 'd', 'a')
    dup2 = _raw('', 'who is the head of state?', 'w', 'x', 'y', 'z', 'b')  # same text, diff case/space
    calls = {'n': 0}

    def fake_fetch(*a, **k):
        calls['n'] += 1
        return ([dup, dup2] if calls['n'] == 1 else []), None, False  # fresh batch once, then empty
    monkeypatch.setattr(aloc, 'fetch_batch', fake_fetch)
    monkeypatch.setattr(aloc, 'import_image', lambda url, **k: url)
    with app.app_context():
        res = aloc.import_questions(sid, 'Government', ['ALOC-a'], target=10)
        assert res['added'] == 1 and res['duplicates'] == 1


def test_token_failover(app, monkeypatch):
    """A rejected/exhausted first token rotates to the next, which succeeds."""
    import utils.aloc as aloc
    sid = _subject(app, 'Chemistry')
    calls = []
    good = [_raw(i, f'C{i}?', 'a', 'b', 'c', 'd', 'a') for i in range(3)]

    def fake_fetch(token, slug, examtype='utme', year=None, timeout=45):
        calls.append(token)
        if token == 'ALOC-dead':
            return [], 'token rejected/exhausted (HTTP 429)', True   # token_bad → rotate
        return list(good), None, False
    monkeypatch.setattr(aloc, 'fetch_batch', fake_fetch)
    monkeypatch.setattr(aloc, 'import_image', lambda url, **k: url)
    with app.app_context():
        res = aloc.import_questions(sid, 'Chemistry', ['ALOC-dead', 'ALOC-live'], target=3)
        assert res['added'] == 3
        assert res['tokens_used'] == 2 and res['tokens_total'] == 2
        assert calls[0] == 'ALOC-dead' and 'ALOC-live' in calls


def test_import_route_saves_multiple_tokens(app, monkeypatch):
    import utils.aloc as aloc
    sid = _subject(app, 'Biology')
    batch = [_raw(100 + i, f'Bio Q{i}?', 'a', 'b', 'c', 'd', 'c') for i in range(4)]
    monkeypatch.setattr(aloc, 'fetch_batch', lambda *a, **k: (list(batch), None, False))
    monkeypatch.setattr(aloc, 'import_image', lambda url, **k: url)
    c = _admin(app); tok = _csrf(c)
    r = c.post('/mock-jamb/bank/import-aloc', data={
        '_csrf_token': tok, 'subject_id': sid, 'tokens': 'ALOC-one\nALOC-two',
        'examtype': 'utme', 'count': '4', 'remember': '1'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert MockJAMBQuestion.query.filter_by(subject_id=sid, source='aloc').count() == 4
        from utils.aloc import get_tokens
        assert get_tokens() == ['ALOC-one', 'ALOC-two']
