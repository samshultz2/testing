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


def _resolve_blueprint_section(node, by_id, valid_sections):
    """The draw blueprint section a question tagged to ``node`` belongs to:
    ``node``'s own ``blueprint_section`` if set, else its nearest ancestor's,
    validated against the subject's actual blueprint sections. None if nothing
    in the chain has been curated yet, or the curated value is stale (no
    longer a real section) -- callers then leave `section` untouched, same as
    before this field existed."""
    seen, cur = set(), node
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        bs = (cur.blueprint_section or '').strip()
        if bs:
            from utils.jamb_blueprint import canon_section
            bs = canon_section(bs)
            return bs if bs in valid_sections else None
        cur = by_id.get(cur.parent_id)
    return None


_PASSAGE_SECTIONS = {'comprehension', 'cloze', 'summary'}


def _place_english(row, code_section, valid_sections):
    """Use of English: JAMB's instruction wording ("opposite in meaning", "the
    information conveyed", "in capital letters"…) or the novel's characters say
    the section reliably; the AI's syllabus code is only used when the wording
    says nothing -- and never to put a question with no passage into a reading
    (passage) section, which a mock can't draw."""
    from utils.english_sections import rule_section, novel_by_characters
    sec = rule_section(row.question_text)
    if 'novel' in valid_sections and novel_by_characters(row.question_text, row.exam_year):
        sec = 'novel'                     # the novel's characters, in one of its years
    if sec and sec in valid_sections:
        row.section = sec
        return
    if code_section and not (row.passage_id is None and code_section in _PASSAGE_SECTIONS):
        row.section = code_section


def place_section(row, subject_name, node, by_id, valid_sections):
    """Set the paper section for a question just given a coded syllabus item:
    the syllabus's curated mapping when there is one; for English, the question's
    instruction wording ("same vowel sound", "opposite in meaning"…); otherwise
    only repair a section that isn't in the paper at all, and only on a
    confident match. Never a guess; Novel questions are never moved."""
    from utils.jamb_blueprint import canon_section
    from utils import myschool as ms
    if canon_section(row.section) == 'novel':
        return
    bp = _resolve_blueprint_section(node, by_id, valid_sections)
    if ms.norm_subject(subject_name) == 'english language':
        _place_english(row, bp, valid_sections)
        return
    if bp:
        row.section = bp
        return
    text = ' '.join(filter(None, [row.question_text, row.option_a, row.option_b, row.option_c, row.option_d]))
    if row.section not in valid_sections:
        sec = ms.classify_confident(subject_name, text, year=row.exam_year)[0]
        if sec in valid_sections and sec != 'novel':
            row.section = sec


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
    from utils.ai_tag_params import create
    resp = create(client, model, 2000,
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


def coded_retag(subject, year=None, exam_body=None, mode='all', max_questions=_MAX_DEFAULT,
                model=None):
    """Tag a subject's stand-alone bank questions with coded syllabus items via the
    configured Anthropic key. ``mode='untagged'`` only touches questions with no
    code yet. ``model`` overrides the Settings model. See module docstring."""
    from models import db, MockJAMBQuestion
    from utils.waec_ocr import _vision_config

    result = {'scanned': 0, 'tagged': 0, 'outside': 0, 'still_untagged': 0,
              'chunks': 0, 'total': 0, 'capped': False, 'error': None}

    cfg = _vision_config()
    if not cfg['installed']:
        result['error'] = 'not_installed'; return result
    if not cfg['has_key']:
        result['error'] = 'no_key'; return result

    try:                                   # latest topic -> paper-section mappings first
        from utils.syllabus_sections import sync_mappings
        sync_mappings(subject)
    except Exception:
        pass
    by_code, _syll = coded_nodes(subject.id)
    if not by_code:
        result['error'] = 'no_syllabus'; return result
    syllabus_block = _syllabus_block(by_code)
    by_id = {n.id: n for n in by_code.values()}
    from utils.jamb_blueprint import sections_for
    valid_sections = {s['section'] for s in sections_for(subject.name)}

    q = db.session.query(MockJAMBQuestion.id).filter(
        MockJAMBQuestion.subject_id == subject.id,
        MockJAMBQuestion.mock_exam_id.is_(None),
        MockJAMBQuestion.passage_id.is_(None),
        (MockJAMBQuestion.section.is_(None)) | (MockJAMBQuestion.section != 'novel'))   # keep Novel titles
    if year:
        from utils.mock_bank_retag import filter_years
        q = filter_years(q, MockJAMBQuestion.exam_year, year)
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
            mapping = _classify_chunk(client, (model or '').strip() or cfg['model'], subject.name, syllabus_block, rows)
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
            # Also correct the flat `section` the exam draw actually samples by,
            # when this node (or an ancestor) has a curated blueprint_section --
            # the coded classification is more reliable than the free-text
            # keyword classifier that otherwise owns this field, so a confident
            # coded match should win.
            place_section(row, subject.name, node, by_id, valid_sections)
            result['tagged'] += 1
        db.session.commit()

    result['still_untagged'] = result['scanned'] - result['tagged'] - result['outside']
    return result
