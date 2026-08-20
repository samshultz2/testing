"""Local, offline topic + sub-topic tagging for the Mock-JAMB question bank.

A no-API-key alternative to the Anthropic tagger: it embeds each bank question
and each JAMB-syllabus topic/sub-topic with a small sentence-transformer
(all-MiniLM-L6-v2, ~90 MB, CPU-fine) and assigns the nearest syllabus entry by
cosine similarity. Like the other engines it can only pick a REAL syllabus
topic — below a confidence threshold it leaves the question blank rather than
mislabel it.

IMPORTANT: this pulls in torch via sentence-transformers, so it must only ever
run in the background-jobs worker — never imported at web-request time. The
model is imported lazily inside _model() and cached as a process singleton, so
one warm copy lives in the jobs process and the web workers stay lean. Tagging
is normally a rare, one-off operation (the whole bank once, then only newly
added questions), which is why it runs as a job rather than inline.
"""
from __future__ import annotations

import importlib.util
import os

_MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
_ENCODE_BATCH = 64          # questions embedded per forward pass
_COMMIT_EVERY = 200         # rows written per DB commit
_DEFAULT_THRESHOLD = 0.34   # min cosine similarity to accept a tag

_model_singleton = None     # loaded once per process (jobs worker only)


def available():
    """True if sentence-transformers is importable — checked WITHOUT importing
    it (so this is safe to call from a web worker to gate the UI)."""
    return importlib.util.find_spec('sentence_transformers') is not None


def _model():
    """Lazily load and cache the embedding model. Only ever called inside the
    jobs worker, so torch is never pulled into a web process."""
    global _model_singleton
    if _model_singleton is None:
        from sentence_transformers import SentenceTransformer
        cache = os.environ.get('EMBED_MODEL_DIR') or None
        _model_singleton = SentenceTransformer(_MODEL_NAME, cache_folder=cache)
    return _model_singleton


def _candidates(subject_name):
    """Build the syllabus candidate set for a subject:
    (embed_text, topic, subtopic) — one entry per bare topic plus one per
    sub-topic, so a question can match at either granularity."""
    from utils.syllabus_data import FULL_SYLLABUS
    from utils import myschool as ms
    entries = FULL_SYLLABUS.get(ms.norm_subject(subject_name))
    if not entries:
        return None
    cands = []
    for topic, subs in entries:
        cands.append((topic, topic, None))                 # topic-level match
        for sub in (subs or []):
            cands.append((f'{topic}. {sub}', topic, sub))  # sub-topic-level match
    return cands


def local_tag(subject, mode='untagged', year=None, threshold=_DEFAULT_THRESHOLD,
              progress_cb=None):
    """Tag a subject's stand-alone bank questions with syllabus topic + sub-topic
    using local embeddings. ``mode='untagged'`` (default) only fills blanks —
    the usual case, since a full pass is a one-off and later runs just catch new
    questions; ``mode='all'`` re-tags everything. ``progress_cb(done, total)`` is
    called as it advances. Returns
    ``{scanned, topic_set, subtopic_set, still_untagged, total}``.
    """
    import numpy as np
    from models import db, MockJAMBQuestion
    from utils.mock_bank_retag import _target_ids, _drawable_sections
    from utils.jamb_blueprint import sections_for
    from utils import myschool as ms

    res = {'scanned': 0, 'topic_set': 0, 'subtopic_set': 0, 'still_untagged': 0, 'total': 0}

    cands = _candidates(subject.name)
    if not cands:
        res['error'] = 'no_syllabus'
        return res

    ids = _target_ids(subject, mode, year=year)
    res['total'] = len(ids)
    if not ids:
        return res

    valid_sections = {s['section'] for s in sections_for(subject.name)}
    draw = _drawable_sections(subject)

    model = _model()
    cand_emb = model.encode([c[0] for c in cands], normalize_embeddings=True,
                            convert_to_numpy=True, batch_size=_ENCODE_BATCH)

    pending = 0
    for start in range(0, len(ids), _ENCODE_BATCH):
        chunk = ids[start:start + _ENCODE_BATCH]
        rows = MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(chunk)).all()
        if not rows:
            continue
        texts = []
        for r in rows:
            texts.append(' '.join(filter(None, [
                r.question_text, r.option_a, r.option_b, r.option_c, r.option_d]))[:1200])
        q_emb = model.encode(texts, normalize_embeddings=True,
                             convert_to_numpy=True, batch_size=_ENCODE_BATCH)
        sims = q_emb @ cand_emb.T           # cosine (both normalized)
        best = sims.argmax(axis=1)
        for ri, (row, bi) in enumerate(zip(rows, best)):
            res['scanned'] += 1
            if float(sims[ri][bi]) < threshold:
                continue
            _text, topic, sub = cands[int(bi)]
            row.topic = topic[:100]
            row.subtopic = (sub[:120] if sub else None)
            res['topic_set'] += 1
            if sub:
                res['subtopic_set'] += 1
            if row.section not in valid_sections:
                qt = ' '.join(filter(None, [row.question_text, row.option_a,
                                            row.option_b, row.option_c, row.option_d]))
                sec = ms.classify_confident(subject.name, qt, year=row.exam_year)[0]
                if sec in valid_sections:
                    row.section = sec
                elif draw:
                    row.section = draw[sum(ord(c) for c in qt) % len(draw)]
            pending += 1
        if pending >= _COMMIT_EVERY:
            db.session.commit(); pending = 0
        if progress_cb:
            try:
                progress_cb(min(start + len(chunk), len(ids)), len(ids))
            except Exception:
                pass
    db.session.commit()

    res['still_untagged'] = res['scanned'] - res['topic_set']
    return res
