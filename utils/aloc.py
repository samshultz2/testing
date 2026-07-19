"""Import Mock JAMB questions from the ALOC questions API (questions.aloc.com.ng).

ALOC returns flat, un-topiced objective questions per subject (UTME / WASSCE /
Post-UTME). We fetch batches, normalise them and insert them into the central
question bank (``mock_exam_id`` NULL), de-duplicating by the ALOC question id via
``source='aloc'`` + ``source_ref``. ALOC has no topics/sub-topics or fine JAMB
sections, so imported questions are left untagged (the sitting still serves them
via the fallback draw) or given a single default section the admin chooses; they
can be re-tagged later in the bank.

The access token is passed in the ``AccessToken`` header; store it once in
``SchoolSettings`` (key ``aloc_access_token``) so imports don't need it re-typed.
"""
from __future__ import annotations

import html
import re

ALOC_BASE = 'https://questions.aloc.com.ng/api/v2'
SETTING_KEY = 'aloc_access_token'
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


def get_token():
    from models import SchoolSettings
    try:
        return SchoolSettings.get(SETTING_KEY) or ''
    except Exception:
        return ''


def save_token(token):
    from models import SchoolSettings
    SchoolSettings.set(SETTING_KEY, (token or '').strip(), 'string',
                       'Access token for the ALOC questions API')


def _clean(text):
    """ALOC embeds simple HTML (<b>, <i>, entities). Strip tags + unescape so the
    stored question/option is plain text."""
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', str(text))
    return html.unescape(text).strip()


def normalise_item(raw):
    """Turn a raw ALOC question object into our shape, or None if unusable
    (missing text/answer, or a 5-option question whose 5th option is in use —
    our model holds four options)."""
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
    return {
        'ext_id': str(raw.get('id') or ''),
        'question': q, 'a': a, 'b': b, 'c': c, 'd': d,
        'correct': answer.upper(),
        'image': (raw.get('image') or '').strip() or None,
        'examyear': str(raw.get('examyear') or '').strip() or None,
    }


def fetch_batch(token, slug, examtype='utme', year=None, timeout=45):
    """Fetch one ALOC batch (~40 questions) for a subject. Returns (items, error)
    where items is a list of raw dicts. Never raises."""
    import requests
    params = {'subject': slug, 'type': examtype}
    if year:
        params['year'] = year
    headers = {'AccessToken': token, 'Accept': 'application/json'}
    try:
        r = requests.get(f'{ALOC_BASE}/m', params=params, headers=headers, timeout=timeout)
    except Exception as exc:
        return [], f'Network error contacting ALOC: {exc}'
    if r.status_code == 401 or r.status_code == 403:
        return [], 'ALOC rejected the access token (check it is correct and active).'
    if r.status_code != 200:
        return [], f'ALOC returned HTTP {r.status_code}.'
    try:
        payload = r.json()
    except Exception:
        return [], 'ALOC returned a non-JSON response.'
    data = payload.get('data')
    if isinstance(data, dict):
        data = [data]
    return (data or []), None


def import_questions(subject_id, subject_name, token, examtype='utme', year=None,
                     target=40, default_section=None, max_batches=8):
    """Import up to ``target`` new ALOC questions for a subject into the bank.

    Returns a result dict: ``{added, skipped, duplicates, error, slug}``.
    De-dupes against questions already imported from ALOC for this subject (by
    external id) and within this run.
    """
    from sqlalchemy import func
    from models import db, MockJAMBQuestion

    slug = aloc_slug(subject_name)
    if not slug:
        return {'added': 0, 'skipped': 0, 'duplicates': 0, 'slug': None,
                'error': f'ALOC does not serve “{subject_name}”.'}
    token = (token or '').strip()
    if not token:
        return {'added': 0, 'skipped': 0, 'duplicates': 0, 'slug': slug,
                'error': 'No ALOC access token provided.'}

    seen = {r for (r,) in db.session.query(MockJAMBQuestion.source_ref).filter(
        MockJAMBQuestion.subject_id == subject_id, MockJAMBQuestion.source == 'aloc',
        MockJAMBQuestion.source_ref.isnot(None)).all()}
    order = db.session.query(func.coalesce(func.max(MockJAMBQuestion.order), 0)).filter(
        MockJAMBQuestion.mock_exam_id.is_(None), MockJAMBQuestion.subject_id == subject_id).scalar()

    added = skipped = duplicates = 0
    exam_body = 'WAEC' if examtype == 'wassce' else 'JAMB'
    error = None
    for _ in range(max_batches):
        if added >= target:
            break
        items, err = fetch_batch(token, slug, examtype, year)
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
            ref = norm['ext_id']
            if ref and ref in seen:
                duplicates += 1
                continue
            if ref:
                seen.add(ref)
            order += 1
            added += 1
            progressed = True
            db.session.add(MockJAMBQuestion(
                mock_exam_id=None, subject_id=subject_id, section=default_section,
                exam_body=exam_body, source='aloc', source_ref=ref or None,
                question_text=norm['question'], option_a=norm['a'], option_b=norm['b'],
                option_c=norm['c'], option_d=norm['d'], correct_option=norm['correct'],
                image_url=norm['image'], marks=1, order=order))
        # ALOC batches are random; if a whole batch was all duplicates, keep trying,
        # but stop if we made no progress AND found nothing new to avoid a long loop.
        if not progressed and duplicates == 0 and skipped == 0:
            break
    db.session.commit()
    return {'added': added, 'skipped': skipped, 'duplicates': duplicates,
            'slug': slug, 'error': error}
