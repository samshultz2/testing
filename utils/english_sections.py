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

# A question on the recommended novel ("This question is based on Chukwuemeka
# Ike's The Potter's Wheel…", "In the novel, …", "According to the novel, …").
NOVEL_CUE = re.compile(
    r"(?:question|questions)\s+(?:is|are)\s+base[d]?\s+on\s+[A-Z][^.?]{0,40}?['’]s\s+[A-Z]|"
    r"\b(?:in|from|according to) the novel\b|inferred from the novel", _I)
_NOVEL_SRC = re.compile(
    r"base[d]?\s+on\s+(?P<author>[A-Z][\w.\-]*(?:\s+[A-Z][\w.\-]*){0,3})['’]s\s+"
    r"(?P<title>[A-Z][\w'’]*(?:\s+[\w'’]+){0,5}?)(?=\s*[.:,;?]|\s+(?:In|According|From|It|The\s+\w+\s+was|Who|What|Why|How)\b)")
# misspelt titles seen in the bank -> the real book
_NOVEL_ALIASES = {'the successes': 'The Successor'}


def novel_by_characters(text, year=None):
    """The recommended novel whose characters the question names, but only when
    the question's year (if known) is one of that book's years -- so a common
    name in a grammar sentence of another year doesn't pull it into Novel."""
    from utils import myschool as ms
    book = ms.book_from_characters(text)
    if not book:
        return None
    if year and str(year).strip():
        that_year = ms.novel_for_year(year)
        if not that_year or not ms.same_novel(that_year, book):
            return None
    return book


def novel_book(text, year=None):
    """Best 'Title — Author' for a novel question: named in it, else from its
    characters, else the recommended novel of its year."""
    from utils import myschool as ms
    return novel_source(text) or ms.book_from_characters(text) or ms.novel_for_year(year)


def novel_source(text):
    """'Title — Author' named in a "based on <Author>'s <Title>" question, matched
    to the recommended-novel list when it's a known book; else None."""
    from utils import myschool as ms
    m = _NOVEL_SRC.search(text or '')
    if not m:
        return None
    title = m.group('title').strip()
    title = _NOVEL_ALIASES.get(title.lower(), title)
    for b in ms.novel_catalogue():
        if ms.same_novel(b['value'], title):
            return b['value']
    return '%s — %s' % (title, m.group('author').strip())


