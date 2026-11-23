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
    if _has(q.image_url):
        return local_missing(q.image_url)          # a picture whose file is gone
    if getattr(q, 'image_not_needed', False):
        return False
    p = q.passage
    if p is not None and _has(p.image_url):
        return local_missing(p.image_url)
    if q.needs_image:
        return True
    return mentions_figure(q.question_text, q.option_a, q.option_b, q.option_c, q.option_d,
                           p.body if p is not None else None)


def _candidates():
    from models import MockJAMBQuestion as Q, MockJAMBPassage as P
    cols = (Q.question_text, Q.option_a, Q.option_b, Q.option_c, Q.option_d, P.body)
    likes = [func.lower(c).like('%' + w + '%') for w in _LIKE for c in cols]
    return (Q.query.outerjoin(P, Q.passage_id == P.id)
            .filter(Q.mock_exam_id.is_(None),
                    or_(Q.needs_image.is_(True), Q.image_url.ilike('/static/%'),
                        P.image_url.ilike('/static/%'), *likes)))


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
    try:
        fix_all_degrees()
        fix_all_powers()
    except Exception:
        db.session.rollback()
    return len(on)


def reason(q):
    """A short phrase explaining why the question is in the queue."""
    if _has(q.image_url) and local_missing(q.image_url):
        return 'Picture file is missing'
    if q.passage is not None and _has(q.passage.image_url) and local_missing(q.passage.image_url):
        return 'Passage picture file is missing'
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


# ---------------------------------------------------------------------------
# Broken pictures: a figure whose file is gone, or one still pointing at another
# website (myschool.ng and most sites block their images from showing on other
# domains, so the picture shows as a broken icon).

_DEG_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[oº˚]\s*$")


def fix_degrees(text):
    """'185 o' → '185°' — myschool renders the degree sign as a superscript 'o',
    which is lost when the text is copied."""
    if not text:
        return text
    m = _DEG_RE.match(text)
    return (m.group(1) + '°') if m else text


def is_external(url):
    return bool(url) and url.strip().lower().startswith(('http://', 'https://', '//'))


def local_missing(url):
    """True for a /static/… picture whose file is not on this server."""
    import os
    from flask import current_app
    if not url or is_external(url) or url.startswith('data:'):
        return False
    static_url = (current_app.static_url_path or '/static').rstrip('/') + '/'
    if not url.startswith(static_url):
        return False
    rel = url[len(static_url):].split('?', 1)[0]
    path = os.path.normpath(os.path.join(current_app.static_folder, rel))
    if not path.startswith(os.path.normpath(current_app.static_folder)):
        return False
    return not os.path.isfile(path)


def save_copy(url):
    """Download a picture from another site (or a data: URI) and keep a copy on
    this server. Returns the local URL, or None when it can't be fetched."""
    from utils.myschool_harvest import _rehost_image
    if url and url.startswith('//'):
        url = 'https:' + url
    return _rehost_image(url) if url else None


def external_count():
    from models import MockJAMBQuestion as Q, MockJAMBPassage as P
    q = Q.query.filter(or_(Q.image_url.ilike('http://%'), Q.image_url.ilike('https://%'),
                           Q.image_url.ilike('//%'))).count()
    p = P.query.filter(or_(P.image_url.ilike('http://%'), P.image_url.ilike('https://%'),
                           P.image_url.ilike('//%'))).count()
    return q + p


def repair(limit=40, budget_s=40):
    """Copy pictures hosted on other websites onto this server, and fix '185 o'
    degree options. A picture that can't be downloaded is removed and its
    question goes to the needs-images queue (bank) so someone uploads it.
    Works in batches; returns {saved, failed, left, degrees}."""
    from models import db, MockJAMBQuestion as Q, MockJAMBPassage as P
    ext = or_(Q.image_url.ilike('http://%'), Q.image_url.ilike('https://%'), Q.image_url.ilike('//%'))
    start = time.monotonic()
    saved = failed = 0
    rows = Q.query.filter(ext).order_by(Q.id).limit(limit).all()
    pext = or_(P.image_url.ilike('http://%'), P.image_url.ilike('https://%'), P.image_url.ilike('//%'))
    prow = P.query.filter(pext).order_by(P.id).limit(max(0, limit - len(rows))).all()
    for obj in rows + prow:
        if time.monotonic() - start > budget_s:
            break
        new = save_copy(obj.image_url)
        if new:
            obj.image_url = new
            saved += 1
        else:
            obj.image_url = None
            if isinstance(obj, Q):
                obj.needs_image = True
                obj.image_not_needed = False
            else:
                for q in obj.questions:
                    q.needs_image = True
                    q.image_not_needed = False
            failed += 1
        db.session.commit()
    degrees = fix_all_degrees() + fix_all_powers()
    return {'saved': saved, 'failed': failed, 'left': external_count(), 'degrees': degrees}


