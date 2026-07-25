"""Auto-tag untagged central-bank questions.

Runs the keyword classifier over the bank questions that carry no topic (usually
pasted / imported / legacy rows, or harvested questions that reached the bank
before their subject's syllabus keywords were rich enough) and fills in the
topic/sub-topic — and a missing section — but ONLY on a genuine keyword match, so
a question is never given a made-up tag. Safe to re-run; it only ever adds tags,
never overwrites an existing one.
"""
from __future__ import annotations


def _cap(v, n):
    return v[:n] if isinstance(v, str) else v


def untagged_count(subject):
    """How many stand-alone bank questions for a subject have no topic."""
    from models import MockJAMBQuestion
    return (MockJAMBQuestion.query
            .filter(MockJAMBQuestion.subject_id == subject.id,
                    MockJAMBQuestion.mock_exam_id.is_(None),
                    (MockJAMBQuestion.topic.is_(None)) | (MockJAMBQuestion.topic == ''))
            .count())


def retag_untagged(subject, fill_section=True, batch=500):
    """Classify every untagged bank question for ``subject`` and set its topic /
    sub-topic (and a missing section) where the classifier is confident.

    Returns ``{scanned, topic_set, section_set, still_untagged}``.
    """
    from models import db, MockJAMBQuestion
    from utils import myschool as ms
    from utils.jamb_blueprint import sections_for

    valid_sections = {s['section'] for s in sections_for(subject.name)}
    q = (MockJAMBQuestion.query
         .filter(MockJAMBQuestion.subject_id == subject.id,
                 MockJAMBQuestion.mock_exam_id.is_(None),
                 (MockJAMBQuestion.topic.is_(None)) | (MockJAMBQuestion.topic == ''))
         .order_by(MockJAMBQuestion.id))

    scanned = topic_set = section_set = 0
    pending = 0
    for row in q.yield_per(batch):
        scanned += 1
        text = ' '.join(filter(None, [
            row.question_text, row.option_a, row.option_b, row.option_c, row.option_d]))
        sec, top, sub = ms.classify_confident(subject.name, text, year=row.exam_year)
        if not top:
            continue                       # no confident match → leave untouched
        row.topic = _cap(top, 100)
        if sub:
            row.subtopic = _cap(sub, 120)
        topic_set += 1
        # fill a missing/invalid section from the same confident match so the
        # question also becomes drawable under the JAMB blueprint
        if fill_section and (row.section not in valid_sections) and sec in valid_sections:
            row.section = sec
            section_set += 1
        pending += 1
        if pending >= batch:
            db.session.commit()
            pending = 0
    if pending:
        db.session.commit()

    return {'scanned': scanned, 'topic_set': topic_set,
            'section_set': section_set, 'still_untagged': scanned - topic_set}
