"""Use of English: place a question in the section of the ACTIVE blueprint from
its wording. JAMB words each question type consistently ("…opposite in meaning
to…", "…has the same vowel sound as…", "…the word in capital letters carries
the emphatic stress…"), so the instruction identifies the section reliably —
more reliably than keyword topics.

``rule_section(text)`` returns a section key or None (no clear instruction).
``fit_section(subject, section, text)`` returns a key that exists in the
subject's current blueprint (an imported syllabus may use finer sections such
as vowels / consonants / basic_grammar than the built-in oral / lexis_structure).
"""
import re
import time

_I = re.I
_IPA_VOWEL = re.compile(r"/[^/\s]*(?:ɪ|iː|æ|ɑː|ɒ|ɔː|ʊ|uː|ʌ|ɜː|ə|eɪ|aɪ|ɔɪ|əʊ|aʊ|ɪə|eə|ʊə)[^/\s]*/")
_IPA_CONS = re.compile(r"/[^/\s]*(?:θ|ð|ʃ|ʒ|tʃ|dʒ|ŋ|j|w|h|p|b|t|d|k|g|f|v|s|z|m|n|l|r)[^/\s]*/")

RULES = [
    ('emphatic_stress', re.compile(
        r"emphatic(?:ally)?\s+stress|emphatically stressed|in capital letters[^.?]{0,80}(?:stress|emphas|relates|answer)|"
        r"(?:stress|emphasis)[^.?]{0,60}in capital letters|carries the (?:emphatic|main) stress", _I)),
    ('word_stress', re.compile(
        r"primary stress|stressed syllable|stress pattern|correct(?:ly)? stress|wrong(?:ly)? stress|"
        r"stressed on the (?:first|second|third|fourth|last|final)|(?:first|second|third|last) syllable|"
        r"different stress|syllable (?:is|that is) stressed|which (?:word|syllable) (?:is|carries)[^?]{0,40}stress", _I)),
    ('rhymes', re.compile(r"\brhymes?\b|\brhyming\b", _I)),
    ('consonants', re.compile(r"consonant", _I)),
    ('vowels', re.compile(r"\bvowel|diphthong|monophthong", _I)),
    ('antonyms', re.compile(r"opposite in meaning|most nearly opposite|\bantonym|opposite of the word", _I)),
    ('synonyms', re.compile(
        r"(?:nearest|closest|same|similar) in meaning to the (?:word|words|underlined|italicized|expression|phrase|word\(s\))|"
        r"nearest in meaning to the word|\bsynonym", _I)),
    ('sentence_interpretation', re.compile(
        r"best explains? the (?:information|meaning|sentence)|information conveyed|interpretation of the sentence|"
        r"best interpretation|the sentence (?:means|implies)|the statement (?:means|implies)|"
        r"nearest in meaning to the (?:sentence|statement)|means that\b|is implied", _I)),
    ('basic_grammar', re.compile(
        r"best completes?|completes? (?:each of )?the (?:following )?(?:sentence|gap)|fill(?:s|ing)? (?:in )?the (?:gap|blank)|"
        r"most (?:appropriate|suitable)ly? (?:fills?|completes?)|question tag|correct (?:form|option) (?:of|to)|"
        r"grammatically correct|_{3,}|\.{4,}", _I)),
]

# A sound question that only shows the sound ("…the same sound as the
# underlined…") — decide vowel vs consonant from the phonetic symbol.
_SOUND = re.compile(r"same sound|different sound|the sound\b|sound (?:as|in)|pronounced", _I)


def rule_section(text):
    t = text or ''
    for sec, rx in RULES:
        if rx.search(t):
            return sec
    if _SOUND.search(t):
        if _IPA_VOWEL.search(t):
            return 'vowels'
        if _IPA_CONS.search(t):
            return 'consonants'
    return None


# built-in broad keys -> the imported syllabus's nearest section, when only the
# finer ones exist
_FALLBACK = {'lexis_structure': ['basic_grammar'], 'oral': [], 'novel': ['novel'], 'reading_text': ['novel']}
_CACHE = {'at': 0, 'sec': {}}


def active_sections(subject_name):
    """Section keys of the subject's current blueprint (cached for a minute)."""
    now = time.monotonic()
    if now - _CACHE['at'] > 60:
        _CACHE.update(at=now, sec={})
    if subject_name not in _CACHE['sec']:
        try:
            from utils.jamb_blueprint import sections_for
            _CACHE['sec'][subject_name] = {s['section'] for s in sections_for(subject_name)}
        except Exception:
            _CACHE['sec'][subject_name] = set()
    return _CACHE['sec'][subject_name]


def fit_section(subject_name, section, text):
    """A section key valid for the subject's blueprint: the wording's clear
    section when there is one, else ``section`` itself if valid, else its
    nearest equivalent, else None (left for a person / the re-tagger)."""
    from utils.jamb_blueprint import canon_section
    active = active_sections(subject_name)
    section = canon_section(section)
    if section == 'novel':
        return 'novel'
    r = rule_section(text)
    if r and (not active or r in active):
        return r
    if not active or section in active:
        return section
    for alt in _FALLBACK.get(section or '', []):
        if alt in active:
            return alt
    return None


def sort_bank(subject, apply=False, log=print, limit_samples=8):
    """Re-file the English bank's stand-alone questions into the active
    blueprint's sections. A question moves only when its wording clearly names
    its section, or when its current section isn't in the blueprint (e.g. the
    built-in 'oral' / 'lexis_structure' under an imported syllabus). Novel and
    passage-bound questions are left alone. Returns (moves, samples, stuck)."""
    from collections import Counter
    from models import db, MockJAMBQuestion
    from utils.jamb_blueprint import canon_section
    active = active_sections(subject.name)
    rows = (MockJAMBQuestion.query.filter(MockJAMBQuestion.subject_id == subject.id,
                                          MockJAMBQuestion.mock_exam_id.is_(None),
                                          MockJAMBQuestion.passage_id.is_(None))
            .order_by(MockJAMBQuestion.id).all())
    moves, samples, stuck = Counter(), {}, Counter()
    for i, q in enumerate(rows, 1):
        cur = q.section or ''
        if canon_section(cur) == 'novel':
            if cur != 'novel' and apply:
                q.section = 'novel'
            continue
        new = fit_section(subject.name, cur or None, q.question_text)
        if new is None:
            if cur not in active:
                stuck[cur or '(no section)'] += 1
            continue
        if new == cur:
            continue
        key = '%s -> %s' % (cur or '(no section)', new)
        moves[key] += 1
        lst = samples.setdefault(key, [])
        if len(lst) < limit_samples:
            lst.append('#%s %s | %s' % (q.id, q.exam_year or '----', (q.question_text or '')[:90].replace('\n', ' ')))
        if apply:
            q.section = new
        if apply and i % 200 == 0:
            db.session.commit()
    if apply:
        db.session.commit()
    return moves, samples, stuck
