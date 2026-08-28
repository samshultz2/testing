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
