"""AI retag of bank questions to the coded syllabus (Anthropic client mocked)."""
import itertools
import sys
import types

import pytest

from models import db, Subject, MockJAMBQuestion, MockJAMBSyllabus, MockJAMBSyllabusNode

_SEQ = itertools.count()


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        MockJAMBSyllabusNode.query.delete()
        MockJAMBSyllabus.query.delete()
        db.session.commit()


def _fake_anthropic(reply_json):
    """A stand-in `anthropic` module whose client returns a fixed reply."""
    mod = types.ModuleType('anthropic')

    class _Resp:
        def __init__(self, text):
            self.content = [types.SimpleNamespace(text=text)]

    class _Msgs:
        def create(self, **kw):
            return _Resp(reply_json)

    class _Client:
        def __init__(self, *a, **k):
            self.messages = _Msgs()

    mod.Anthropic = _Client
    return mod


def test_coded_retag_only_accepts_provided_codes(app, monkeypatch):
    import utils.mock_bank_coded_retag as cr
    from utils.jamb_syllabus_import import import_syllabus

    tag = next(_SEQ)
    with app.app_context():
        s = Subject(name=f'RetagMath{tag}', is_active=True)
        db.session.add(s)
        db.session.commit()
        import_syllabus(s, open('data/jamb_syllabi/mathematics.json').read(), fmt='json')
        q_ok = MockJAMBQuestion(subject_id=s.id, question_text='Convert 45 to base 2',
                                option_a='1', option_b='2', option_c='3', option_d='4',
                                correct_option='A', exam_year='2019', exam_body='JAMB')
        q_bad = MockJAMBQuestion(subject_id=s.id, question_text='Totally off-syllabus item',
                                 option_a='1', option_b='2', option_c='3', option_d='4',
                                 correct_option='A', exam_year='2019', exam_body='JAMB')
        db.session.add_all([q_ok, q_bad])
        db.session.commit()
        ok_id, bad_id = q_ok.id, q_bad.id
        sid = s.id

        # The model returns a real code for one, an INVENTED code for another,
        # and OUTSIDE for none-fits — only the real code must be written.
        reply = ('[{"id": %d, "primary": "MATH.NUM.1.B", "secondary": ["MATH.NUM.1.A","MATH.FAKE.9"]},'
                 ' {"id": %d, "primary": "MATH.INVENTED.1"}]' % (ok_id, bad_id))
        monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic(reply))
        monkeypatch.setattr('utils.waec_ocr._vision_config',
                            lambda: {'installed': True, 'has_key': True,
                                     'model': 'claude-haiku-4-5', 'key': 'sk-test'})

        res = cr.coded_retag(s, mode='all')
        assert res['error'] is None
        assert res['tagged'] == 1

        got_ok = db.session.get(MockJAMBQuestion, ok_id)
        assert got_ok.syllabus_item_code == 'MATH.NUM.1.B'
        assert got_ok.syllabus_secondary_codes == 'MATH.NUM.1.A'   # invented secondary dropped
        got_bad = db.session.get(MockJAMBQuestion, bad_id)
        assert got_bad.syllabus_item_code is None                  # invented primary rejected


def test_coded_retag_needs_a_syllabus(app, monkeypatch):
    import utils.mock_bank_coded_retag as cr
    with app.app_context():
        s = Subject(name=f'NoSyll{next(_SEQ)}', is_active=True)
        db.session.add(s)
        db.session.commit()
        monkeypatch.setattr('utils.waec_ocr._vision_config',
                            lambda: {'installed': True, 'has_key': True,
                                     'model': 'm', 'key': 'k'})
        assert cr.coded_retag(s)['error'] == 'no_syllabus'


def _syllabus_with_blueprint_section(tag):
    """A tiny syllabus (one section, one topic, two items) with an item-level
    and a section-level blueprint_section, matching a real per-mock blueprint
    override so the mapping validates against something real."""
    return {
        'subject': f'BpSecSubj{tag}', 'code': f'X{tag}', 'prefix': f'X{tag}',
        'version': '1', 'total': 10,
        'blueprint': [
            {'section': 'antonyms', 'label': 'Antonyms', 'count': 5},
            {'section': 'synonyms', 'label': 'Synonyms', 'count': 5},
        ],
        'sections': [{
            'code': 'LEX', 'name': 'Lexis', 'blueprint_section': 'synonyms', 'topics': [{
                'code': 'LEX.1', 'name': 'Vocabulary', 'items': [
                    {'code': 'LEX.1.A', 'name': 'Antonyms', 'blueprint_section': 'antonyms'},
                    {'code': 'LEX.1.B', 'name': 'Uncurated item'},   # inherits section's 'synonyms'
                ],
            }],
        }],
    }


