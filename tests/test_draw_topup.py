"""A paper always reaches its blueprint total when the bank has enough questions."""
import random
from types import SimpleNamespace as NS

from utils.jamb_blueprint import draw_paper
from utils.syllabus_sections import _PREVIOUS_BLUEPRINTS

_n = [0]


def _q(section, passage=None):
    _n[0] += 1
    return NS(id=_n[0], section=section, passage_id=passage, syllabus_item_code=None)


def _bp(*secs):
    out = [{'section': k, 'label': k, 'count': c, 'passage': p, 'per_passage': 5} for k, c, p in secs]
    return {'total': sum(c for _, c, _ in secs), 'sections': out}


def _count(items):
    return sum(len(i['questions']) if i['kind'] == 'passage' else 1 for i in items)


def test_summary_short_borrows_comprehension_passage():
    bp = _bp(('comprehension', 5, True), ('summary', 5, True), ('synonyms', 5, False))
    passages = {'comprehension': [{'passage': NS(id=p), 'questions': [_q('comprehension', p) for _ in range(5)]}
                                  for p in (1, 2)]}
    standalone = {'synonyms': [_q('synonyms') for _ in range(8)]}
    items, served = draw_paper(bp, passages, standalone, random.Random(1), arrange=True)
    assert _count(items) == 15 and len(served) == 15
    assert sum(1 for i in items if i['kind'] == 'passage') == 2          # both comprehension passages
    assert len({i['passage'].id for i in items if i['kind'] == 'passage'}) == 2   # never the same one twice


def test_short_standalone_section_topped_up_from_others_not_novel():
    bp = _bp(('novel', 5, False), ('antonyms', 5, False), ('basic_grammar', 10, False))
    standalone = {'novel': [_q('novel')], 'antonyms': [_q('antonyms') for _ in range(2)],
                  'basic_grammar': [_q('basic_grammar') for _ in range(30)]}
    extra_novel = [_q('novel') for _ in range(5)]                         # other book: not offered
    items, served = draw_paper(bp, {}, standalone, random.Random(2), arrange=True)
    assert _count(items) == 20 and len(served) == 20
    assert not served & {q.id for q in extra_novel}
    # arranged papers keep section order: novel, antonyms, then grammar
    secs = [i['q'].section for i in items]
    assert secs == sorted(secs, key=['novel', 'antonyms', 'basic_grammar'].index)


def test_bank_too_small_serves_what_it_has():
    bp = _bp(('synonyms', 5, False), ('antonyms', 5, False))
    standalone = {'synonyms': [_q('synonyms') for _ in range(3)], 'antonyms': [_q('antonyms')]}
    items, served = draw_paper(bp, {}, standalone, random.Random(3))
    assert _count(items) == 4


def test_english_bundled_blueprint_and_previous():
    import json
    d = json.load(open('data/jamb_syllabi/english_language.json'))
    counts = {x['section']: x['count'] for x in d['blueprint']}
    assert counts['comprehension'] == 10 and counts['summary'] == 0 and sum(counts.values()) == 60
    assert _PREVIOUS_BLUEPRINTS['english language'] == [{'comprehension': 5, 'summary': 5}]


def test_sync_blueprint_updates_only_untouched(app):
    import json, uuid
    from models import db, Subject, MockJAMBSyllabus
    from utils.syllabus_sections import sync_blueprint
    d = json.load(open('data/jamb_syllabi/english_language.json'))
    old = [dict(x) for x in d['blueprint']]
    for x in old:
        if x['section'] in ('comprehension', 'summary'):
            x['count'] = 5
    edited = [dict(x) for x in old]
    edited[-1]['count'] += 1                                  # someone changed it by hand
    with app.app_context():
        out = []
        for bp in (old, edited):
            s = Subject(name='English Language', is_active=False); db.session.add(s); db.session.flush()
            y = MockJAMBSyllabus(subject_id=s.id, subject_name='English Language %s' % uuid.uuid4().hex[:4],
                                 blueprint=json.dumps(bp))
            db.session.add(y); db.session.commit()
            out.append((s, y, sync_blueprint(s)))
        try:
            (s1, y1, ch1), (s2, y2, ch2) = out
            assert sorted(ch1) == [('comprehension', 5, 10), ('summary', 5, 0)]
            assert {x['section']: x['count'] for x in json.loads(y1.blueprint)}['comprehension'] == 10
            assert ch2 == [] and json.loads(y2.blueprint) == edited
        finally:
            for s, y, _ in out:
                db.session.delete(y); db.session.delete(s)
            db.session.commit()
