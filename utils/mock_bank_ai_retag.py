"""AI topic-tagging for the Mock-JAMB question bank.

Uses the Anthropic key configured in Settings → OCR (via utils.waec_ocr
._vision_config — the same linked key as the scan OCR) to tag stand-alone bank
questions with the best-matching JAMB syllabus topic. The model is only ever
allowed to pick from the real syllabus (utils.syllabus_data.FULL_SYLLABUS), so
it can label or leave blank but never invent a topic.

Scope: re-tags EVERY stand-alone question in the chosen subject (optionally
narrowed to one past-question year), overwriting existing topics. Passage-bound
questions are left untouched. Best-effort and chunked: one bad API response or
parse only skips that chunk. Returns
``{scanned, topic_set, still_untagged, chunks, error}`` — ``error`` is set (and
nothing is charged/changed) when the key/package/syllabus is unavailable.
"""
from __future__ import annotations

import json
import re

_CHUNK = 20              # questions per Anthropic call
# Hard ceiling per run: ~20 calls fits comfortably inside the 120s gunicorn
# worker timeout, and stops one click running up a huge bill. When a subject/
# year has more, the caller is told to run again (or narrow by year).
_MAX_DEFAULT = 400


def _syllabus_for(subject_name):
    """(topics list, {topic_lower: canonical}, {topic: [subtopics]}) or (None, …)."""
    from utils.syllabus_data import FULL_SYLLABUS
    from utils import myschool as ms
    entries = FULL_SYLLABUS.get(ms.norm_subject(subject_name))
    if not entries:
        return None, None, None
    topics = [t for (t, _subs) in entries]
    by_lower = {t.lower(): t for t in topics}
    subs = {t: list(s or []) for (t, s) in entries}
    return topics, by_lower, subs


def _extract_json_array(text):
    """Pull the first JSON array out of the model's reply (tolerant of prose /
    code fences around it)."""
    if not text:
        return []
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


def _tag_chunk(client, model, subject_name, topics, rows):
    """Ask the model to map each question id to a syllabus topic. Returns
    ``{id: (topic, subtopic)}`` for confident, in-vocabulary answers only."""
    numbered = '\n'.join(f'{i+1}. {t}' for i, t in enumerate(topics))
    items = []
    for r in rows:
        opts = ' | '.join(filter(None, [r.option_a, r.option_b, r.option_c, r.option_d]))
        q = (r.question_text or '').strip().replace('\n', ' ')
        items.append(f'{{"id": {r.id}, "q": {json.dumps(q[:600])}, "options": {json.dumps(opts[:400])}}}')
    prompt = (
        f"You are tagging JAMB {subject_name} past-question items to a FIXED syllabus.\n"
        f"Allowed topics (choose the single best match, copied EXACTLY; use null if "
        f"none genuinely fits):\n{numbered}\n\n"
        f"For every question below, pick the one best topic. Optionally add a short "
        f"sub-topic phrase. Reply with ONLY a JSON array, one object per question:\n"
        f'[{{"id": <id>, "topic": "<exact topic or null>", "subtopic": "<phrase or null>"}}]\n\n'
        f"Questions:\n[" + ",\n".join(items) + "]"
    )
    resp = client.messages.create(
        model=model, max_tokens=1600,
        messages=[{'role': 'user', 'content': prompt}])
    text = ''.join(getattr(b, 'text', '') for b in (resp.content or []))
    out = {}
    for obj in _extract_json_array(text):
        try:
            qid = int(obj.get('id'))
        except (TypeError, ValueError):
            continue
        topic = (obj.get('topic') or '').strip()
        sub = (obj.get('subtopic') or '').strip() or None
        if topic:
            out[qid] = (topic, sub)
    return out


def ai_retag(subject, year=None, max_questions=_MAX_DEFAULT):
    """Tag a subject's stand-alone bank questions with syllabus topics via the
    configured Anthropic key. See module docstring."""
    from models import db, MockJAMBQuestion
    from utils.waec_ocr import _vision_config
    from utils.mock_bank_retag import _target_ids, _drawable_sections
    from utils.jamb_blueprint import sections_for
    from utils import myschool as ms

    result = {'scanned': 0, 'topic_set': 0, 'still_untagged': 0, 'chunks': 0,
              'total': 0, 'capped': False, 'error': None}

    cfg = _vision_config()
    if not cfg['installed']:
        result['error'] = 'not_installed'; return result
    if not cfg['has_key']:
        result['error'] = 'no_key'; return result

    topics, topic_lc, subs_by_topic = _syllabus_for(subject.name)
    if not topics:
        result['error'] = 'no_syllabus'; return result

    valid_sections = {s['section'] for s in sections_for(subject.name)}
    draw = _drawable_sections(subject)

    all_ids = _target_ids(subject, 'all', year=year)
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
            mapping = _tag_chunk(client, cfg['model'], subject.name, topics, rows)
        except Exception:
            continue                       # skip this chunk on API/parse failure
        result['chunks'] += 1
        for row in rows:
            got = mapping.get(row.id)
            if not got:
                continue
            topic, sub = got
            canon = topic_lc.get(topic.lower())     # only accept real syllabus topics
            if not canon:
                continue
            row.topic = canon[:100]
            # keep the sub-topic only if it's plausibly one of the syllabus sub-topics
            # or a short free phrase; cap length either way.
            row.subtopic = (sub[:120] if sub else None)
            result['topic_set'] += 1
            # make sure it stays drawable: give it a valid section if it lacks one.
            if row.section not in valid_sections:
                text = ' '.join(filter(None, [row.question_text, row.option_a,
                                              row.option_b, row.option_c, row.option_d]))
                sec = ms.classify_confident(subject.name, text, year=row.exam_year)[0]
                if sec in valid_sections:
                    row.section = sec
                elif draw:
                    row.section = draw[sum(ord(c) for c in text) % len(draw)]
        db.session.commit()

    result['still_untagged'] = result['scanned'] - result['topic_set']
    return result