def test_coded_retag_corrects_section_from_curated_item(app, monkeypatch):
    """A confident coded match to an item with its own blueprint_section fixes
    a wrong free-text section -- the coded classification wins."""
    import json
    import utils.mock_bank_coded_retag as cr
    from utils.jamb_syllabus_import import import_syllabus

    tag = next(_SEQ)
    with app.app_context():
        s = Subject(name=f'BpSecSubj{tag}', is_active=True)
        db.session.add(s); db.session.commit()
        import_syllabus(s, json.dumps(_syllabus_with_blueprint_section(tag)), fmt='json')
        q = MockJAMBQuestion(subject_id=s.id, question_text='opposite of happy',
                             option_a='sad', option_b='glad', option_c='mad', option_d='bad',
                             correct_option='A', section='synonyms')  # wrong: this IS an antonym item
        db.session.add(q); db.session.commit()
        qid = q.id

        reply = '[{"id": %d, "primary": "X%d.LEX.1.A"}]' % (qid, tag)
        monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic(reply))
        monkeypatch.setattr('utils.waec_ocr._vision_config',
                            lambda: {'installed': True, 'has_key': True,
                                     'model': 'm', 'key': 'k'})
        res = cr.coded_retag(s, mode='all')
        assert res['tagged'] == 1
        got = db.session.get(MockJAMBQuestion, qid)
        assert got.section == 'antonyms'


def test_coded_retag_section_inherited_from_ancestor(app, monkeypatch):
    """An item with no blueprint_section of its own inherits its parent
    section's value."""
    import json
    import utils.mock_bank_coded_retag as cr
    from utils.jamb_syllabus_import import import_syllabus

    tag = next(_SEQ)
    with app.app_context():
        s = Subject(name=f'BpSecSubj{tag}', is_active=True)
        db.session.add(s); db.session.commit()
        import_syllabus(s, json.dumps(_syllabus_with_blueprint_section(tag)), fmt='json')
        q = MockJAMBQuestion(subject_id=s.id, question_text='similar to happy',
                             option_a='sad', option_b='glad', option_c='mad', option_d='bad',
                             correct_option='B', section=None)
        db.session.add(q); db.session.commit()
        qid = q.id

        reply = '[{"id": %d, "primary": "X%d.LEX.1.B"}]' % (qid, tag)
        monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic(reply))
        monkeypatch.setattr('utils.waec_ocr._vision_config',
                            lambda: {'installed': True, 'has_key': True,
                                     'model': 'm', 'key': 'k'})
        res = cr.coded_retag(s, mode='all')
        assert res['tagged'] == 1
        got = db.session.get(MockJAMBQuestion, qid)
        assert got.section == 'synonyms'          # inherited from the LEX section


def test_coded_retag_leaves_section_alone_without_curation(app, monkeypatch):
    """A match to a node with no blueprint_section anywhere in its ancestry
    (the mapping hasn't been curated for this subject yet) must not touch
    `section` at all -- same as before this feature existed."""
    import utils.mock_bank_coded_retag as cr
    from utils.jamb_syllabus_import import import_syllabus

    tag = next(_SEQ)
    with app.app_context():
        s = Subject(name=f'RetagMath{tag}b', is_active=True)
        db.session.add(s); db.session.commit()
        import_syllabus(s, open('data/jamb_syllabi/mathematics.json').read(), fmt='json')
        q = MockJAMBQuestion(subject_id=s.id, question_text='Convert 45 to base 2',
                             option_a='1', option_b='2', option_c='3', option_d='4',
                             correct_option='A', section='whatever-was-there-before')
        db.session.add(q); db.session.commit()
        qid = q.id

        reply = '[{"id": %d, "primary": "MATH.NUM.1.B"}]' % qid
        monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic(reply))
        monkeypatch.setattr('utils.waec_ocr._vision_config',
                            lambda: {'installed': True, 'has_key': True,
                                     'model': 'm', 'key': 'k'})
        res = cr.coded_retag(s, mode='all')
        assert res['tagged'] == 1
        got = db.session.get(MockJAMBQuestion, qid)
        assert got.syllabus_item_code == 'MATH.NUM.1.B'
        assert got.section == 'whatever-was-there-before'   # untouched, no mapping curated yet
