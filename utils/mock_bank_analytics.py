"""Per-subject question-bank analytics — what the central Mock JAMB bank actually
holds for one subject, broken down by topic, sub-topic, year and exam body, so a
teacher can see where questions cluster and, crucially, which syllabus areas are
thin, cold (not tested in recent years) or never tested — i.e. what to focus
students on.

All read-only over the tenant's own bank (``mock_exam_id`` NULL). Recency is
measured against the bank's own most-recent exam years for the subject (so it
adapts whether the newest banked year is 2023 or 2025).
"""
from __future__ import annotations

# How many of the most-recent banked years count as "recent" for the cold check.
RECENT_WINDOW = 3


def _year_int(y):
    """A 4-digit year as int, or None (bank years are free-text strings)."""
    try:
        s = str(y or '').strip()[:4]
        return int(s) if s.isdigit() else None
    except (TypeError, ValueError):
        return None


def _pct(n, total):
    return round(100.0 * n / total, 1) if total else 0.0


def subject_breakdown(subject):
    """A dict summarising the bank for one subject:

    ``total`` (banked stand-alone + passage questions), ``recent_years`` (the
    window used for the cold check), ``topics`` / ``subtopics`` (count, percent,
    years covered, most-recent year, cold flag), ``by_year``, ``by_exam_body``,
    and ``gaps`` — syllabus topics/sub-topics with no banked question at all.

    Prefers the subject's imported *coded* syllabus (stable per-question
    ``syllabus_item_code``, see MockJAMBSyllabus/MockJAMBSyllabusNode) when one
    exists: gaps are then exact (every syllabus item is known up front, so a
    never-banked item shows as a real gap, not just a name that was never
    typed as a free-text topic). Falls back to the free-text ``topic``/
    ``subtopic`` fields for a subject with no coded syllabus imported yet —
    same shape either way, so the template doesn't care which one ran.
    """
    from models import MockJAMBSyllabus
    syll = MockJAMBSyllabus.query.filter_by(subject_id=subject.id).first()
    if syll:
        return _coded_breakdown(subject, syll)
    return _freetext_breakdown(subject)


