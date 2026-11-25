"""Repair the English bank's Novel section.

Earlier auto-tagging could (a) file questions it couldn't place into the Novel
section, and (b) overwrite real Novel questions' book title with a syllabus
heading. This sorts it out:

* a Novel-section question that really is about the novel stays, tagged with
  its book (myschool's own label when it can be re-read, else the novel set for
  its exam year);
* anything else moves back to the section its wording fits (or to no section,
  never a guess);
* a question tagged with a novel's title but filed elsewhere moves into Novel.

Downloaded questions are checked against their myschool.ng page (it says
whether a question is a novel question, and which book); others by wording.
``repair(subject, apply=False)`` only reports; ``apply=True`` saves.
"""
from collections import Counter


def _title_ok(topic):
    from utils.myschool import novel_catalogue, same_novel, is_generic_novel_tag
    t = (topic or '').strip()
    if not t or is_generic_novel_tag(t):
        return False
    return any(same_novel(c['value'], t) for c in novel_catalogue())


import re

# Wording that unmistakably marks a Use-of-English item from another section
# (vocabulary, oral, sentence completion, comprehension) — never a novel one.
_OTHER_SECTION = re.compile(
    r"nearest in meaning|closest in meaning|opposite in meaning|same meaning|in italics|underlined|"
    r"vowel sound|consonant sound|same sound|rhymes? with|stress(?:ed)? (?:on|syllable)|primary stress|"
    r"emphatic(?:ally)? stress|syllable|phonetic|correctly spelt|wrongly spelt|best completes|"
    r"completes? the (?:sentence|gap)|fill(?:s)? the gap|the gap|the blank|according to the passage|"
    r"in the passage|the writer of the passage|interpretation of the sentence|question tag", re.I)


def _clearly_other(text):
    return bool(_OTHER_SECTION.search(text or ''))


def _myschool_verdict(q, subject, session, cache):
    """(is_novel, title) from the question's myschool page, or None if it
    can't be checked (not a myschool question, or the page didn't load)."""
    from utils import myschool as ms
    ref = (q.source_ref or '').strip()
    year = (q.exam_year or '').strip()[:4]
    if (q.source or '') != 'myschool' or not ref.isdigit() or not year.isdigit():
        return None
    exam = {'JAMB': 'jamb', 'WAEC': 'waec', 'NECO': 'neco'}.get((q.exam_body or 'JAMB').upper(), 'jamb')
    slug = ms.subject_slug(subject.name)
    try:
        html = ms.fetch(ms.question_url(slug, exam, year, ref), session)
    except Exception:
        return None
    parsed = ms.parse_detail(html) if html else None
    if not parsed:
        return None
    if not parsed.get('is_novel'):
        return (False, None)
    title = parsed.get('novel_title')
    if not title:
        key = (slug, exam, year)
        if key not in cache:
            try:
                cache[key] = ms.scrape_novel_title(subject.name, exam, year, session)
            except Exception:
                cache[key] = None
        title = cache[key]
    return (True, title)


