"""The JAMB (UTME) paper blueprint — how many questions each subject draws from
each *section*, and which sections carry a shared passage.

Real UTME structure (what this encodes):
* **Use of English — 60 questions**, in the JAMB order: Comprehension passages,
  a Cloze passage, Lexis & Structure (synonyms/antonyms/sentence
  interpretation/completion), Test of Orals (vowels, consonants, stress,
  intonation) and Registers (subject-specific vocabulary).
* **Every other subject — 40 questions**, split across its syllabus sections
  (Mathematics: Number/Algebra/Geometry & Trig/Calculus/Statistics; the sciences
  by their main branches).

A *section* is the paper's structural grouping the draw samples from — distinct
from a syllabus topic (a section usually spans several topics). Each bank
question is tagged with its section so a mock can draw a JAMB-shaped, per-student
random paper from thousands of banked questions.

Subjects without an explicit blueprint fall back to a single ``general`` section
of 40 — the draw simply samples 40 from the subject's pool.
"""
from __future__ import annotations
import re


def norm_subject(name):
    """Casefold + de-punctuate + map the common Nigerian exam aliases so
    'Maths'/'MATHEMATICS ' and 'Use of English'/'English Language' collide."""
    key = re.sub(r'[^a-z0-9]', '', (name or '').lower())
    aliases = {
        'maths': 'mathematics', 'math': 'mathematics', 'mathematic': 'mathematics',
        'english': 'english language', 'useofenglish': 'english language',
        'englishlanguage': 'english language', 'lang': 'english language',
        'bio': 'biology', 'chem': 'chemistry', 'phy': 'physics', 'physic': 'physics',
        'econs': 'economics', 'econ': 'economics', 'govt': 'government', 'gov': 'government',
        'lit': 'literature in english', 'literatureinenglish': 'literature in english',
        'literature': 'literature in english', 'crs': 'christian religious studies',
        'crk': 'christian religious studies', 'geo': 'geography', 'accounts': 'accounting',
        'financialaccounting': 'accounting', 'agric': 'agricultural science',
        'agriculture': 'agricultural science', 'civic': 'civic education',
        'civics': 'civic education',
    }
    if key in aliases:
        return aliases[key]
    return ' '.join(re.findall(r'[a-z]+|[0-9]+', (name or '').lower())).strip()


# A section entry: (section key, label, count, needs_passage, questions_per_passage)
def _sec(key, label, count, passage=False, per_passage=5):
    return {'section': key, 'label': label, 'count': count,
            'passage': passage, 'per_passage': per_passage}


# ---------------------------------------------------------------------------
# per-subject blueprints (section → count), reflecting the real UTME paper
# ---------------------------------------------------------------------------
JAMB_BLUEPRINT = {
    # Real UTME Use of English (60): Comprehension (3 passages) + Cloze
    # (1 passage) + Sentence Interpretation + Antonyms + Synonyms + Lexis &
    # Structure (sentence completion) + Test of Orals + questions on the
    # recommended Novel/reading text. Counts vary slightly by year and are
    # editable per mock; they sum to 60 here.
    'english language': {
        'total': 60,
        'sections': [
            _sec('comprehension', 'Comprehension', 15, passage=True, per_passage=5),
            _sec('cloze', 'Cloze passage', 10, passage=True, per_passage=10),
            _sec('sentence_interpretation', 'Sentence Interpretation', 8),
            _sec('antonyms', 'Antonyms', 4),
            _sec('synonyms', 'Synonyms', 4),
            _sec('lexis_structure', 'Lexis & Structure', 4),
            _sec('oral', 'Test of Orals', 5),
            _sec('novel', 'Recommended Novel', 10),
        ],
    },
    'mathematics': {
        'total': 40,
        'sections': [
            _sec('number', 'Number & Numeration', 10),
            _sec('algebra', 'Algebra', 12),
            _sec('geometry', 'Geometry & Trigonometry', 10),
            _sec('calculus', 'Calculus', 4),
            _sec('statistics', 'Statistics', 4),
        ],
    },
    'physics': {
        'total': 40,
        'sections': [
            _sec('measurement', 'Measurement & Units', 2),
            _sec('mechanics', 'Mechanics', 12),
            _sec('thermal', 'Heat & Thermal Physics', 6),
            _sec('waves_optics', 'Waves & Optics', 8),
            _sec('electromagnetism', 'Electricity & Magnetism', 10),
            _sec('modern', 'Modern Physics', 2),
        ],
    },
    'chemistry': {
        'total': 40,
        'sections': [
            _sec('separation', 'Separation techniques', 2),
            _sec('atomic_bonding', 'Atomic structure & bonding', 6),
            _sec('stoichiometry', 'Mole concept & stoichiometry', 6),
            _sec('states_gas', 'States of matter & gas laws', 4),
            _sec('energetics_rates', 'Energetics, rates & equilibrium', 5),
            _sec('acids_bases_salts', 'Acids, bases & salts', 5),
            _sec('redox_electro', 'Redox & electrochemistry', 4),
            _sec('periodic_metals', 'Periodic table, metals & non-metals', 4),
            _sec('organic', 'Organic chemistry', 4),
        ],
    },
    'biology': {
        'total': 40,
        'sections': [
            _sec('cell', 'Cell biology & living organisms', 6),
            _sec('nutrition', 'Nutrition', 5),
            _sec('transport_respiration', 'Transport & respiration', 6),
            _sec('excretion_regulation', 'Excretion & regulation', 4),
            _sec('support_movement', 'Support & movement', 3),
            _sec('reproduction', 'Reproduction, growth & development', 5),
            _sec('ecology', 'Ecology', 6),
            _sec('genetics_evolution', 'Genetics & evolution', 5),
        ],
    },
}