RULES = [
    ('novel', NOVEL_CUE),
    ('emphatic_stress', re.compile(
        r"emphatic(?:ally)?\s+stress|emphatically stressed|in capital letters[^.?]{0,80}(?:stress|emphas|relates|answer)|"
        r"(?:stress|emphasis)[^.?]{0,60}in capital letters|carries the (?:emphatic|main) stress|"
        r"to which the (?:given )?sentence relates", _I)),
    ('word_stress', re.compile(
        r"primary stress|stressed syllable|stress pattern|correct(?:ly)? stress|wrong(?:ly)? stress|"
        r"stressed on the (?:first|second|third|fourth|last|final)|(?:first|second|third|last) syllable|"
        r"different stress|same (?:pattern of )?stress|syllable (?:is|that is) stressed|which (?:word|syllable) (?:is|carries)[^?]{0,40}stress", _I)),
    ('rhymes', re.compile(r"\brhymes?\b|\brhyming\b", _I)),
    ('consonants', re.compile(r"consonant", _I)),
    ('vowels', re.compile(r"\bvowel|diphthong|monophthong", _I)),
    ('antonyms', re.compile(r"opposite in meaning|most nearly opposite|\bantonym|opposite of the word|"
                            r"expresses the opposite|opposite meaning", _I)),
    ('synonyms', re.compile(
        r"(?:nearest|closest|same|similar) in meaning to the (?:word|words|underlined|italicized|expression|phrase|word\(s\))|"
        r"nearest in meaning to the word|\bsynonym|"
        # older JAMB wordings: "nearest meaning to the word or phrase underlined",
        # "best express(es) the meaning of the phrase or word underlined"
        r"nearest (?:in )?meaning (?:to|of) the (?:underline[ds]?|word|phrase|expression)|"
        r"best express(?:es)? the meaning of the (?:word|phrase|expression)|"
        r"meaning of the (?:word|phrase|expression)s?(?: or (?:word|phrase)s?)? underlined|"
        # 1978-80 papers: "best conveys the meaning of the underlined portion",
        # "has the same meaning as the underlined word or words"
        r"conveys? the meaning of the underlined|same meaning as the underlined", _I)),
    ('sentence_interpretation', re.compile(
        r"best explains? the (?:information|meaning|sentence)|information conveyed|interpretation of the sentence|"
        r"best interpretation|(?:the|this) sentence (?:means|implies)|(?:the|this) statement (?:means|implies)|"
        r"nearest in meaning to the (?:sentence|statement)|means that\b|is implied", _I)),
    ('basic_grammar', re.compile(
        r"best completes?|completes? (?:each of )?the (?:following )?(?:sentence|gap)|"
        r"fil{1,3}(?:s|ing)?(?:\(s\)|s\(s\))? (?:in )?the (?:gap|blank)|-{4,}|"
        r"(?:wrongly|correctly|incorrectly) spelt|spelling|correctly punctuated|punctuation|"
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
        if new != 'novel' and 'novel' in active and novel_by_characters(q.question_text, q.exam_year):
            new = 'novel'
        if new is None:
            if cur not in active:
                k = cur or '(no section)'
                stuck[k] += 1
                lst = samples.setdefault('stuck: ' + k, [])
                if len(lst) < limit_samples:
                    lst.append('#%s %s | %s' % (q.id, q.exam_year or '----',
                                                (q.question_text or '')[:110].replace('\n', ' ')))
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
            if new == 'novel':
                from utils import myschool as ms
                book = novel_book(q.question_text, q.exam_year)
                if book and (not (q.topic or '').strip() or ms.is_generic_novel_tag(q.topic)
                             or not any(ms.same_novel(q.topic, b['value']) for b in ms.novel_catalogue())):
                    q.topic = book
        if apply and i % 200 == 0:
            db.session.commit()
    if apply:
        db.session.commit()
    return moves, samples, stuck


# A summary question: what the passage / a paragraph is mainly about.
SUMMARY = re.compile(
    r"summar(?:y|ise|ize|ises|izes|ising|izing)|main (?:idea|point|theme|concern|argument|message)|"
    r"central (?:idea|theme|point|message)|(?:best|most suitable|most appropriate|suitable|appropriate) title|"
    r"(?:passage|paragraph|writer|author)(?:'s)? (?:is )?(?:mainly|chiefly|primarily|essentially) "
    r"(?:about|concerned)|the gist", _I)


def passage_section(body, stems):
    """The section a whole reading passage belongs in, from its text and all its
    questions' stems: 'cloze', 'summary' or 'comprehension'. Summary needs most
    of its questions to be summary questions (one "best title" question in an
    ordinary passage doesn't make it a summary passage)."""
    from utils import myschool as ms
    stems = [s or '' for s in stems]
    bare = sum(1 for s in stems if not s.strip() or ms._BARE_STEM.match(s.strip()))
    if ms.passage_kind(body, '') == 'cloze' or (stems and bare * 2 >= len(stems)):
        return 'cloze'
    if stems and sum(1 for s in stems if SUMMARY.search(s)) * 2 > len(stems):
        return 'summary'
    return 'comprehension'


def sort_passages(subject, apply=False, limit_samples=8):
    """Re-file the English bank's reading passages (and every question on them)
    as cloze / summary / comprehension. Novel passages are left alone. Only
    sections that exist in the subject's blueprint are used. Returns
    (moves Counter, samples {key: [lines]})."""
    from collections import Counter
    from models import db, MockJAMBPassage, MockJAMBQuestion
    from utils.jamb_blueprint import canon_section
    active = active_sections(subject.name)
    moves, samples = Counter(), {}
    passages = (MockJAMBPassage.query.filter(MockJAMBPassage.subject_id == subject.id,
                                             MockJAMBPassage.mock_exam_id.is_(None))
                .order_by(MockJAMBPassage.id).all())
    for p in passages:
        qs = MockJAMBQuestion.query.filter(MockJAMBQuestion.passage_id == p.id).all()
        if canon_section(p.section) == 'novel' or any(canon_section(q.section) == 'novel' for q in qs):
            continue
        new = passage_section(p.body, [q.question_text for q in qs])
        if active and new not in active:
            new = 'comprehension' if 'comprehension' in active else None
        if not new:
            continue
        changed_q = [q for q in qs if (q.section or '') != new]
        if (p.section or '') == new and not changed_q:
            continue
        key = '%s -> %s' % (p.section or '(no section)', new)
        moves[key] += 1
        lst = samples.setdefault(key, [])
        if len(lst) < limit_samples:
            lst.append('passage #%s (%d q) | %s' % (p.id, len(qs), (p.body or '')[:90].replace('\n', ' ')))
        if apply:
            p.section = new
            p.kind = new
            for q in changed_q:
                q.section = new
    if apply:
        db.session.commit()
    return moves, samples


def grammar_audit(subject, limit_samples=12):
    """How the Basic grammar section was filled: questions whose wording says
    'complete the sentence / fill the gap' vs ones only put there by default
    (old 'Lexis and Structure' with no clear instruction). Returns
    (by_wording, by_default, samples_of_default)."""
    from models import MockJAMBQuestion
    rows = (MockJAMBQuestion.query.filter(MockJAMBQuestion.subject_id == subject.id,
                                          MockJAMBQuestion.mock_exam_id.is_(None),
                                          MockJAMBQuestion.passage_id.is_(None),
                                          MockJAMBQuestion.section == 'basic_grammar')
            .order_by(MockJAMBQuestion.id).all())
    by_wording = by_default = 0
    samples = []
    for q in rows:
        if rule_section(q.question_text) == 'basic_grammar':
            by_wording += 1
        else:
            by_default += 1
            if len(samples) < limit_samples:
                samples.append('#%s %s | %s' % (q.id, q.exam_year or '----',
                                                (q.question_text or '')[:110].replace('\n', ' ')))
    return by_wording, by_default, samples