def _coded_breakdown(subject, syll):
    """subject_breakdown(), sourced from the coded syllabus tree instead of
    free-text topic/subtopic: one 'topic' row per coded topic node, one
    'subtopic' row per coded item (leaf) node, and TRUE gaps -- a syllabus
    item with zero banked questions shows up even if no question was ever
    typed with a matching name."""
    from models import db, MockJAMBQuestion, MockJAMBSyllabusNode
    from sqlalchemy import func

    sid = subject.id
    base = MockJAMBQuestion.query.filter(
        MockJAMBQuestion.subject_id == sid,
        MockJAMBQuestion.mock_exam_id.is_(None))
    total = base.count()

    nodes = MockJAMBSyllabusNode.query.filter_by(syllabus_id=syll.id).all()
    by_id = {n.id: n for n in nodes}
    topics_by_id = {n.id: n for n in nodes if n.kind == 'topic'}
    items = [n for n in nodes if n.kind == 'item']

    year_ints = sorted({_year_int(y) for (y,) in db.session.query(MockJAMBQuestion.exam_year)
                        .filter(MockJAMBQuestion.subject_id == sid,
                                MockJAMBQuestion.mock_exam_id.is_(None)).distinct().all()
                        if _year_int(y) is not None}, reverse=True)
    recent_years = set(year_ints[:RECENT_WINDOW])

    # count + years banked per coded item code
    item_agg = {}
    for code, yr, n in (db.session.query(MockJAMBQuestion.syllabus_item_code,
                                         MockJAMBQuestion.exam_year, func.count(MockJAMBQuestion.id))
                        .filter(MockJAMBQuestion.subject_id == sid,
                                MockJAMBQuestion.mock_exam_id.is_(None),
                                MockJAMBQuestion.syllabus_item_code.isnot(None),
                                MockJAMBQuestion.syllabus_item_code != '')
                        .group_by(MockJAMBQuestion.syllabus_item_code, MockJAMBQuestion.exam_year).all()):
        slot = item_agg.setdefault(code, {'count': 0, 'years': set()})
        slot['count'] += n
        yi = _year_int(yr)
        if yi is not None:
            slot['years'].add(yi)

    def _row(count, years):
        years = sorted(years, reverse=True)
        recent_hit = bool(years and recent_years & set(years))
        return {
            'count': count, 'pct': _pct(count, total), 'years': years,
            'recent_year': (years[0] if years else None),
            'cold': bool(recent_years and years and not recent_hit),
        }

    # per coded item ("subtopic" row) -- every item in the tree, banked or not
    subtopics = []
    topic_totals = {}   # topic node id -> {'count', 'years'}
    for it in items:
        topic_node = by_id.get(it.parent_id)
        topic_name = topic_node.name if topic_node else None
        slot = item_agg.get(it.code, {'count': 0, 'years': set()})
        row = _row(slot['count'], slot['years'])
        row.update({'topic': topic_name, 'subtopic': it.name})
        subtopics.append(row)
        if topic_node:
            agg = topic_totals.setdefault(topic_node.id, {'count': 0, 'years': set()})
            agg['count'] += slot['count']
            agg['years'] |= slot['years']
    subtopics.sort(key=lambda d: (-d['count'], (d['subtopic'] or '').lower()))

    # per coded topic ("topic" row) -- every topic in the tree, banked or not
    topics = []
    for tnode in topics_by_id.values():
        agg = topic_totals.get(tnode.id, {'count': 0, 'years': set()})
        row = _row(agg['count'], agg['years'])
        row.update({'topic': tnode.name})
        topics.append(row)
    topics.sort(key=lambda d: (-d['count'], (d['topic'] or '').lower()))

    untagged = base.filter((MockJAMBQuestion.syllabus_item_code.is_(None)) |
                           (MockJAMBQuestion.syllabus_item_code == '')).count()

    by_year = [{'year': y, 'count': n} for (y, n) in sorted(
        _year_counts(db, sid).items(), key=lambda kv: (kv[0] is None, -(kv[0] or 0)))]
    by_exam_body = [{'body': (b or 'Unspecified'), 'count': n} for (b, n) in
                    sorted(_body_counts(db, sid).items(), key=lambda kv: -kv[1])]

    gap_topics = [t['topic'] for t in topics if t['count'] == 0]
    gap_subtopics = [{'topic': s['topic'], 'subtopic': s['subtopic']}
                     for s in subtopics if s['count'] == 0]

    return {
        'total': total, 'untagged': untagged, 'coded': True,
        'recent_years': sorted(recent_years, reverse=True),
        'topics': topics, 'subtopics': subtopics,
        'by_year': by_year, 'by_exam_body': by_exam_body,
        'cold_topics': [t for t in topics if t['cold']],
        'gaps': {'topics': gap_topics, 'subtopics': gap_subtopics},
    }