DEFAULT_BLUEPRINT = {'total': 40, 'sections': [_sec('general', 'General', 40)]}

# Section catalogue for the bank authoring UI (subject → [{section, label, passage}]).
# Sciences/maths reuse their blueprint sections; a couple of humanities get a
# richer catalogue than their (flat) draw blueprint so questions can still be
# tagged meaningfully.
_EXTRA_SECTIONS = {
    'english language': [_sec('registers', 'Registers', 0), _sec('summary', 'Summary', 0)],
    'economics': [_sec('micro', 'Microeconomics', 0), _sec('macro', 'Macroeconomics', 0),
                  _sec('development', 'Development & public finance', 0),
                  _sec('international', 'International economics', 0)],
    'government': [_sec('concepts', 'Basic concepts', 0), _sec('constitution', 'Constitution & institutions', 0),
                   _sec('nigeria', 'Nigerian government & politics', 0),
                   _sec('international', 'International relations', 0)],
    'commerce': [_sec('trade', 'Trade & aids to trade', 0), _sec('business', 'Business organisations', 0),
                 _sec('finance', 'Finance & institutions', 0)],
    'accounting': [_sec('principles', 'Principles & double entry', 0), _sec('final', 'Final accounts', 0),
                   _sec('specialised', 'Specialised accounts', 0)],
    'geography': [_sec('physical', 'Physical geography', 0), _sec('human', 'Human geography', 0),
                  _sec('regional', 'Regional geography (Nigeria)', 0), _sec('practical', 'Practical & map work', 0)],
}


def blueprint_for(subject_name, override=None):
    """Return this subject's blueprint (a deep-ish copy), with any per-mock
    ``override`` — a ``{section: count}`` map — applied to the counts."""
    base = JAMB_BLUEPRINT.get(norm_subject(subject_name), DEFAULT_BLUEPRINT)
    sections = [dict(s) for s in base['sections']]
    if override:
        for s in sections:
            if s['section'] in override and override[s['section']] is not None:
                try:
                    s['count'] = max(0, int(override[s['section']]))
                except (TypeError, ValueError):
                    pass
    total = sum(s['count'] for s in sections)
    return {'total': total, 'sections': sections}


def sections_for(subject_name):
    """The taggable sections for a subject in the bank UI: its blueprint sections
    (plus any extra catalogue entries), each ``{section, label, passage}``."""
    key = norm_subject(subject_name)
    base = JAMB_BLUEPRINT.get(key)
    out = []
    seen = set()
    for s in (base['sections'] if base else []):
        out.append({'section': s['section'], 'label': s['label'], 'passage': s['passage']})
        seen.add(s['section'])
    for s in _EXTRA_SECTIONS.get(key, []):
        if s['section'] not in seen:
            out.append({'section': s['section'], 'label': s['label'], 'passage': False})
            seen.add(s['section'])
    if not out:
        out.append({'section': 'general', 'label': 'General', 'passage': False})
    return out


def section_label(subject_name, section):
    for s in sections_for(subject_name):
        if s['section'] == section:
            return s['label']
    return (section or 'General').replace('_', ' ').title()


def draw_paper(blueprint, passages_by_section, questions_by_section, rng):
    """Draw a JAMB-shaped paper for one subject.

    ``passages_by_section``: ``{section: [{'passage': p, 'questions': [q,...]}]}``
    ``questions_by_section``: ``{section: [q, ...]}`` (stand-alone questions)
    ``rng``: a seeded ``random.Random`` (per candidate → per-student papers).

    Returns ``(items, served_ids)`` where items are ``{'kind':'passage', 'passage', 'questions'}``
    or ``{'kind':'question', 'q'}`` in a shuffled order (passages kept whole).
    Sections short of stock draw whatever is available.
    """
    items = []
    for sec in blueprint['sections']:
        want = sec['count']
        if want <= 0:
            continue
        if sec['passage']:
            groups = list(passages_by_section.get(sec['section'], []))
            rng.shuffle(groups)
            taken = 0
            for g in groups:
                if taken >= want:
                    break
                qs = list(g['questions'])
                rng.shuffle(qs)
                items.append({'kind': 'passage', 'passage': g['passage'], 'questions': qs})
                taken += len(qs)
        else:
            pool = list(questions_by_section.get(sec['section'], []))
            rng.shuffle(pool)
            for q in pool[:want]:
                items.append({'kind': 'question', 'q': q})
    rng.shuffle(items)
    served = set()
    for it in items:
        if it['kind'] == 'passage':
            for q in it['questions']:
                served.add(q.id)
        else:
            served.add(it['q'].id)
    return items, served
