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


def test_blueprints_follow_the_jamb_syllabus_parts():
    """Outside English/Literature: one section per top-level syllabus part,
    labelled with the part's name, counts summing to 40, at least 1 each."""
    import glob, json
    for f in glob.glob('data/jamb_syllabi/*.json'):
        d = json.load(open(f))
        if d['subject'] in ('English Language', 'Literature in English'):
            continue
        bp = d['blueprint']
        assert [x['label'] for x in bp] == [p['name'] for p in d['sections']], f
        assert [x['section'] for x in bp] == [p['blueprint_section'] for p in d['sections']], f
        assert sum(x['count'] for x in bp) == 40 and min(x['count'] for x in bp) >= 1, f


def test_every_bundled_syllabus_blueprint_tallies_with_its_mappings():
    import glob, json
    for f in glob.glob('data/jamb_syllabi/*.json'):
        d = json.load(open(f))
        if d.get('subject') == 'Literature in English':
            continue                     # uses the built-in Literature blueprint
        bp = {x['section']: x['count'] for x in d.get('blueprint') or []}
        assert bp, f
        assert sum(bp.values()) == (d.get('total') or 40), f
        used = set()

        def walk(nodes):
            for n in nodes:
                if n.get('blueprint_section'):
                    used.add(n['blueprint_section'])
                walk(n.get('topics') or n.get('items') or [])
        walk(d['sections'])
        assert used == set(bp), (f, used ^ set(bp))


def test_short_paper_topped_up_from_unsorted_questions():
    bp = _bp(('micro', 6, False), ('macro', 4, False))
    standalone = {'micro': [_q('micro') for _ in range(2)], 'general': [_q('general') for _ in range(20)],
                  'novel': [_q('novel') for _ in range(5)]}
    items, served = draw_paper(bp, {}, standalone, random.Random(5), arrange=True)
    assert len(served) == 10
    secs = [i['q'].section for i in items]
    assert secs[:2] == ['micro', 'micro'] and set(secs[2:]) == {'general'} and 'novel' not in secs


def test_sync_blueprint_adopts_bundled_when_stored_is_empty(app):
    import json
    from models import db, Subject, MockJAMBSyllabus
    from utils.syllabus_sections import sync_blueprint
    with app.app_context():
        s = Subject(name='Economics', is_active=False); db.session.add(s); db.session.flush()
        y = MockJAMBSyllabus(subject_id=s.id, subject_name='Economics', blueprint=None)
        db.session.add(y); db.session.commit()
        try:
            ch = sync_blueprint(s)
            import json as _j
            parts = {p['code'].lower() for p in _j.load(open('data/jamb_syllabi/economics.json'))['sections']}
            assert {k for k, _, _ in ch} == parts                # one section per JAMB syllabus part
            assert sum(x['count'] for x in json.loads(y.blueprint)) == 40
            assert sync_blueprint(s) == []                       # second run: nothing to do
        finally:
            db.session.delete(y); db.session.delete(s); db.session.commit()


def test_server_update_replaces_stale_mappings_and_old_blueprint(app):
    """A server that imported Economics with the earlier micro/macro sections
    is brought onto the JAMB parts; a mapping someone set to a valid section stays."""
    import json
    from models import db, Subject, MockJAMBSyllabus, MockJAMBSyllabusNode
    from utils.jamb_syllabus_import import import_syllabus
    from utils.syllabus_sections import sync_blueprint, sync_mappings
    with app.app_context():
        s = Subject(name='Economics', is_active=False); db.session.add(s); db.session.commit()
        import_syllabus(s, open('data/jamb_syllabi/economics.json').read(), fmt='json')
        y = MockJAMBSyllabus.query.filter_by(subject_id=s.id).first()
        try:
            # make it look like the earlier version
            y.blueprint = json.dumps([{'section': 'micro', 'label': 'Microeconomics', 'count': 18},
                                      {'section': 'macro', 'label': 'Money, income and finance', 'count': 9},
                                      {'section': 'development', 'label': 'Public finance and development', 'count': 9},
                                      {'section': 'international', 'label': 'International trade', 'count': 4}])
            nodes = {n.code: n for n in MockJAMBSyllabusNode.query.filter_by(syllabus_id=y.id)}
            dem = next(c for c in nodes if c.endswith('.DEM'))
            sup = next(c for c in nodes if c.endswith('.SUP'))
            nodes[dem].blueprint_section = 'micro'           # stale
            nodes[sup].blueprint_section = 'dem'             # someone's own (valid) choice
            db.session.commit()
            assert sync_blueprint(s)
            assert {x['section'] for x in json.loads(y.blueprint)} >= {'dem', 'sup', 'nat', 'org'}
            sync_mappings(s)
            assert nodes[dem].blueprint_section == 'dem' and nodes[sup].blueprint_section == 'dem'
        finally:
            MockJAMBSyllabusNode.query.filter_by(syllabus_id=y.id).delete()
            db.session.delete(y); db.session.delete(s); db.session.commit()
