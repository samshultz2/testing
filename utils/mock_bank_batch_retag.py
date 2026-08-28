"""Batch AI retag of Mock-JAMB bank questions against the CODED syllabus.

Uses Anthropic's Message Batches API (50% cheaper, asynchronous) with prompt
caching on the authoritative-syllabus block (identical for every question in a
subject, so it is cached once and re-read cheaply). One request per question;
the model may only choose from the syllabus codes we send — it can never invent
one, and codes not in the syllabus are rejected before writing.

Flow (driven by the jobs worker, never blocking a tick):
  submit  -> build one batch request per question, send, store batch_id
  poll    -> check status once; re-enqueue until the batch has 'ended'
  apply   -> stream results, validate each code, write syllabus_item_code

``force=False`` (default) skips questions that already carry a code, so a repeat
run only fills the gaps; ``force=True`` re-tags everything.
"""
from __future__ import annotations

import json

from utils.mock_bank_coded_retag import (
    coded_nodes, _syllabus_block, _extract_json_array, OUTSIDE,
)

_MAX_REQUESTS = 5000            # safety cap per batch (well under the API's 100k)


def target_ids(subject, year=None, exam_body=None, force=False):
    """Stand-alone bank-question ids to classify. ``force=False`` skips ones that
    already carry a syllabus_item_code."""
    from models import db, MockJAMBQuestion
    q = db.session.query(MockJAMBQuestion.id).filter(
        MockJAMBQuestion.subject_id == subject.id,
        MockJAMBQuestion.mock_exam_id.is_(None),
        MockJAMBQuestion.passage_id.is_(None))
    if year:
        q = q.filter(MockJAMBQuestion.exam_year == str(year))
    if exam_body:
        q = q.filter(MockJAMBQuestion.exam_body == exam_body)
    if not force:
        q = q.filter((MockJAMBQuestion.syllabus_item_code.is_(None))
                     | (MockJAMBQuestion.syllabus_item_code == ''))
    return [row[0] for row in q.order_by(MockJAMBQuestion.id).all()]


def _system_text(subject_name, syllabus_block):
    """The cacheable instruction+syllabus prefix shared by every request."""
    return (
        "You are classifying examination questions.\n\n"
        f"Subject:\n{subject_name}\n\n"
        f"Authoritative syllabus:\n{syllabus_block}\n\n"
        "Task:\n"
        "Classify the question using the most specific applicable syllabus item.\n\n"
        "Rules:\n"
        "1. Only use syllabus IDs provided.\n"
        "2. Do not invent syllabus items.\n"
        "3. Select one primary syllabus item.\n"
        "4. Add secondary items only when genuinely necessary.\n"
        "5. If no syllabus item is appropriate, mark OUTSIDE_SYLLABUS.\n"
        "6. Preserve the original question.\n"
        "7. Return structured JSON only, shaped exactly:\n"
        '{"primary": "<syllabus ID or OUTSIDE_SYLLABUS>", "secondary": ["<syllabus ID>", ...]}'
    )


def build_requests(subject_name, syllabus_block, rows, model, max_tokens=300):
    """One batch request per question. The big syllabus prefix is a cached system
    block; the per-question user text is tiny."""
    system = [{'type': 'text', 'text': _system_text(subject_name, syllabus_block),
               'cache_control': {'type': 'ephemeral'}}]
    reqs = []
    for r in rows:
        opts = ' | '.join(filter(None, [r.option_a, r.option_b, r.option_c, r.option_d]))
        q = (r.question_text or '').strip().replace('\n', ' ')
        user = (f"Question: {q[:600]}\nOptions: {opts[:400]}\n\n"
                "Return only the JSON object.")
        reqs.append({
            'custom_id': f'q{r.id}',
            'params': {
                'model': model,
                'max_tokens': max_tokens,
                'system': system,
                'messages': [{'role': 'user', 'content': user}],
            },
        })
    return reqs


def submit_batch(client, requests):
    """Create a Message Batch; return its id."""
    batch = client.messages.batches.create(requests=requests)
    return getattr(batch, 'id', None) or batch['id']


def batch_status(client, batch_id):
    """'in_progress' | 'canceling' | 'ended' (or whatever the API reports)."""
    b = client.messages.batches.retrieve(batch_id)
    return getattr(b, 'processing_status', None) or (b.get('processing_status') if isinstance(b, dict) else None)


def _parse_result_obj(obj):
    """A result may be an object or a single-element array; return (primary, [secondary])."""
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    if not isinstance(obj, dict):
        return None, []
    primary = (obj.get('primary') or '').strip()
    secondary = obj.get('secondary') or []
    if not isinstance(secondary, list):
        secondary = []
    return primary, [str(s).strip() for s in secondary if str(s).strip()]


def apply_results(client, batch_id, subject, by_code, by_id):
    """Stream the finished batch, validate codes and write them. Returns a
    summary dict."""
    from models import db, MockJAMBQuestion
    summary = {'tagged': 0, 'outside': 0, 'invalid': 0, 'errored': 0, 'scanned': 0}
    for entry in client.messages.batches.results(batch_id):
        cid = getattr(entry, 'custom_id', None)
        result = getattr(entry, 'result', None)
        rtype = getattr(result, 'type', None)
        if not cid or not cid.startswith('q'):
            continue
        try:
            qid = int(cid[1:])
        except ValueError:
            continue
        summary['scanned'] += 1
        if rtype != 'succeeded':
            summary['errored'] += 1
            continue
        msg = getattr(result, 'message', None)
        text = ''.join(getattr(b, 'text', '') for b in (getattr(msg, 'content', None) or []))
        obj = None
        try:
            obj = json.loads(text)
        except Exception:
            arr = _extract_json_array(text)
            obj = arr[0] if arr else None
        primary, secondary = _parse_result_obj(obj)
        row = db.session.get(MockJAMBQuestion, qid)
        if row is None or not primary:
            continue
        if primary == OUTSIDE:
            summary['outside'] += 1
            continue
        if primary not in by_code:
            summary['invalid'] += 1
            continue
        row.syllabus_item_code = primary
        valid_sec = [c for c in secondary if c in by_code and c != primary][:5]
        row.syllabus_secondary_codes = ','.join(valid_sec) or None
        node = by_code[primary]
        parent = by_id.get(node.parent_id)
        row.subtopic = (node.name or '')[:120] or None
        row.topic = ((parent.name if parent else node.name) or '')[:100] or None
        summary['tagged'] += 1
    db.session.commit()
    return summary