def _freetext_breakdown(subject):
    from models import db, MockJAMBQuestion
    from sqlalchemy import func

    sid = subject.id
    base = MockJAMBQuestion.query.filter(
        MockJAMBQuestion.subject_id == sid,
        MockJAMBQuestion.mock_exam_id.is_(None))
    total = base.count()

    # the recency window: the most-recent distinct banked years for this subject
    year_ints = sorted({_year_int(y) for (y,) in db.session.query(MockJAMBQuestion.exam_year)
                        .filter(MockJAMBQuestion.subject_id == sid,
                                MockJAMBQuestion.mock_exam_id.is_(None)).distinct().all()
                        if _year_int(y) is not None}, reverse=True)
    recent_years = set(year_ints[:RECENT_WINDOW])

    def _rollup(*group_cols):
        """count + per-topic year set, grouped by the given column(s)."""
        rows = (db.session.query(*group_cols, MockJAMBQuestion.exam_year,
                                 func.count(MockJAMBQuestion.id))
                .filter(MockJAMBQuestion.subject_id == sid,
                        MockJAMBQuestion.mock_exam_id.is_(None))
                .group_by(*group_cols, MockJAMBQuestion.exam_year).all())
        agg = {}                      # key -> {'count', 'years'(set of int)}
        for r in rows:
            key = tuple(r[:len(group_cols)])
            yr = _year_int(r[len(group_cols)])
            n = r[-1]
            slot = agg.setdefault(key, {'count': 0, 'years': set()})
            slot['count'] += n
            if yr is not None:
                slot['years'].add(yr)
        return agg

    def _finish(agg, keyname):
        out = []
        for key, slot in agg.items():
            label = key[0] if len(key) == 1 else key
            years = sorted(slot['years'], reverse=True)
            recent_hit = bool(slot['years'] & recent_years)
            out.append({
                keyname: (label if isinstance(label, str) else None),
                'topic': key[0], 'subtopic': (key[1] if len(key) > 1 else None),
                'count': slot['count'], 'pct': _pct(slot['count'], total),
                'years': years, 'recent_year': (years[0] if years else None),
                # cold = has questions but none from the recent window (and there IS a
                # recent window to compare against, and this topic carries year data).
                'cold': bool(recent_years and slot['years'] and not recent_hit),
            })
        out.sort(key=lambda d: (-d['count'], (d.get(keyname) or d['topic'] or '').lower()))
        return out

    # Untagged (no topic) questions are surfaced separately, not as a "topic".
    topic_agg = {k: v for k, v in _rollup(MockJAMBQuestion.topic).items()
                 if (k[0] or '').strip()}
    topics = _finish(topic_agg, 'topic')

    sub_agg = {k: v for k, v in _rollup(MockJAMBQuestion.topic, MockJAMBQuestion.subtopic).items()
               if (k[1] or '').strip()}
    subtopics = _finish(sub_agg, 'subtopic')

    untagged = base.filter((MockJAMBQuestion.topic.is_(None)) |
                           (MockJAMBQuestion.topic == '')).count()

    by_year = [{'year': y, 'count': n} for (y, n) in sorted(
        _year_counts(db, sid).items(), key=lambda kv: (kv[0] is None, -(kv[0] or 0)))]
    by_exam_body = [{'body': (b or 'Unspecified'), 'count': n} for (b, n) in
                    sorted(_body_counts(db, sid).items(), key=lambda kv: -kv[1])]

    gaps = _syllabus_gaps(subject, topic_agg, sub_agg)

    return {
        'total': total, 'untagged': untagged, 'coded': False,
        'recent_years': sorted(recent_years, reverse=True),
        'topics': topics, 'subtopics': subtopics,
        'by_year': by_year, 'by_exam_body': by_exam_body,
        'cold_topics': [t for t in topics if t['cold']],
        'gaps': gaps,
    }


def _year_counts(db, sid):
    from models import MockJAMBQuestion
    from sqlalchemy import func
    out = {}
    for (y, n) in (db.session.query(MockJAMBQuestion.exam_year, func.count(MockJAMBQuestion.id))
                   .filter(MockJAMBQuestion.subject_id == sid,
                           MockJAMBQuestion.mock_exam_id.is_(None))
                   .group_by(MockJAMBQuestion.exam_year).all()):
        out[_year_int(y)] = out.get(_year_int(y), 0) + n
    return out


def _body_counts(db, sid):
    from models import MockJAMBQuestion
    from sqlalchemy import func
    return dict(db.session.query(MockJAMBQuestion.exam_body, func.count(MockJAMBQuestion.id))
                .filter(MockJAMBQuestion.subject_id == sid,
                        MockJAMBQuestion.mock_exam_id.is_(None))
                .group_by(MockJAMBQuestion.exam_body).all())


def _syllabus_gaps(subject, topic_agg, sub_agg):
    """Syllabus topics/sub-topics (from the seeded SyllabusTopic tree) that have NO
    banked question — the areas past questions in the bank have never covered."""
    try:
        from routes.cbt import _subject_topic_tree
        tree = _subject_topic_tree(subject.id)
    except Exception:
        tree = []
    have_topics = {(k[0] or '').strip().lower() for k in topic_agg}
    have_subs = {(k[1] or '').strip().lower() for k in sub_agg}
    topic_gaps, sub_gaps = [], []
    for t in tree:
        title = (t['title'] or '').strip()
        if title.lower() not in have_topics:
            topic_gaps.append(title)
        for s in t.get('subtopics', []):
            st = (s['title'] or '').strip()
            if st.lower() not in have_subs:
                sub_gaps.append({'topic': title, 'subtopic': st})
    return {'topics': topic_gaps, 'subtopics': sub_gaps}
