"""Import Mock JAMB questions from the ALOC questions API (questions.aloc.com.ng).

ALOC returns flat, un-topiced objective questions per subject (UTME / WASSCE /
Post-UTME) in a random order on every poll. We fetch batches, normalise them and
insert them into the central question bank (``mock_exam_id`` NULL), keeping the
past-question ``exam_year`` and re-hosting any question image locally.

De-duplication is belt-and-braces: by the ALOC question id (``source_ref``) AND
by the normalised question text, so re-polling (which returns questions in a new
random order) never stores a duplicate.

Multiple access tokens are supported for fail-over: tokens are tried in order and
the importer rotates to the next whenever one is rejected or exhausted (HTTP
401/403/429 or a non-OK ALOC status), so a depleted daily quota transparently
falls through to the next token.

ALOC has no topics/sub-topics, so imported questions come in untagged — tagging
is optional; the JAMB paper draw keys off ``section`` (which the admin can set as
an import default or assign later), never topic.
"""
from __future__ import annotations

import html
import re

ALOC_BASE = 'https://questions.aloc.com.ng/api/v2'
TOKENS_KEY = 'aloc_access_tokens'          # newline/comma separated list
LEGACY_TOKEN_KEY = 'aloc_access_token'     # earlier single-token setting
EXAM_TYPES = ('utme', 'wassce', 'post-utme')

# Our (normalised) subject name  ->  ALOC subject slug. Only subjects ALOC serves.
SUBJECT_SLUGS = {
    'english language': 'english',
    'mathematics': 'mathematics',
    'physics': 'physics',
    'chemistry': 'chemistry',
    'biology': 'biology',
    'economics': 'economics',
    'government': 'government',
    'commerce': 'commerce',
    'accounting': 'accounting',
    'geography': 'geography',
    'christian religious studies': 'crk',
    'civic education': 'civiledu',
    'literature in english': 'englishlit',
}


def aloc_slug(subject_name):
    from utils.jamb_blueprint import norm_subject
    return SUBJECT_SLUGS.get(norm_subject(subject_name))


# ---------------------------------------------------------------------------
# token storage (a list, for fail-over)
# ---------------------------------------------------------------------------

def parse_tokens(raw):
    """Split a pasted blob of tokens (newlines/commas) into a de-duped list."""
    parts = re.split(r'[\s,]+', raw or '')
    out, seen = [], set()
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def get_tokens():
    from models import SchoolSettings
    try:
        raw = SchoolSettings.get(TOKENS_KEY)
        if not raw:
            raw = SchoolSettings.get(LEGACY_TOKEN_KEY) or ''
        return parse_tokens(raw)
    except Exception:
        return []


def save_tokens(tokens):
    from models import SchoolSettings
    tokens = tokens if isinstance(tokens, list) else parse_tokens(tokens)
    SchoolSettings.set(TOKENS_KEY, '\n'.join(tokens), 'string',
                       'Access token(s) for the ALOC questions API (one per line)')


def mask_token(tok):
    tok = tok or ''
    return (tok[:9] + '…' + tok[-3:]) if len(tok) > 14 else (tok[:4] + '…')


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def _clean(text):
    """ALOC embeds simple HTML (<b>, <i>, entities). Strip tags + unescape."""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', str(text))
    return html.unescape(text).strip()


def _norm_text(text):
    return re.sub(r'\s+', ' ', (text or '').lower()).strip()


def normalise_item(raw):
    """Turn a raw ALOC question object into our shape, or None if unusable
    (missing text/answer, or a genuine 5-option question — our model holds four)."""
    if not isinstance(raw, dict):
        return None
    q = _clean(raw.get('question'))
    opt = raw.get('option') or {}
    a, b, c, d = (_clean(opt.get(k)) for k in ('a', 'b', 'c', 'd'))
    e = _clean(opt.get('e'))
    answer = (raw.get('answer') or '').strip().lower()
    if not q or answer not in ('a', 'b', 'c', 'd'):
        return None
    if e:                      # a real 5th option would be lost — skip to stay correct
        return None
    if not (a and b and c and d):
        return None
    year = str(raw.get('examyear') or '').strip() or None
    return {
        'ext_id': str(raw.get('id') or '') or None,
        'question': q, 'a': a, 'b': b, 'c': c, 'd': d,
        'correct': answer.upper(),
        'image': (raw.get('image') or '').strip() or None,
        'exam_year': (year[:8] if year else None),
    }


# ---------------------------------------------------------------------------
# image re-hosting (store questions' images locally, not hot-linked)
# ---------------------------------------------------------------------------

def import_image(url, timeout=30):
    """Download a question image and re-host it under static/uploads/mock_jamb,
    re-encoded to PNG. Returns the local URL, or the original URL if the download
    fails (so the question still shows an image), or None."""
    if not url:
        return None
    if not url.lower().startswith(('http://', 'https://')):
        return url
    try:
        import os
        import secrets
        import requests
        from io import BytesIO
        from flask import current_app, url_for
        from utils.uploads import open_image
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200 or not r.content:
            return url
        im = open_image(BytesIO(r.content)).convert('RGB')
        name = secrets.token_hex(8) + '.png'
        folder = os.path.join(current_app.root_path, 'static', 'uploads', 'mock_jamb')
        os.makedirs(folder, exist_ok=True)
        im.save(os.path.join(folder, name), 'PNG')
        return url_for('static', filename='uploads/mock_jamb/' + name)
    except Exception:
        return url          # fall back to the remote URL rather than losing it


