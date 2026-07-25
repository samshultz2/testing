"""Auto-tag / re-tag central-bank questions with the keyword classifier.

Modes:
* ``untagged`` (default, safe): only fills in questions that have no topic.
* ``all``: re-classifies every stand-alone bank question so improved syllabus
  keywords upgrade existing auto-tags — but only overwrites when the classifier
  is confident, so a question is never blanked or given a made-up topic.

Passage-bound questions (comprehension/cloze/novel) are never touched — their
section is structural and their topic is legitimately empty.

``ensure_section`` (opt-in) additionally gives any still-unmatched question a
valid, deterministic blueprint section so it is drawable in exams — reaching
full *usable* coverage even where a precise topic can't truthfully be assigned.
"""
from __future__ import annotations


def _cap(v, n):
    return v[:n] if isinstance(v, str) else v


def _target_ids(subject, mode):
    """Primary keys of the bank questions to (re)tag, fully materialised up front —
    so we never hold a server-side cursor open across the per-chunk commits (which
    would invalidate it: psycopg InvalidCursorName)."""
    from models import db, MockJAMBQuestion
    q = db.session.query(MockJAMBQuestion.id).filter(
        MockJAMBQuestion.subject_id == subject.id,
        MockJAMBQuestion.mock_exam_id.is_(None),
        MockJAMBQuestion.passage_id.is_(None))       # never re-tag passage-bound questions
    if mode != 'all':
        q = q.filter((MockJAMBQuestion.topic.is_(None)) | (MockJAMBQuestion.topic == ''))
    return [row[0] for row in q.order_by(MockJAMBQuestion.id).all()]


def untagged_count(subject):
    """How many stand-alone bank questions for a subject have no topic."""
    from models import MockJAMBQuestion
    return (MockJAMBQuestion.query
            .filter(MockJAMBQuestion.subject_id == subject.id,
                    MockJAMBQuestion.mock_exam_id.is_(None),
                    MockJAMBQuestion.passage_id.is_(None),
                    (MockJAMBQuestion.topic.is_(None)) | (MockJAMBQuestion.topic == ''))
            .count())


def _drawable_sections(subject):
    """Valid, non-passage blueprint sections a stand-alone question can be filed
    under (so a fallback never dumps a question into a comprehension/cloze slot)."""
    from utils.jamb_blueprint import sections_for
    return [s['section'] for s in sections_for(subject.name) if not s['passage']] \
        or [s['section'] for s in sections_for(subject.name)]


def retag_untagged(subject, mode='untagged', fill_section=True, ensure_section=False, batch=500):
    """Classify a subject's bank questions and set topic/sub-topic (and section)
    where confident. Returns
    ``{scanned, topic_set, section_set, section_ensured, still_untagged}``.
    """
    from models import db, MockJAMBQuestion
    from utils import myschool as ms
    from utils.jamb_blueprint import sections_for

    valid_sections = {s['section'] for s in sections_for(subject.name)}
    draw_sections = _drawable_sections(subject)

    ids = _target_ids(subject, mode)
    scanned = topic_set = section_set = section_ensured = 0
    # Process in id-chunks, committing after each — never stream a server-side
    # cursor across commits (that invalidates it on Postgres).
    for start in range(0, len(ids), batch):
        chunk = ids[start:start + batch]
        rows = MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(chunk)).all()
        for row in rows:
            scanned += 1
            text = ' '.join(filter(None, [
                row.question_text, row.option_a, row.option_b, row.option_c, row.option_d]))
            sec, top, sub = ms.classify_confident(subject.name, text, year=row.exam_year)
            if top:
                row.topic = _cap(top, 100)
                row.subtopic = _cap(sub, 120) if sub else None
                topic_set += 1
                if fill_section and (row.section not in valid_sections) and sec in valid_sections:
                    row.section = sec
                    section_set += 1
            # last resort (opt-in): make an unmatched question drawable by giving it a
            # valid section, chosen deterministically so re-runs are stable
            if ensure_section and (row.section not in valid_sections) and draw_sections:
                row.section = draw_sections[sum(ord(c) for c in text) % len(draw_sections)]
                section_ensured += 1
        db.session.commit()

    return {'scanned': scanned, 'topic_set': topic_set, 'section_set': section_set,
            'section_ensured': section_ensured, 'still_untagged': scanned - topic_set}
