"""Batch AI retag via the jobs worker (Anthropic Message Batches API mocked)."""
import itertools
import sys
import types

import pytest

from models import (db, Subject, MockJAMBQuestion, MockJAMBSyllabus,
                    MockJAMBSyllabusNode, BackgroundJob)

_SEQ = itertools.count()


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        MockJAMBSyllabusNode.query.delete()
        MockJAMBSyllabus.query.delete()
        db.session.commit()


def _fake_anthropic(result_map):
    """`anthropic` module whose batch API immediately 'ends' and returns
    result_map = {custom_id: primary_code}."""
    mod = types.ModuleType('anthropic')

    class _Batch:
        id = 'batch_test_1'
        processing_status = 'ended'

    class _Msg:
        def __init__(self, text):
            self.content = [types.SimpleNamespace(text=text)]

    class _Result:
        def __init__(self, primary):
            self.type = 'succeeded'
            self.message = _Msg('{"primary": "%s", "secondary": []}' % primary)

    class _Entry:
        def __init__(self, cid, primary):
            self.custom_id = cid
            self.result = _Result(primary)

    class _Batches:
        def create(self, requests=None, **k):
            self._reqs = requests
            return _Batch()

        def retrieve(self, bid):
            return _Batch()

        def results(self, bid):
            return [_Entry(cid, p) for cid, p in result_map.items()]

    class _Messages:
        batches = _Batches()

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Messages()

    mod.Anthropic = _Client
    return mod


def _drain_all(app, limit=50):
    """Run queued jobs until none remain (poll jobs re-enqueue themselves)."""
    from utils import jobs
    for _ in range(limit):
        with app.app_context():
            ran = jobs.drain(app=app)
        if not ran:
            break


def test_batch_retag_tags_untagged_only_then_force(app, monkeypatch):
    from utils.jamb_syllabus_import import import_syllabus
    from utils import jobs

    tag = next(_SEQ)
    monkeypatch.setattr('utils.jobs.async_enabled', lambda app=None: True)
    monkeypatch.setattr('utils.waec_ocr._vision_config',
                        lambda: {'installed': True, 'has_key': True,
                                 'model': 'claude-haiku-4-5', 'key': 'sk-test'})

    with app.app_context():
        s = Subject(name=f'BatchMath{tag}', is_active=True)
        db.session.add(s)
        db.session.commit()
        import_syllabus(s, open('data/jamb_syllabi/mathematics.json').read(), fmt='json')
        q1 = MockJAMBQuestion(subject_id=s.id, question_text='Convert 45 to base 2',
                              correct_option='A', exam_body='JAMB')
        q2 = MockJAMBQuestion(subject_id=s.id, question_text='Already tagged one',
                              correct_option='A', exam_body='JAMB',
                              syllabus_item_code='MATH.ALG.1.A')
        db.session.add_all([q1, q2])
        db.session.commit()
        q1_id, q2_id, sid = q1.id, q2.id, s.id

        # Model classifies whatever it is asked; only q1 should be in scope (q2 tagged).
        monkeypatch.setitem(sys.modules, 'anthropic',
                            _fake_anthropic({f'q{q1_id}': 'MATH.NUM.1.B'}))
        jobs.enqueue('bank_batch_retag',
                     {'subject_id': sid, 'model': '', 'force': False, 'phase': 'submit'})

    _drain_all(app)

    with app.app_context():
        assert db.session.get(MockJAMBQuestion, q1_id).syllabus_item_code == 'MATH.NUM.1.B'
        # q2 kept its original code (not re-tagged without force)
        assert db.session.get(MockJAMBQuestion, q2_id).syllabus_item_code == 'MATH.ALG.1.A'

    # Now force: q2 is back in scope and gets re-classified.
    with app.app_context():
        monkeypatch.setitem(sys.modules, 'anthropic',
                            _fake_anthropic({f'q{q1_id}': 'MATH.NUM.1.B',
                                             f'q{q2_id}': 'MATH.GEO.1.A'}))
        jobs.enqueue('bank_batch_retag',
                     {'subject_id': sid, 'model': '', 'force': True, 'phase': 'submit'})
    _drain_all(app)
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, q2_id).syllabus_item_code == 'MATH.GEO.1.A'
