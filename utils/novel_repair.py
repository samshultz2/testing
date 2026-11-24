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


def repair(subject, apply=False, use_myschool=True, log=print, limit_samples=12):
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
        verdict = _myschool_verdict(q, subject, session, cache) if use_myschool else None
        if verdict is None:
            is_novel, title, how = ms.looks_like_novel_question(q.question_text), None, 'wording'
        else:
            (is_novel, title), how = verdict, 'myschool'
        stats['checked_' + how] += 1
        if is_novel:
            if _title_ok(q.topic) and not title:
                note('kept (already titled)', q, q.topic)
                continue
            new = (title or '').strip() or ms.novel_for_year(q.exam_year) or None
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
    return stats, samples
