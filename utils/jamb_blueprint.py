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
import json
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
        'financialaccounting': 'accounting', 'principlesofaccounts': 'accounting',
        'principlesofaccount': 'accounting', 'principleofaccounts': 'accounting',
        'poa': 'accounting', 'agric': 'agricultural science',
        'agriculture': 'agricultural science', 'civic': 'civic education',
        'civics': 'civic education',
        # Computer Studies is often renamed Digital Technologies / ICT / Computer Science.
        'computerstudies': 'computer studies', 'computerscience': 'computer studies',
        'digitaltechnology': 'computer studies', 'digitaltechnologies': 'computer studies',
        'ict': 'computer studies', 'computer': 'computer studies',
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
    # Real UTME Use of English (60), in the order JAMB presents them:
    # Section A — Comprehension & Summary (25): Comprehension (2 passages, 10) +
    # Cloze (1 passage, 5) + the Prescribed Reading text / recommended Novel (10).
    # Section B — Lexis & Structure (25): Sentence Interpretation (5), Synonyms (5),
    # Antonyms (5), Sentence Completion (10, where register questions now live).
    # Section C — Oral English / Test of Orals (10).
    'english language': {
        'total': 60,
        'sections': [
            _sec('comprehension', 'Comprehension', 10, passage=True, per_passage=5),
            _sec('cloze', 'Cloze passage', 5, passage=True, per_passage=5),
            _sec('novel', 'Recommended Novel / reading text', 10),
            _sec('sentence_interpretation', 'Sentence Interpretation', 5),
            _sec('synonyms', 'Synonyms', 5),
            _sec('antonyms', 'Antonyms', 5),
            _sec('lexis_structure', 'Sentence Completion (Lexis & Structure)', 10),
            _sec('oral', 'Test of Orals', 10),
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
    # JAMB Literature in English (50): literary appreciation/theory plus the
    # recommended texts across the three genres — Prose (the novels), Drama (the
    # plays) and Poetry. Counts are indicative and editable per mock.
    'literature in english': {
        'total': 50,
        'sections': [
            _sec('appreciation', 'Literary appreciation & terms', 14),
            _sec('prose', 'Prose (novels)', 12),
            _sec('drama', 'Drama (plays)', 12),
            _sec('poetry', 'Poetry', 12),
        ],
    },
}

DEFAULT_BLUEPRINT = {'total': 40, 'sections': [_sec('general', 'General', 40)]}

# Section catalogue for the bank authoring UI (subject → [{section, label, passage}]).
# Sciences/maths reuse their blueprint sections; a couple of humanities get a
# richer catalogue than their (flat) draw blueprint so questions can still be
# tagged meaningfully.
_EXTRA_SECTIONS = {
    # JAMB folds register vocabulary into Lexis & Structure (no separate slot), so
    # 'registers' and 'summary' are taggable extras at count 0 — give them a per-mock
    # count if you want them drawn as their own section.
    'english language': [_sec('summary', 'Summary', 0), _sec('registers', 'Registers', 0)],
}


# An imported syllabus may name a section differently from the app's built-in
# key. "Reading text" (reading_text) is the recommended-novel slot: it is mapped
# to the app's ``novel`` section so novel questions count, are drawn and are
# filtered to the mock's chosen book exactly as for the built-in plan.
SECTION_ALIASES = {'reading_text': 'novel', 'recommended_novel': 'novel', 'prescribed_text': 'novel'}


def canon_section(section):
    s = (section or '').strip()
    return SECTION_ALIASES.get(s, s)


def imported_blueprint(subject_name):
    """The blueprint from an admin-imported syllabus for this subject, or None.

    Imported syllabi (data, not code) take priority over the built-in defaults so
    the per-subject question distribution comes from what the school imported.
    DB access is guarded so this stays usable outside a request/app context.
    """
    try:
        from models import Subject, MockJAMBSyllabus
        key = norm_subject(subject_name)
        row = (MockJAMBSyllabus.query.join(Subject, MockJAMBSyllabus.subject_id == Subject.id)
               .filter(MockJAMBSyllabus.blueprint.isnot(None)).all())
        for s in row:
            if norm_subject(s.subject_name or (s.subject.name if s.subject else '')) == key:
                secs = json.loads(s.blueprint)
                if secs:
                    return [_sec(canon_section(x['section']), x.get('label', x['section']), int(x.get('count', 0)),
                                 bool(x.get('passage')), int(x.get('per_passage') or 5)) for x in secs]
    except Exception:
        pass
    return None


def blueprint_for(subject_name, override=None):
    """Return this subject's blueprint (a deep-ish copy), with any per-mock
    ``override`` — a ``{section: count}`` map — applied to the counts. An imported
    syllabus's blueprint wins over the built-in default when present."""
    imported = imported_blueprint(subject_name)
    if imported is not None:
        sections = [dict(s) for s in imported]
    else:
        base = JAMB_BLUEPRINT.get(norm_subject(subject_name), DEFAULT_BLUEPRINT)
        sections = [dict(s) for s in base['sections']]
    if override:
        override = {canon_section(k): v for k, v in override.items()}
        for s in sections:
            if s['section'] in override and override[s['section']] is not None:
                try:
                    s['count'] = max(0, int(override[s['section']]))
                except (TypeError, ValueError):
                    pass
    if norm_subject(subject_name) == 'english language':
        sections = _force_total(sections, ENGLISH_TOTAL)
    total = sum(s['count'] for s in sections)
    return {'total': total, 'sections': sections}


# Use of English is ALWAYS a 60-question paper. A per-mock override or an
# imported syllabus may move questions between sections, but never change the
# paper size — the difference is put back on / taken off the stand-alone sections.
ENGLISH_TOTAL = 60


def _force_total(sections, target):
    total = sum(s['count'] for s in sections)
    if total == target or not sections:
        return sections
    flex = [s for s in sections if not s['passage']] or sections
    if total < target:
        pref = next((s for s in flex if s['section'] == 'lexis_structure'), None) or max(flex, key=lambda s: s['count'])
        pref['count'] += target - total
        return sections
    extra = total - target
    for s in sorted(flex, key=lambda s: -s['count']):
        take = min(extra, s['count'])
        s['count'] -= take
        extra -= take
        if not extra:
            break
    return sections


def blueprint_total(subject_name, override=None):
    """The number of questions a full paper for this subject should have (sum of
    the blueprint section counts, honouring any per-mock override). 0 if the
    subject has no JAMB blueprint. Used as the hard cap so a paper never serves
    the whole bank when the questions aren't section-tagged."""
    if norm_subject(subject_name) not in JAMB_BLUEPRINT and imported_blueprint(subject_name) is None:
        return 0
    return blueprint_for(subject_name, override)['total']


def sections_for(subject_name):
    """The taggable sections for a subject in the bank UI: its blueprint sections
    (plus any extra catalogue entries), each ``{section, label, passage}``."""
    key = norm_subject(subject_name)
    out = []
    seen = set()
    # An imported syllabus's blueprint defines the taggable sections when present.
    imported = imported_blueprint(subject_name)
    base = None if imported is not None else JAMB_BLUEPRINT.get(key)
    for s in (imported or (base['sections'] if base else [])):
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


def _draw_balanced(pool, want, rng, item_topic_map):
    """Sample ``want`` questions from ``pool``, spread evenly across the coded
    syllabus topics present in it (round-robin), then backfill any remainder
    from the questions ``item_topic_map`` doesn't cover. With no coded tagging
    on the pool this reduces to a plain shuffle-and-take, identical to the
    pre-coded-syllabus behaviour."""
    if not item_topic_map:
        pool = list(pool)
        rng.shuffle(pool)
        return pool[:want]

    by_topic, uncoded = {}, []
    for q in pool:
        topic = item_topic_map.get(q.syllabus_item_code)
        (by_topic.setdefault(topic, []) if topic else uncoded).append(q)

    chosen = []
    if by_topic:
        topics = list(by_topic.keys())
        rng.shuffle(topics)
        for lst in by_topic.values():
            rng.shuffle(lst)
        i, empty_streak = 0, 0
        while len(chosen) < want and empty_streak < len(topics):
            t = topics[i % len(topics)]
            i += 1
            if by_topic[t]:
                chosen.append(by_topic[t].pop())
                empty_streak = 0
            else:
                empty_streak += 1
    if len(chosen) < want:
        rng.shuffle(uncoded)
        chosen.extend(uncoded[:want - len(chosen)])
    return chosen


# Reading sections that can stand in for each other when one runs short.
_PASSAGE_ALTERNATES = {'summary': ('comprehension',), 'comprehension': ('summary',)}


def draw_paper(blueprint, passages_by_section, questions_by_section, rng, arrange=False,
               item_topic_map=None):
    """Draw a JAMB-shaped paper for one subject.

    ``passages_by_section``: ``{section: [{'passage': p, 'questions': [q,...]}]}``
    ``questions_by_section``: ``{section: [q, ...]}`` (stand-alone questions)
    ``rng``: a seeded ``random.Random`` (per candidate → per-student papers).
    ``arrange``: keep the paper in blueprint *section order* (Comprehension →
    Cloze → … → Orals) instead of shuffling sections together — JAMB presents Use
    of English this way. Per-candidate variety still comes from which questions are
    sampled and the per-question option shuffle, so papers stay unique.
    ``item_topic_map``: optional ``{syllabus_item_code: topic_key}`` from the
    subject's imported coded syllabus. When given, stand-alone sections spread
    their draw evenly across the coded topics present (instead of a flat random
    sample), backfilling from not-yet-coded questions to still reach the
    section's target — so retagging a subject's bank incrementally improves
    balance without ever shrinking an under-tagged paper. Passage sections are
    unaffected (a passage's questions are always kept together).

    Returns ``(items, served_ids)`` where items are ``{'kind':'passage', 'passage', 'questions'}``
    or ``{'kind':'question', 'q'}`` (passages kept whole).
    A section short of stock draws what it has; a short reading section borrows
    from its sister section (summary <-> comprehension), and any remaining gap is
    topped up from the other stand-alone sections so the paper still reaches the
    blueprint total when the bank holds enough questions.
    """
    # Draw section by section (kept per section so a top-up lands in its own
    # section and an arranged paper keeps JAMB's order).
    per_sec = {}
    used_passages, used_q = set(), set()

    def take_passages(groups, want, out):
        taken = 0
        groups = [g for g in groups if id(g['passage']) not in used_passages]
        rng.shuffle(groups)
        for g in groups:
            if taken >= want:
                break
            qs = [q for q in g['questions'] if q.id not in used_q]
            rng.shuffle(qs)
            # keep the passage, but never overshoot the section target — trim the
            # last passage's questions to the remaining need (e.g. a scraped
            # 10-blank cloze passage under a 5-question cloze section serves 5).
            qs = qs[:want - taken]
            if not qs:
                continue
            used_passages.add(id(g['passage']))
            used_q.update(q.id for q in qs)
            out.append({'kind': 'passage', 'passage': g['passage'], 'questions': qs})
            taken += len(qs)
        return taken

    target = 0
    for sec in blueprint['sections']:
        want = sec['count']
        if want <= 0:
            continue
        target += want
        out = per_sec.setdefault(sec['section'], [])
        if sec['passage']:
            got = take_passages(passages_by_section.get(sec['section'], []), want, out)
            # short of its own passages: a sister reading section serves the rest
            # (summary questions are set on comprehension passages, and vice versa)
            for alt in _PASSAGE_ALTERNATES.get(sec['section'], ()):
                if got >= want:
                    break
                got += take_passages(passages_by_section.get(alt, []), want - got, out)
        else:
            pool = [q for q in questions_by_section.get(sec['section'], []) if q.id not in used_q]
            for q in _draw_balanced(pool, want, rng, item_topic_map):
                used_q.add(q.id)
                out.append({'kind': 'question', 'q': q})

    # Still short (a section had too few questions): top the paper up to its
    # blueprint total from the other stand-alone sections, largest first, so
    # every candidate gets a full-length paper. The novel section is never used
    # for this -- it is limited to the mock's own book.
    def n_served():
        return sum(len(it['questions']) if it['kind'] == 'passage' else 1
                   for lst in per_sec.values() for it in lst)

    short = target - n_served()
    if short > 0:
        donors = sorted((s for s in blueprint['sections']
                         if s['count'] > 0 and not s['passage'] and s['section'] != 'novel'),
                        key=lambda s: -s['count'])
        spare = {}
        for s in donors:
            pool = [q for q in questions_by_section.get(s['section'], []) if q.id not in used_q]
            rng.shuffle(pool)
            spare[s['section']] = pool
        while short > 0 and any(spare.values()):
            for s in donors:
                if short <= 0:
                    break
                if spare[s['section']]:
                    q = spare[s['section']].pop()
                    used_q.add(q.id)
                    per_sec.setdefault(s['section'], []).append({'kind': 'question', 'q': q})
                    short -= 1
        # Last resort: stand-alone questions filed under a section this blueprint
        # doesn't draw (not yet sorted into the syllabus's sections, e.g.
        # 'general'). They go at the end of the paper.
        if short > 0:
            drawn = {s['section'] for s in blueprint['sections']}
            rest = [q for sec, qs in questions_by_section.items()
                    if sec not in drawn and sec != 'novel' for q in qs if q.id not in used_q]
            rng.shuffle(rest)
            for q in rest[:short]:
                used_q.add(q.id)
                per_sec.setdefault('__other__', []).append({'kind': 'question', 'q': q})

    items = [it for sec in blueprint['sections'] for it in per_sec.pop(sec['section'], [])] + per_sec.pop('__other__', [])

    if not arrange:
        rng.shuffle(items)
    served = set()
    for it in items:
        if it['kind'] == 'passage':
            for q in it['questions']:
                served.add(q.id)
        else:
            served.add(it['q'].id)
    return items, served
