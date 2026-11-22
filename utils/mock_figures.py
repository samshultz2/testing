"""Which Mock JAMB bank questions need a picture they don't have.

A question needs an image when it was flagged on import (``needs_image``) or when
its stem, options or passage point at something visual — "the diagram above",
"Fig. 2", "the graph", "the circuit shown" — and neither the question nor its
passage carries an image. An admin can rule a match a false alarm
(``image_not_needed``), and it then stays out of the queue for good.

``sync()`` writes the result back onto ``needs_image`` so the exam draw (which
holds flagged questions out) and the queue always agree.
"""
import re
import time

from sqlalchemy import func, or_

# Words that point at a picture. Kept tight to avoid the common false alarms:
# "figure of speech", "significant figures", "a figure of 20", "paragraph".
FIGURE_RE = re.compile(
    r"\b(?:diagrams?|fig\.|fig\s*\d|figures?\s*\d|(?:the|this|above|below|following|given)\s+figures?|"
    r"figures?\s+(?:above|below|shown)|graphs?|sketch(?:ed)?|drawing|circuits?\s+(?:shown|above|below|diagram)|"
    r"shown\s+(?:above|below|in\s+the)|illustrated|labell?ed\s+[A-Z0-9IVX]{1,4}\b|"
    r"(?:map|chart|picture|image|photograph|apparatus|set-?up|structure)\s+(?:above|below|shown))(?!\w)", re.I)
NOT_FIGURE_RE = re.compile(r"\bfigures?\s+of\s+speech\b|\bsignificant\s+figures?\b", re.I)

# Cheap SQL pre-filter (substring match) — the regex above then decides.
_LIKE = ('diagram', 'fig', 'graph', 'sketch', 'drawing', 'circuit', 'shown', 'illustrated',
         'labelled', 'labeled', 'above', 'below')


def mentions_figure(*texts):
    """True when any of the texts refers to a picture."""
    for t in texts:
        if not t:
            continue
        t = NOT_FIGURE_RE.sub(' ', t)
        if FIGURE_RE.search(t):
            return True
    return False


def _has(v):
    return bool((v or '').strip())


def needs_image(q):
    """Does this bank question (with its passage) still need a picture?"""
    if _has(q.image_url) or getattr(q, 'image_not_needed', False):
        return False
    p = q.passage
    if p is not None and _has(p.image_url):
        return False
    if q.needs_image:
        return True
    return mentions_figure(q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
                           p.body if p is not None else None)


def _candidates():
    from models import MockJAMBQuestion as Q, MockJAMBPassage as P
    cols = (Q.question_text, Q.option_a, Q.option_b, Q.option_c, Q.option_d, P.body)
    likes = [func.lower(c).like('%' + w + '%') for w in _LIKE for c in cols]
    return (Q.query.outerjoin(P, Q.passage_id == P.id)
            .filter(Q.mock_exam_id.is_(None), or_(Q.needs_image.is_(True), *likes)))


_last = {}


def sync(force=False, every=60):
    """Set ``needs_image`` on every bank question that needs a picture and clear it
    on those that no longer do. Returns the number of questions now flagged.
    Throttled to once a minute per database unless ``force``."""
    from models import db, MockJAMBQuestion as Q
    key = str(db.engine.url)
    now = time.monotonic()
    if not force and now - _last.get(key, -1e9) < every:
        return None
    _last[key] = now
    on, off = [], []
    for q in _candidates().all():
        want = needs_image(q)
        if want and not q.needs_image:
            on.append(q.id)
        elif q.needs_image and not want:
            off.append(q.id)
    for ids, val in ((on, True), (off, False)):
        for i in range(0, len(ids), 400):
            Q.query.filter(Q.id.in_(ids[i:i + 400])).update(
                {Q.needs_image: val}, synchronize_session=False)
    if on or off:
        db.session.commit()
    return len(on)


def reason(q):
    """A short phrase explaining why the question is in the queue."""
    if q.needs_image and (q.source or '') not in ('', 'manual', 'paste') and not mentions_figure(
            q.question_text, q.option_a, q.option_b, q.option_c, q.option_d):
        return 'Flagged on import'
    texts = [q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
             q.passage.body if q.passage is not None else None]
    for t in texts:
        if not t:
            continue
        m = FIGURE_RE.search(NOT_FIGURE_RE.sub(' ', t))
        if m:
            w = m.group(0).strip()
            return 'Mentions “%s”%s' % (w if len(w) < 30 else w[:28] + '…',
                                         ' in its passage' if t is texts[-1] and t else '')
    return 'Flagged on import'
