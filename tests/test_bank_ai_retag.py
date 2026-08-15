"""AI topic-tagging for the Mock-JAMB bank: uses the linked Anthropic key,
only assigns real syllabus topics, and honours the year filter. The Anthropic
client is faked so no network/paid call happens.
"""
import sys
import types

from models import db, Subject, MockJAMBQuestion
import utils.mock_bank_ai_retag as ar


def _install_fake_anthropic(monkeypatch):
    mod = types.ModuleType('anthropic')
    class Anthropic:                       # constructible; never actually called
        def __init__(self, **kw):
            pass
    mod.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, 'anthropic', mod)


def _cfg(installed=True, has_key=True):
    return {'enabled': True, 'model': 'claude-haiku-4-5', 'key': 'sk-test',
            'has_key': has_key, 'key_masked': '', 'env_key': False,
            'key_source': 'settings', 'installed': installed}


def test_extract_json_array_tolerates_prose_and_fences():
    assert ar._extract_json_array('[{"id":1,"topic":"X"}]') == [{'id': 1, 'topic': 'X'}]
    assert ar._extract_json_array('Here you go:\n```json\n[{"id":2}]\n```') == [{'id': 2}]
    assert ar._extract_json_array('no json here') == []


def test_ai_retag_reports_no_key(app, monkeypatch):
    monkeypatch.setattr('utils.waec_ocr._vision_config', lambda: _cfg(has_key=False))
    with app.app_context():
        subj = Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.commit()
        try:
            res = ar.ai_retag(subj)
            assert res['error'] == 'no_key' and res['topic_set'] == 0
        finally:
            db.session.delete(subj); db.session.commit()


def test_ai_retag_tags_valid_topic_and_respects_year(app, monkeypatch):
    from utils.syllabus_data import FULL_SYLLABUS
    valid_topic = FULL_SYLLABUS['mathematics'][0][0]     # a real syllabus topic

    monkeypatch.setattr('utils.waec_ocr._vision_config', lambda: _cfg())
    _install_fake_anthropic(monkeypatch)

    # Fake the model call: tag every passed row with the valid topic, plus one
    # invented (invalid) topic that must be rejected.
    def fake_tag_chunk(client, model, subject_name, topics, rows):
        out = {}
        for r in rows:
            out[r.id] = (valid_topic, 'sub')
        return out
    monkeypatch.setattr('utils.mock_bank_ai_retag._tag_chunk', fake_tag_chunk)

    with app.app_context():
        subj = Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.flush()
        q19 = MockJAMBQuestion(subject_id=subj.id, exam_year='2019',
                               question_text='2019 q', option_a='a', option_b='b',
                               option_c='c', option_d='d', correct_option='A')
        q20 = MockJAMBQuestion(subject_id=subj.id, exam_year='2020',
                               question_text='2020 q', option_a='a', option_b='b',
                               option_c='c', option_d='d', correct_option='A')
        db.session.add_all([q19, q20]); db.session.commit()
        ids = (subj.id, q19.id, q20.id)
        try:
            res = ar.ai_retag(subj, year='2019')
            assert res['error'] is None
            assert res['scanned'] == 1 and res['topic_set'] == 1   # only 2019 in scope
            db.session.expire_all()
            assert db.session.get(MockJAMBQuestion, ids[1]).topic == valid_topic
            assert db.session.get(MockJAMBQuestion, ids[2]).topic in (None, '')  # 2020 untouched
        finally:
            for qid in ids[1:]:
                o = db.session.get(MockJAMBQuestion, qid)
                if o:
                    db.session.delete(o)
            db.session.delete(db.session.get(Subject, ids[0]))
            db.session.commit()


def test_ai_retag_rejects_invented_topic(app, monkeypatch):
    monkeypatch.setattr('utils.waec_ocr._vision_config', lambda: _cfg())
    _install_fake_anthropic(monkeypatch)
    monkeypatch.setattr('utils.mock_bank_ai_retag._tag_chunk',
                        lambda *a, **k: {r.id: ('Totally Made Up Topic', None)
                                         for r in a[4]})
    with app.app_context():
        subj = Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.flush()
        q = MockJAMBQuestion(subject_id=subj.id, exam_year='2019',
                             question_text='q', correct_option='A')
        db.session.add(q); db.session.commit()
        qid, sid = q.id, subj.id
        try:
            res = ar.ai_retag(subj)
            assert res['scanned'] == 1 and res['topic_set'] == 0   # invented topic ignored
            db.session.expire_all()
            assert (db.session.get(MockJAMBQuestion, qid).topic or '') == ''
        finally:
            db.session.delete(db.session.get(MockJAMBQuestion, qid))
            db.session.delete(db.session.get(Subject, sid))
            db.session.commit()