def fix_all_degrees():
    """Turn '185 o' options into '185°' across all Mock JAMB questions."""
    from models import db, MockJAMBQuestion as Q
    degrees = 0
    pats = [f'%{d}{sp}{o}' for d in '0123456789' for sp in ('', ' ') for o in ('o', 'º', '˚')]
    ends = [c.like(pat) for c in (Q.option_a, Q.option_b, Q.option_c, Q.option_d) for pat in pats]
    for q in Q.query.filter(or_(*ends)).limit(5000).all():
        changed = False
        for col in ('option_a', 'option_b', 'option_c', 'option_d'):
            v = getattr(q, col)
            nv = fix_degrees(v)
            if nv != v:
                setattr(q, col, nv)
                changed = True
        degrees += 1 if changed else 0
    if degrees:
        db.session.commit()
    return degrees


# ---------------------------------------------------------------------------
# Where a question came from on myschool.ng — so whoever adds a missing picture
# can open the original page and save the diagram from there.

_MS_URL = re.compile(r'myschool\.ng/classroom/([a-z0-9-]+)/(\d+)', re.I)
_EXAM_TYPE = {'JAMB': 'jamb', 'WAEC': 'waec', 'NECO': 'neco', 'Post-UTME': 'post-utme'}


def myschool_qid(url):
    """The myschool question number in a question link, or None."""
    m = _MS_URL.search(url or '')
    return m.group(2) if m else None


def source_link(q):
    """(url, exact) — the question's own page on myschool.ng when we know its
    number (downloaded in the app, or pasted with its link), otherwise a web
    search for its wording on myschool.ng (exact=False)."""
    from urllib.parse import quote, urlencode
    from utils import myschool as ms
    ref = (q.source_ref or '').strip()
    if (q.source or '') == 'myschool' and ref.isdigit():
        slug = ms.subject_slug(q.subject.name if q.subject is not None else '')
        params = {}
        if _EXAM_TYPE.get(q.exam_body or ''):
            params['exam_type'] = _EXAM_TYPE[q.exam_body]
        if (q.exam_year or '').isdigit():
            params['exam_year'] = q.exam_year
        return f"{ms.BASE}/{slug}/{ref}" + ('?' + urlencode(params) if params else ''), True
    text = re.sub(r'<[^>]+>|\$[^$]*\$|\\\(.*?\\\)', ' ', q.question_text or '')
    words = re.findall(r"[A-Za-z0-9'’]+", text)[:10]
    if not words:
        return None, False
    return 'https://www.google.com/search?q=' + quote('site:myschool.ng "%s"' % ' '.join(words)), False


# "y = kx 2" → "y = kx²": an exponent that lost its superscript when copied. Only
# a lone digit 2–4 right after a variable-like token (one or two lower-case
# letters that aren't an English word, or a closing bracket) inside something
# that reads like maths (has = + − × ÷ or brackets) is raised, so ordinary text
# such as "Paper 2", "in 2 days" or "x = 2" is left alone.
_POW_SKIP = {'is', 'in', 'at', 'of', 'to', 'by', 'be', 'as', 'an', 'or', 'if', 'on', 'it', 'we',
             'no', 'so', 'up', 'do', 'go', 'me', 'my', 'he', 'am', 'us', 'pm',
             'kg', 'ms', 'and', 'the'}
_POW_RE = re.compile(r'((?<![A-Za-z])\d*[a-z]{1,2}|\))\s([2-4])(?![0-9.,/:%])(?=\s*(?:[=+\-−×÷*/)<>≤≥,;]|$))')
_POW_CHARS = str.maketrans('234', '²³⁴')
_MATHY = re.compile(r'[=+−×÷<>≤≥()]|\s-\s')


def fix_powers(text):
    if not text or not _MATHY.search(text):
        return text

    def sub(m):
        tok = m.group(1)
        if tok.lstrip('0123456789').lower() in _POW_SKIP:
            return m.group(0)
        return tok + m.group(2).translate(_POW_CHARS)
    return _POW_RE.sub(sub, text)


def fix_all_powers(limit=20000):
    """Raise lost exponents in Mock JAMB questions and options. Returns the
    number of questions changed."""
    from models import db, MockJAMBQuestion as Q
    cols = ('question_text', 'option_a', 'option_b', 'option_c', 'option_d')
    pats = [f'% {d}' for d in '234'] + [f'% {d} %' for d in '234']
    cond = or_(*[getattr(Q, c).like(p) for c in cols for p in pats])
    n = 0
    for q in Q.query.filter(cond).limit(limit).all():
        changed = False
        for c in cols:
            v = getattr(q, c)
            nv = fix_powers(v)
            if nv != v:
                setattr(q, c, nv)
                changed = True
        n += 1 if changed else 0
    if n:
        db.session.commit()
    return n