# ---------------------------------------------------------------------------
# fetching (single token) — returns (items, error, token_bad)
# ---------------------------------------------------------------------------

def fetch_batch(token, slug, examtype='utme', year=None, timeout=45):
    """Fetch one ALOC batch (~40 questions). Returns ``(items, error, token_bad)``
    where ``token_bad`` asks the caller to rotate to the next token (auth/quota).
    Never raises."""
    import requests
    params = {'subject': slug, 'type': examtype}
    if year:
        params['year'] = year
    headers = {'AccessToken': token, 'Accept': 'application/json'}
    try:
        r = requests.get(f'{ALOC_BASE}/m', params=params, headers=headers, timeout=timeout)
    except Exception as exc:
        return [], f'Network error contacting ALOC: {exc}', False
    # ALOC uses assorted 4xx codes for a bad/expired/exhausted token (e.g. 401,
    # 403, 406, 429) — treat any client error as "rotate to the next token".
    if 400 <= r.status_code < 500:
        return [], f'token rejected/exhausted (HTTP {r.status_code})', True
    if r.status_code != 200:
        return [], f'ALOC returned HTTP {r.status_code}.', False
    try:
        payload = r.json()
    except Exception:
        return [], 'ALOC returned a non-JSON response.', False
    status = payload.get('status')
    if status not in (200, '200', None):
        # ALOC signals quota/limit problems in the body with a non-200 status.
        return [], f'ALOC status {status}', True
    data = payload.get('data')
    if isinstance(data, dict):
        data = [data]
    return (data or []), None, False


# ---------------------------------------------------------------------------
# import (multi-token, deduped)
# ---------------------------------------------------------------------------

def import_questions(subject_id, subject_name, tokens, examtype='utme', year=None,
                     target=40, default_section=None, max_batches=12):
    """Import up to ``target`` new ALOC questions for a subject into the bank,
    rotating across ``tokens`` on rejection/exhaustion.

    Returns ``{added, skipped, duplicates, tokens_used, tokens_total, slug, error}``.
    De-dupes by ALOC id and by question text, against the existing bank and within
    this run.
    """
    from sqlalchemy import func
    from models import db, MockJAMBQuestion

    slug = aloc_slug(subject_name)
    if not slug:
        return {'added': 0, 'skipped': 0, 'duplicates': 0, 'tokens_used': 0,
                'tokens_total': 0, 'slug': None, 'error': f'ALOC does not serve “{subject_name}”.'}
    tokens = [t for t in (tokens if isinstance(tokens, list) else parse_tokens(tokens)) if t]
    if not tokens:
        return {'added': 0, 'skipped': 0, 'duplicates': 0, 'tokens_used': 0,
                'tokens_total': 0, 'slug': slug, 'error': 'No ALOC access token provided.'}

    existing = MockJAMBQuestion.query.filter_by(
        subject_id=subject_id, mock_exam_id=None).all()
    seen_ids = {q.source_ref for q in existing if q.source_ref}
    seen_texts = {_norm_text(q.question_text) for q in existing}
    order = db.session.query(func.coalesce(func.max(MockJAMBQuestion.order), 0)).filter(
        MockJAMBQuestion.mock_exam_id.is_(None), MockJAMBQuestion.subject_id == subject_id).scalar()

    added = skipped = duplicates = 0
    exam_body = 'WAEC' if examtype == 'wassce' else 'JAMB'
    ti = 0                       # current token index
    tokens_used = set()
    error = None
    batches = 0
    while added < target and ti < len(tokens) and batches < max_batches:
        batches += 1
        token = tokens[ti]
        tokens_used.add(ti)
        items, err, token_bad = fetch_batch(token, slug, examtype, year)
        if token_bad:
            ti += 1              # rotate to the next token
            error = err
            continue
        if err:
            error = err
            break
        if not items:
            break
        progressed = False
        for raw in items:
            if added >= target:
                break
            norm = normalise_item(raw)
            if not norm:
                skipped += 1
                continue
            ntext = _norm_text(norm['question'])
            if (norm['ext_id'] and norm['ext_id'] in seen_ids) or ntext in seen_texts:
                duplicates += 1
                continue
            if norm['ext_id']:
                seen_ids.add(norm['ext_id'])
            seen_texts.add(ntext)
            order += 1
            added += 1
            progressed = True
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=subject_id, section=default_section,
                exam_body=exam_body, source='aloc', source_ref=norm['ext_id'],
                exam_year=norm['exam_year'], question_text=norm['question'],
                option_a=norm['a'], option_b=norm['b'], option_c=norm['c'],
                option_d=norm['d'], correct_option=norm['correct'],
                image_url=import_image(norm['image']), marks=1, order=order))
        # A batch that yielded nothing genuinely new (all dup/skip) still means the
        # token works; keep polling for fresh random batches until max_batches.
        if not progressed and duplicates == 0 and skipped == 0:
            break
    db.session.commit()
    return {'added': added, 'skipped': skipped, 'duplicates': duplicates,
            'tokens_used': len(tokens_used), 'tokens_total': len(tokens),
            'slug': slug, 'error': error}
