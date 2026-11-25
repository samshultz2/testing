"""Use of English sections under an imported syllabus: Reading text = the novel
slot, and questions re-filed by wording into Vowels / Basic grammar / …"""
import json
import uuid

import pytest

from models import db, Subject, MockJAMBQuestion
from models.mock_jamb import MockJAMBSyllabus

BP = [{"section": "comprehension", "label": "Comprehension passage", "count": 5, "passage": True, "per_passage": 5},
      {"section": "cloze", "label": "Cloze passage", "count": 10, "passage": True, "per_passage": 10},
      {"section": "reading_text", "label": "Reading text", "count": 5},
      {"section": "sentence_interpretation", "label": "Sentence interpretation", "count": 5},
      {"section": "antonyms", "label": "Antonyms", "count": 5},
      {"section": "synonyms", "label": "Synonyms", "count": 5},
      {"section": "basic_grammar", "label": "Basic grammar", "count": 10},
      {"section": "vowels", "label": "Vowels", "count": 2},
      {"section": "consonants", "label": "Consonants", "count": 2},
      {"section": "rhymes", "label": "Rhymes", "count": 2},
      {"section": "word_stress", "label": "Word stress", "count": 2},
      {"section": "emphatic_stress", "label": "Emphatic stress", "count": 2}]


def test_rule_section_wordings():
    from utils.english_sections import rule_section as r
    assert r('Choose the word that has the same vowel sound as the one underlined') == 'vowels'
    assert r('Choose the word that has the same consonant sound as the underlined') == 'consonants'
    assert r('Choose the option that rhymes with the given word') == 'rhymes'
    assert r('Choose the word that has a different stress pattern from the others') == 'word_stress'
    assert r('The word in capital letters has the emphatic stress. Choose the option to which the sentence relates') == 'emphatic_stress'
    assert r('Choose the option opposite in meaning to the word in italics') == 'antonyms'
    assert r('Choose the option nearest in meaning to the word in italics') == 'synonyms'
    assert r('Choose the option that best explains the information conveyed in the sentence') == 'sentence_interpretation'
    assert r('Choose the option that best completes the gap: He ____ to school') == 'basic_grammar'
    assert r('Who is Mr Bepo?') is None


@pytest.fixture
def imported_english(app):
    import utils.english_sections as es
    with app.app_context():
        subj = Subject.query.filter_by(name='English').first()
        if subj is None:
            subj = Subject(name='English', is_active=False); db.session.add(subj); db.session.flush()
        syl = MockJAMBSyllabus(subject_id=subj.id, subject_name='English', code='T-ENG', blueprint=json.dumps(BP))
        db.session.add(syl); db.session.commit()
        es._CACHE.update(at=0, sec={})
        yield subj
        db.session.delete(syl); db.session.commit()
        es._CACHE.update(at=0, sec={})


def test_reading_text_is_the_novel_slot(app, imported_english):
    from utils.jamb_blueprint import sections_for, blueprint_for
    with app.app_context():
        secs = {s['section']: s['label'] for s in sections_for('English')}
        assert secs.get('novel') == 'Reading text' and 'reading_text' not in secs
        bp = blueprint_for('English', {'reading_text': 7})          # old per-mock override key still applies
        assert next(s for s in bp['sections'] if s['section'] == 'novel')['count'] == 7


def test_sort_bank_files_into_imported_sections(app, imported_english):
    from utils.english_sections import sort_bank
    with app.app_context():
        subj = imported_english
        t = uuid.uuid4().hex[:5]

        def q(text, sec):
            return MockJAMBQuestion(mock_exam_id=None, subject_id=subj.id, section=sec, topic=None, exam_year='2020',
                                    question_text=f'{text} {t}', option_a='a', option_b='b', option_c='c', option_d='d',
                                    correct_option='A', marks=1)
        rows = [q('Choose the word that has the same vowel sound as the one underlined: seat', 'oral'),
                q('Choose the option that best completes the gap: He ____ to school daily', 'lexis_structure'),
                q('Choose the option opposite in meaning to the word in italics', 'synonyms'),   # misfiled
                q('Why was Mr Ayesoro transferred?', 'novel'),
                q('He bought a typewriter with a view .... to type', 'antonyms'),               # dots = a gap
                q('Lagos is a big city', 'oral')]                                                # no clue
        db.session.add_all(rows); db.session.commit()
        moves, _s, stuck = sort_bank(subj, apply=False, log=lambda *a: None)
        assert db.session.get(MockJAMBQuestion, rows[0].id).section == 'oral'                   # dry run
        sort_bank(subj, apply=True, log=lambda *a: None)
        g = [db.session.get(MockJAMBQuestion, r.id).section for r in rows]
        assert g[:5] == ['vowels', 'basic_grammar', 'antonyms', 'novel', 'basic_grammar']
        assert g[5] == 'oral' and stuck['oral'] >= 1                                            # left for a person
        for r in rows:
            db.session.delete(db.session.get(MockJAMBQuestion, r.id))
        db.session.commit()


