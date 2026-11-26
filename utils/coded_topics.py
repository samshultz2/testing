"""Topic / sub-topic names for Mock JAMB analytics, from the CODED syllabus.

A question that carries a syllabus code is reported under that code's topic
and item names. In a subject that has a coded syllabus, a question without a
code yet is grouped as "Not yet coded" (instead of whatever free-text topic it
was scraped with), so analytics only ever show the JAMB syllabus's own names.
A subject with no coded syllabus keeps its free-text topics.
"""
from __future__ import annotations

NOT_CODED = 'Not yet coded'


def label_maps(subject_ids):
    """({subject_id: {code: (topic, item)}}, set of subject ids with a coded syllabus).
    Cached for the current request (bulk imports call it once per question)."""
    ids = frozenset(s for s in subject_ids if s)
    try:
        from flask import g, has_app_context
        if has_app_context():
            cache = g.setdefault('_coded_label_maps', {})
            if ids not in cache:
                cache[ids] = _label_maps(ids)
            return cache[ids]
    except Exception:
        pass
    return _label_maps(ids)


def _label_maps(ids):
    from models import MockJAMBSyllabus, MockJAMBSyllabusNode
    maps, coded = {}, set()
    if not ids:
        return maps, coded
    sylls = MockJAMBSyllabus.query.filter(MockJAMBSyllabus.subject_id.in_(ids)).all()
    for syl in sylls:
        nodes = MockJAMBSyllabusNode.query.filter_by(syllabus_id=syl.id).all()
        by_id = {n.id: n for n in nodes}
        m = {}
        for n in nodes:
            # topic = nearest ancestor (or self) of kind 'topic', else the top part
            topic, cur, seen = None, n, set()
            while cur is not None and cur.id not in seen:
                seen.add(cur.id)
                if cur.kind == 'topic':
                    topic = cur
                    break
                if cur.parent_id is None:
                    topic = cur
                    break
                cur = by_id.get(cur.parent_id)
            t = (topic.name if topic else n.name) or n.code
            item = n.name if (n.kind == 'item' and topic is not n) else None
            m[n.code] = (t, item)
        maps[syl.subject_id] = m
        coded.add(syl.subject_id)
    return maps, coded


def label(subject_id, code, topic, subtopic, maps, coded):
    """(topic, subtopic) to report a question under."""
    m = maps.get(subject_id)
    if m and code and code in m:
        return m[code]
    if subject_id in coded:
        return NOT_CODED, None
    return topic, subtopic


def coded_tree(subject_id):
    """The authoring pickers' topic tree for a subject with a coded syllabus,
    in the shape of routes.cbt._subject_topic_tree: [{id, title, exam_body,
    subtopics: [{id, title}]}] -- the syllabus's own topic and item names, in
    syllabus order. [] when the subject has no coded syllabus."""
    from models import MockJAMBSyllabus, MockJAMBSyllabusNode
    syl = MockJAMBSyllabus.query.filter_by(subject_id=subject_id).first() if subject_id else None
    if not syl:
        return []
    maps, _ = label_maps({subject_id})
    m = maps.get(subject_id, {})
    nodes = MockJAMBSyllabusNode.query.filter_by(syllabus_id=syl.id).order_by(MockJAMBSyllabusNode.id).all()
    tree, by_title = [], {}
    # a top-level part that has topics under it is a heading, not a topic
    has_topic_child = {n.parent_id for n in nodes if n.kind == 'topic'}
    for n in nodes:
        if n.parent_id is None and n.id in has_topic_child:
            continue
        t, item = m.get(n.code, (None, None))
        if not t:
            continue
        if t not in by_title:
            by_title[t] = {'id': n.code, 'title': t, 'exam_body': 'Both', 'subtopics': []}
            tree.append(by_title[t])
        if item and item not in {s['title'] for s in by_title[t]['subtopics']}:
            by_title[t]['subtopics'].append({'id': n.code, 'title': item})
    return tree


def code_for(subject_id, topic, subtopic):
    """The syllabus code a (topic, sub-topic) pair names in a coded subject:
    the item's code when the sub-topic is given, else the topic's own code.
    None when nothing matches (or the subject has no coded syllabus)."""
    maps, _ = label_maps({subject_id})
    m = maps.get(subject_id) or {}
    t = (topic or '').strip().lower()
    s = (subtopic or '').strip().lower()
    if not t:
        return None
    best = None
    for code, (tt, item) in m.items():
        if (tt or '').lower() != t:
            continue
        if s and (item or '').lower() == s:
            return code
        if not item and best is None:
            best = code                       # the topic node itself
    return None if s else best


def codes_matching(subject_id, topic=None, subtopic=None):
    """Codes under a reported topic / item name (for the bank filter)."""
    maps, _ = label_maps({subject_id})
    m = maps.get(subject_id) or {}
    out = []
    for code, (tt, item) in m.items():
        if topic and tt != topic:
            continue
        if subtopic and item != subtopic:
            continue
        out.append(code)
    return out