def repair(subject, apply=False, use_myschool=True, log=print, limit_samples=12, find_elsewhere=True, from_year=2010):
    from models import db, MockJAMBQuestion
    from utils import myschool as ms
    session = ms._session() if use_myschool else None
    cache, stats, samples = {}, Counter(), {}

    def note(kind, q, extra=''):
        stats[kind] += 1
        lst = samples.setdefault(kind, [])
        if len(lst) < limit_samples:
            lst.append('#%s %s | %s%s' % (q.id, q.exam_year or '----', (q.question_text or '')[:80].replace('\n', ' '),
                                          (' -> ' + extra) if extra else ''))

    base = MockJAMBQuestion.query.filter(MockJAMBQuestion.subject_id == subject.id,
                                         MockJAMBQuestion.mock_exam_id.is_(None),
                                         MockJAMBQuestion.passage_id.is_(None))
    rows = base.filter(MockJAMBQuestion.section == 'novel').order_by(MockJAMBQuestion.id).all()
    log('Checking %d Novel-section questions%s…' % (len(rows), ' (re-reading myschool.ng pages)' if use_myschool else ''))
    for i, q in enumerate(rows, 1):
        named = _title_in_text(q.question_text)
        verdict = (True, named) if named else (_myschool_verdict(q, subject, session, cache) if use_myschool else None)
        if verdict is None:
            # can't check the page: keep it as a novel question (and title it by
            # year) unless its wording clearly belongs to another section — real
            # novel questions often just name a character ("Who is Mr Mezie?")
            is_novel = ms.looks_like_novel_question(q.question_text) or not _clearly_other(q.question_text)
            title, how = None, 'wording'
        else:
            (is_novel, title), how = verdict, ('title' if named else 'myschool')
            if not is_novel:
                known = ms.book_from_characters(q.question_text)
                if known and ms.same_novel(known, ms.novel_for_year(q.exam_year) or '') \
                        and not _clearly_other(q.question_text):
                    is_novel, title = True, known
        stats['checked_' + how] += 1
        if is_novel:
            if _title_ok(q.topic) and not title:
                note('kept (already titled)', q, q.topic)
                continue
            new = (title or '').strip() or ms.book_from_characters(q.question_text) or ms.novel_for_year(q.exam_year) or None
            if new and not ms.same_novel(new, q.topic or ''):
                note('kept, titled', q, new)
                if apply:
                    q.topic = new[:100]; q.subtopic = None
            elif not new:
                note('kept, no title known (tag in the bank)', q)
                if apply and not _title_ok(q.topic):
                    q.topic = None
            else:
                note('kept (already titled)', q, q.topic)
        else:
            sec, top, sub = ms.classify_confident(subject.name, q.question_text)
            if sec == 'novel':
                sec = None
            note('moved out of Novel', q, sec or '(no section)')
            if apply:
                q.section = sec
                if sec:
                    q.topic = (top or q.topic or '')[:100] or None
                    q.subtopic = sub
        if apply and i % 50 == 0:
            db.session.commit()
        if i % 25 == 0:
            log('  …%d/%d' % (i, len(rows)))
    # questions titled with a novel but filed elsewhere
    for q in base.filter((MockJAMBQuestion.section.is_(None)) | (MockJAMBQuestion.section != 'novel')).all():
        if _title_ok(q.topic):
            note('moved into Novel (tagged with a novel)', q, q.topic)
            if apply:
                q.section = 'novel'
    if apply:
        db.session.commit()
    if find_elsewhere:
        _find_elsewhere(subject, base, apply, session, cache, note, log, from_year)
    return stats, samples


# ---------------------------------------------------------------- elsewhere
_NAME = re.compile(r"\b(?:(?:Mr|Mrs|Miss|Mallam|Malam|Alhaji|Chief|Dr|Prof|Aunty|Uncle)\.?\s+)?[A-Z][a-z]{2,}\b")
_NOT_NAMES = set('''The What Who Which When Where Why How According Choose Complete Fill From Select Identify
In On At Of For And But Or Not None All Both Each Every This That These Those His Her Their Its Our Your
January February March April May June July August September October November December Monday Tuesday
Wednesday Thursday Friday Saturday Sunday English Nigeria Nigerian Lagos Abuja God Allah Christmas
Book Novel Chapter Author Writer Narrator Story Text Question Following Option Options Answer Based
Life Changer Lekki Headmaster Last Days Forcados High School Sweet Sixteen Dependence Questions Schools
Independence Paragraph Passage Sentence Students Teacher Teachers Principal Black Day Group Heritage Hope
Kingdom Museum United States America Britain London Africa African Ibadan Badagry Ajegunle Ikeja Lekki Island
Victoria Yaba Ikoyi Japa School Church Mosque Hospital University College Bank Market Street Road State'''.split())


def _book_words():
    from utils.myschool import novel_catalogue
    out = set()
    for c in novel_catalogue():
        out.update(w.capitalize() for w in re.findall(r"[A-Za-z]+", c['value']))
    return out


def _names(text):
    out, skip = set(), _NOT_NAMES | _book_words()
    for m in _NAME.finditer(text or ''):
        w = m.group(0).split()[-1]
        if w in skip or w.capitalize() in skip:
            continue
        out.add(w)
    return out


