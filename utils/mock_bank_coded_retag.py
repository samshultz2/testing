"""AI retag of Mock-JAMB bank questions against the imported CODED syllabus.

Unlike utils.mock_bank_ai_retag (which labels questions with free-text topic
names from the built-in syllabus), this classifies each question to a stable
syllabus-item CODE (e.g. ``MATH.NUM.1.A``) from the subject's imported syllabus
(MockJAMBSyllabus / MockJAMBSyllabusNode). The model is only ever allowed to pick
from the codes we send it — it can never invent one — and it writes the primary
code to ``MockJAMBQuestion.syllabus_item_code`` (plus any secondary codes).

Uses the same Anthropic key configured in Settings (utils.waec_ocr._vision_config).
Best-effort and chunked; one bad API response only skips that chunk. Returns
``{scanned, tagged, outside, still_untagged, chunks, total, capped, error}``.
"""
from __future__ import annotations

import json
import re

_CHUNK = 20
_MAX_DEFAULT = 400
OUTSIDE = 'OUTSIDE_SYLLABUS'


def coded_nodes(subject_id):
    """{code: node} for every node in the subject's imported syllabus (or {})."""
    from models import MockJAMBSyllabus, MockJAMBSyllabusNode
    syll = MockJAMBSyllabus.query.filter_by(subject_id=subject_id).first()
    if not syll:
        return {}, None
    nodes = MockJAMBSyllabusNode.query.filter_by(syllabus_id=syll.id).all()
    return {n.code: n for n in nodes}, syll


def _syllabus_block(by_code):
    """The authoritative-syllabus text: one `CODE — path` line per node, deepest
    context included so the model can pick the most specific item."""
    parent = {c: n.parent_id for c, n in by_code.items()}
    by_id = {n.id: n for n in by_code.values()}

    def path(n):
        names, seen = [], set()
        cur = n
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            names.append(cur.name or cur.code)
            cur = by_id.get(cur.parent_id)
        return ' > '.join(reversed(names))

    lines = []
    for code in sorted(by_code):
        lines.append(f'{code} — {path(by_code[code])}')
    return '\n'.join(lines)