def test_classify_uses_imported_sections(app, imported_english):
    from utils import myschool as ms
    with app.app_context():
        assert ms.classify('English', 'Choose the word that has the same vowel sound as the underlined')[0] == 'vowels'
        assert ms.classify('English', 'Choose the option that best completes the gap: She ____ here')[0] == 'basic_grammar'
        assert ms.classify('English', 'What did Mr Bepo tell the staff?', year=2025)[0] == 'novel'


def test_coded_tag_places_english_section_by_wording(app, imported_english):
    """After a coded tag, an English question's section follows its wording;
    Novel questions never move; nothing is guessed."""
    from utils.mock_bank_coded_retag import place_section
    from utils.jamb_blueprint import sections_for
    with app.app_context():
        valid = {s['section'] for s in sections_for('English')}

        class R:
            def __init__(self, text, sec):
                self.question_text, self.section, self.exam_year = text, sec, '2020'
                self.option_a = self.option_b = self.option_c = self.option_d = ''
        node = type('N', (), {'blueprint_section': None, 'parent_id': None, 'id': -1})()
        a = R('Choose the word that has the same vowel sound as the underlined', 'oral'); place_section(a, 'English', node, {}, valid)
        b = R('Why was Mr Ayesoro transferred?', 'novel'); place_section(b, 'English', node, {}, valid)
        c = R('Lagos is a big city', 'synonyms'); place_section(c, 'English', node, {}, valid)
        assert (a.section, b.section, c.section) == ('vowels', 'novel', 'synonyms')


def test_old_ai_retag_never_guesses_sections():
    import inspect
    import utils.mock_bank_ai_retag as ai
    import utils.mock_bank_local_tag as lt
    for mod in (ai, lt):
        assert 'sum(ord(c)' not in inspect.getsource(mod)          # the old hash 'guess'


def test_bundled_syllabi_map_every_sectioned_subject():
    """Every bundled syllabus whose subject has paper sections maps each of its
    sections (or all their topics) to one, so coded tags give a section."""
    import glob
    from utils.jamb_blueprint import JAMB_BLUEPRINT, _EXTRA_SECTIONS, norm_subject
    for f in glob.glob('data/jamb_syllabi/*.json'):
        d = json.load(open(f))
        key = norm_subject(d.get('subject') or f.split('/')[-1][:-5].replace('_', ' '))
        has_sections = bool(d.get('blueprint')) or key in JAMB_BLUEPRINT or _EXTRA_SECTIONS.get(key)
        if not has_sections or key == 'english language':        # English: by wording
            continue
        for s in d['sections']:
            assert s.get('blueprint_section') or all(t.get('blueprint_section') for t in s.get('topics', [])), (f, s['code'])


def test_resection_from_codes_without_ai(app):
    """A coded Biology question in the wrong section is moved by its code alone."""
    from utils.jamb_syllabus_import import import_syllabus
    from utils.syllabus_sections import resection, sync_mappings
    from models import MockJAMBSyllabusNode
    with app.app_context():
        subj = Subject.query.filter_by(name='Biology').first()
        if subj is None:
            subj = Subject(name='Biology', is_active=True); db.session.add(subj); db.session.commit()
        if not MockJAMBSyllabus.query.filter_by(subject_id=subj.id).first():
            import_syllabus(subj, open('data/jamb_syllabi/biology.json').read(), fmt='json')
        syl = MockJAMBSyllabus.query.filter_by(subject_id=subj.id).first()
        # forget the mappings, as on a server that imported before they existed
        nodes = MockJAMBSyllabusNode.query.filter_by(syllabus_id=syl.id).all()
        saved = {n.id: n.blueprint_section for n in nodes}
        for n in nodes:
            n.blueprint_section = None
        db.session.commit()
        code = next(n.code for n in nodes if n.code.endswith('FRM.2'))          # Nutrition
        q = MockJAMBQuestion(mock_exam_id=None, subject_id=subj.id, section='ecology', syllabus_item_code=code,
                             question_text='Which enzyme digests starch? ' + uuid.uuid4().hex[:5], option_a='a',
                             option_b='b', option_c='c', option_d='d', correct_option='A', marks=1)
        db.session.add(q); db.session.commit()
        assert sync_mappings(subj) > 0
        moves, _s = resection(subj, apply=False)
        assert db.session.get(MockJAMBQuestion, q.id).section == 'ecology'           # dry run
        assert moves['ecology -> nutrition'] >= 1
        resection(subj, apply=True)
        assert db.session.get(MockJAMBQuestion, q.id).section == 'nutrition'
        db.session.delete(db.session.get(MockJAMBQuestion, q.id))
        for n in MockJAMBSyllabusNode.query.filter_by(syllabus_id=syl.id).all():
            n.blueprint_section = saved.get(n.id)
        db.session.commit()