def _words(text):
    return ' ' + ' '.join(re.sub(r"[^a-z0-9]+", " ", (text or '').lower()).split()) + ' '


def _title_in_text(text):
    """The recommended text named in a question, matched as whole words
    ("…based on The Lekki Headmaster…"); "Independence Day" is not "In Dependence"."""
    from utils.myschool import novel_catalogue
    w = _words(text)
    for c in novel_catalogue():
        t = _words(c['title']).strip()
        if t.startswith('the '):
            t = t[4:]
        if len(t) >= 6 and (' %s ' % t) in w:
            return c['value']
    return None


def _book_for_year(year):
    from utils.myschool import novel_for_year
    return novel_for_year(year)


def _find_elsewhere(subject, base, apply, session, cache, note, log, from_year):
    """Novel questions filed in other sections: found by the book's title in
    the question, by their myschool.ng page, or (pasted questions that can't be
    checked) by character names learned from the confirmed novel questions."""
    from models import db, MockJAMBQuestion
    from utils.myschool import same_novel
    pool = [q for q in base.filter((MockJAMBQuestion.section.is_(None)) | (MockJAMBQuestion.section != 'novel'))
            .order_by(MockJAMBQuestion.id).all()
            if str(q.exam_year or '')[:4].isdigit() and int(str(q.exam_year)[:4]) >= from_year
            or _title_in_text(q.question_text)]
    log('Looking for novel questions filed elsewhere among %d English questions from %d on…' % (len(pool), from_year))
    found, unchecked, page_no = [], [], []
    for i, q in enumerate(pool, 1):
        title = _title_in_text(q.question_text)
        if title:
            found.append((q, title, 'book named in the question')); continue
        v = _myschool_verdict(q, subject, session, cache) if session is not None else None
        if v is None:
            unchecked.append(q)
        elif v[0]:
            found.append((q, (v[1] or '').strip() or _book_for_year(q.exam_year), 'myschool page'))
        else:
            page_no.append(q)                 # page has no novel note: the school's character list may still tell
        if i % 50 == 0:
            log('  …%d/%d' % (i, len(pool)))
    # learn each book's character names from every confirmed novel question
    confirmed = [(q.question_text, q.topic) for q in base.filter(MockJAMBQuestion.section == 'novel').all()]
    confirmed += [(q.question_text, t) for q, t, _w in found if t]
    seen = {}
    for text, book in confirmed:
        for n in _names(text):
            seen.setdefault((book or '').strip(), {}).setdefault(n, 0)
            seen[(book or '').strip()][n] += 1
    merged = {}
    for b, d in seen.items():
        if not b:
            continue
        key = next((k for k in merged if same_novel(k, b)), b)
        for n, c in d.items():
            merged.setdefault(key, {}).setdefault(n, 0)
            merged[key][n] += c
    names = {b: {n for n, c in d.items() if c >= 2} for b, d in merged.items()}
    for b, ns in names.items():
        if ns:
            log('  names learned for %s: %s' % (b, ', '.join(sorted(ns)[:25])))
    from utils.myschool import book_from_characters
    for q in page_no:
        book, known = _book_for_year(q.exam_year), book_from_characters(q.question_text)
        if known and book and same_novel(known, book) and not _clearly_other(q.question_text):
            found.append((q, known, 'known character'))
    for q in unchecked:
        book = _book_for_year(q.exam_year)
        known = book_from_characters(q.question_text)
        if known and book and same_novel(known, book) and not _clearly_other(q.question_text):
            found.append((q, known, 'known character')); continue
        if not book:
            continue
        ns = next((v for b, v in names.items() if same_novel(b, book)), set())
        hit = _names(q.question_text) & ns
        if hit and not _clearly_other(q.question_text):
            found.append((q, book, 'character ' + ', '.join(sorted(hit))))
    for q, title, why in found:
        book = (title or 'untitled').split(' — ')[0]
        note('found in another section -> Novel: %s' % book, q, why)
        if apply:
            q.section = 'novel'
            if title:
                q.topic = title[:100]; q.subtopic = None
    if apply:
        db.session.commit()