def _extract_json_array(text):
    if not text:
        return []
    for candidate in (text, (re.search(r'\[.*\]', text, re.DOTALL) or [None])[0]
                      if re.search(r'\[.*\]', text, re.DOTALL) else None):
        if not candidate:
            continue
        try:
            data = json.loads(candidate if isinstance(candidate, str) else candidate.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            continue
    return []


def _classify_chunk(client, model, subject_name, syllabus_block, rows):
    """Return {id: (primary_code|OUTSIDE, [secondary_codes])} for the chunk."""
    items = []
    for r in rows:
        opts = ' | '.join(filter(None, [r.option_a, r.option_b, r.option_c, r.option_d]))
        q = (r.question_text or '').strip().replace('\n', ' ')
        items.append(f'{{"id": {r.id}, "question": {json.dumps(q[:600])}, '
                     f'"options": {json.dumps(opts[:400])}}}')
    prompt = (
        "You are classifying examination questions.\n\n"
        f"Subject:\n{subject_name}\n\n"
        f"Authoritative syllabus:\n{syllabus_block}\n\n"
        "Task:\n"
        "Classify each question using the most specific applicable syllabus item.\n\n"
        "Rules:\n"
        "1. Only use syllabus IDs provided.\n"
        "2. Do not invent syllabus items.\n"
        "3. Select one primary syllabus item.\n"
        "4. Add secondary items only when genuinely necessary.\n"
        "5. If no syllabus item is appropriate, mark OUTSIDE_SYLLABUS.\n"
        "6. Preserve the original question.\n"
        "7. Return structured JSON only.\n\n"
        "Return ONLY a JSON array, one object per question, in this shape:\n"
        '[{"id": <id>, "primary": "<syllabus ID or OUTSIDE_SYLLABUS>", '
        '"secondary": ["<syllabus ID>", ...]}]\n\n'
        "Questions:\n[" + ",\n".join(items) + "]"
    )
    resp = client.messages.create(
        model=model, max_tokens=2000,
        messages=[{'role': 'user', 'content': prompt}])
    text = ''.join(getattr(b, 'text', '') for b in (resp.content or []))
    out = {}
    for obj in _extract_json_array(text):
        try:
            qid = int(obj.get('id'))
        except (TypeError, ValueError):
            continue
        primary = (obj.get('primary') or '').strip()
        secondary = obj.get('secondary') or []
        if not isinstance(secondary, list):
            secondary = []
        out[qid] = (primary, [str(s).strip() for s in secondary if str(s).strip()])
    return out


def coded_retag(subject, year=None, exam_body=None, mode='all', max_questions=_MAX_DEFAULT):
    """Tag a subject's stand-alone bank questions with coded syllabus items via the
    configured Anthropic key. ``mode='untagged'`` only touches questions with no
    code yet. See module docstring."""
    from models import db, MockJAMBQuestion
    from utils.waec_ocr import _vision_config

    result = {'scanned': 0, 'tagged': 0, 'outside': 0, 'still_untagged': 0,
              'chunks': 0, 'total': 0, 'capped': False, 'error': None}

    cfg = _vision_config()
    if not cfg['installed']:
        result['error'] = 'not_installed'; return result
    if not cfg['has_key']:
        result['error'] = 'no_key'; return result

    by_code, _syll = coded_nodes(subject.id)
    if not by_code:
        result['error'] = 'no_syllabus'; return result
    syllabus_block = _syllabus_block(by_code)
    by_id = {n.id: n for n in by_code.values()}

    q = db.session.query(MockJAMBQuestion.id).filter(
        MockJAMBQuestion.subject_id == subject.id,
        MockJAMBQuestion.mock_exam_id.is_(None),
        MockJAMBQuestion.passage_id.is_(None))
    if year:
        q = q.filter(MockJAMBQuestion.exam_year == str(year))
    if exam_body:
        q = q.filter(MockJAMBQuestion.exam_body == exam_body)
    if mode == 'untagged':
        q = q.filter((MockJAMBQuestion.syllabus_item_code.is_(None))
                     | (MockJAMBQuestion.syllabus_item_code == ''))
    all_ids = [row[0] for row in q.order_by(MockJAMBQuestion.id).all()]
    result['total'] = len(all_ids)
    ids = all_ids[:max_questions]
    result['capped'] = len(all_ids) > len(ids)
    if not ids:
        return result

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=cfg['key'])
    except Exception:
        result['error'] = 'not_installed'; return result

    for start in range(0, len(ids), _CHUNK):
        chunk_ids = ids[start:start + _CHUNK]
        rows = MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(chunk_ids)).all()
        result['scanned'] += len(rows)
        try:
            mapping = _classify_chunk(client, cfg['model'], subject.name, syllabus_block, rows)
        except Exception:
            continue
        result['chunks'] += 1
        for row in rows:
            got = mapping.get(row.id)
            if not got:
                continue
            primary, secondary = got
            if primary == OUTSIDE:
                result['outside'] += 1
                continue
            if primary not in by_code:          # never accept an invented code
                continue
            row.syllabus_item_code = primary
            valid_sec = [c for c in secondary if c in by_code and c != primary][:5]
            row.syllabus_secondary_codes = ','.join(valid_sec) or None
            # Mirror the coded names into the display topic/sub-topic so the tag
            # shows up in the existing bank filters and analytics.
            node = by_code[primary]
            item_name = node.name
            parent = by_id.get(node.parent_id)
            row.subtopic = (item_name or '')[:120] or None
            row.topic = ((parent.name if parent else item_name) or '')[:100] or None
            result['tagged'] += 1
        db.session.commit()

    result['still_untagged'] = result['scanned'] - result['tagged'] - result['outside']
    return result
