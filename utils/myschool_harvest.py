"""In-app, resumable myschool.ng harvest — the server-side engine behind the
one-click "Download from myschool" button in the Mock JAMB question bank.

It walks a queue of (subject, year) cells, and on each step pulls a handful of
questions, classifies them into the app's section/topic/sub-topic taxonomy and
saves them straight into the central bank — de-duplicated by the myschool
question id (``source='myschool'``, ``source_ref=<qid>``) so re-runs never add a
question twice. Progress lives in ``SchoolSettings`` so a step is fully
resumable: the browser calls ``harvest_step`` repeatedly until it reports
``done`` or ``paused``.

Questions that depend on a figure we can't capture are skipped and counted
(the plain-text stem alone would be unanswerable); tables are folded into the
stem text and kept. Any genuine figure image found is re-hosted locally.
"""
from __future__ import annotations

from datetime import datetime

_KEY = 'mj_myschool_harvest'


def get_state():
    from models import SchoolSettings
    return SchoolSettings.get(_KEY, None)


def save_state(state):
    from models import SchoolSettings
    SchoolSettings.set(_KEY, state, value_type='json')


def _blank_counters():
    return dict(added=0, duplicates=0, skipped=0, needs_image=0,
                tables=0, images=0)


def start_harvest(subjects, exam='jamb', year_min=None, year_max=None, max_pages=60):
    """Begin (or restart) a harvest. ``subjects`` is a list of
    ``{'id': subject_id, 'name': subject_name}``. Years default to a sensible
    JAMB span when unset. Returns the public state."""
    from utils import myschool as ms
    exam = (exam or 'jamb').strip().lower()
    y1 = int(year_min) if year_min else 2001
    y2 = int(year_max) if year_max else datetime.now().year - 1
    if y1 > y2:
        y1, y2 = y2, y1
    years = list(range(y1, y2 + 1))
    cells = []
    for s in subjects:
        slug = ms.subject_slug(s['name'])
        for y in years:
            cells.append({'subject_id': s['id'], 'subject': s['name'],
                          'slug': slug, 'year': y})
    state = {
        'status': 'running' if cells else 'done',
        'exam': exam, 'cells': cells, 'ci': 0, 'ids': None,
        'max_pages': int(max_pages), 'current': None,
        'per_subject': {}, 'found': {}, 'last_error': '',
        'subjects': sorted({c['subject'] for c in cells}),
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    state.update(_blank_counters())
    save_state(state)
    return _public(state)


def _rehost_image(url):
    """Re-host a genuine question figure locally as PNG; returns its static URL, or
    None. Handles both a hosted URL (``/storage/classroom/…`` NuxtImg) and an inline
    ``data:image/…;base64`` figure embedded straight in the page. Best-effort and
    never fatal."""
    try:
        import os
        import secrets
        from io import BytesIO
        from PIL import Image
        from flask import current_app
        if url.startswith('data:'):
            import base64
            b64 = url.split(',', 1)[1] if ',' in url else ''
            content = base64.b64decode(b64)
        else:
            import requests
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code != 200:
                return None
            content = r.content
        if not content or len(content) > 8 * 1024 * 1024:
            return None
        im = Image.open(BytesIO(content)).convert('RGB')
        im.thumbnail((1400, 1400))
        name = secrets.token_hex(8) + '.png'
        folder = os.path.join(current_app.root_path, 'static', 'uploads', 'mock_jamb')
        os.makedirs(folder, exist_ok=True)
        im.save(os.path.join(folder, name), 'PNG')
        # build the static URL directly (works in a request, a background job or a
        # test) — same result as url_for('static', …), no request context needed.
        static_path = (current_app.static_url_path or '/static').rstrip('/')
        return f'{static_path}/uploads/mock_jamb/{name}'
    except Exception:
        return None


def _valid_section(subject_name, section):
    try:
        from utils.jamb_blueprint import sections_for
        keys = {s['section'] for s in sections_for(subject_name)}
        return section if section in keys else None
    except Exception:
        return None


def _get_or_create_passage(subject_id, kind, body):
    """Find (or create) the shared bank passage for a comprehension/cloze stimulus,
    de-duplicated by its text so every question that quotes the same passage links
    to one ``MockJAMBPassage`` (mock_exam_id NULL = bank)."""
    from models import db, MockJAMBPassage
    from sqlalchemy import func
    p = MockJAMBPassage.query.filter_by(
        subject_id=subject_id, mock_exam_id=None, body=body).first()
    if p:
        return p
    base = (db.session.query(func.coalesce(func.max(MockJAMBPassage.order), 0))
            .filter(MockJAMBPassage.mock_exam_id.is_(None),
                    MockJAMBPassage.subject_id == subject_id).scalar())
    p = MockJAMBPassage(mock_exam_id=None, subject_id=subject_id,
                        section=kind, kind=kind, body=body, order=base + 1)
    db.session.add(p)
    db.session.flush()
    return p


def _process_one(cell, qid, state, session):
    from models import db, MockJAMBQuestion
    from sqlalchemy import func
    from utils import myschool as ms

    sid = cell['subject_id']
    # de-dup by the stable myschool question id
    if MockJAMBQuestion.query.filter_by(
            subject_id=sid, source='myschool', source_ref=str(qid)).first():
        state['duplicates'] += 1
        return
    html = ms.fetch(ms.question_url(cell['slug'], state['exam'], cell['year'], qid), session)
    if not html:
        state['skipped'] += 1
        return
    p = ms.parse_detail(html)
    if not p:
        state['skipped'] += 1
        return

    # English (and any passage subject): myschool's own instruction block is a more
    # reliable signal than keyword classification, so trust it — group passage
    # questions under a shared passage, and tag novel questions with the real book.
    # ``set_text`` is the recommended text named in the listing badge for THIS
    # question (English: the novel; Literature: the prose/drama/poetry text).
    set_text = (cell.get('texts') or {}).get(str(qid))
    passage = None
    if p.get('is_novel'):
        sec = 'novel'
        top = (p.get('novel_title') or set_text
               or ms.novel_for_year(cell['year']) or 'Recommended Novel')
        sub = None
    elif p.get('passage_text'):
        sec = ms.passage_kind(p['passage_text'], p['stem'])   # 'comprehension' | 'cloze'
        top, sub = None, None
        passage = _get_or_create_passage(sid, sec, p['passage_text'])
    else:
        sec, top, sub = ms.classify(cell['subject'], p['stem'] + ' ' + ' '.join(p['options']),
                                    year=cell['year'], novel_title=set_text)
        # Literature: tag a text-based question (prose/drama/poetry) with the actual
        # set text, mirroring how English novel questions carry the book title.
        if set_text and sec in ('prose', 'drama', 'poetry'):
            top = set_text
    # Literature's paper has no novel/comprehension/cloze section (those are English).
    # myschool's own note occasionally flags a Literature recommended-text question as a
    # "novel", or wraps an unseen extract as a passage — remap those to a real Literature
    # section (its novels are prose; any extract is appreciation) so the draw can serve
    # them, instead of _valid_section dropping the question to section=None (never shown).
    if ms.norm_subject(cell['subject']) == 'literature in english' and \
            sec in ('novel', 'comprehension', 'cloze'):
        if sec == 'novel' and not top:
            top = set_text or p.get('novel_title')
        sec = 'prose' if sec == 'novel' else 'appreciation'
    sec = _valid_section(cell['subject'], sec)
    image_url = _rehost_image(p['image_url']) if p.get('image_url') else None
    if image_url:
        state['images'] += 1
    # A figure-dependent question with no image we could fetch is saved but held
    # out of exams (needs_image) until an admin supplies the diagram.
    needs_image = bool(p['figure_dependent']) and not image_url

    base = (db.session.query(func.coalesce(func.max(MockJAMBQuestion.order), 0))
            .filter(MockJAMBQuestion.mock_exam_id.is_(None),
                    MockJAMBQuestion.subject_id == sid).scalar())
    db.session.add(MockJAMBQuestion(
        mock_exam_id=None, subject_id=sid, section=sec, exam_body='JAMB',
        passage_id=(passage.id if passage else None),
        question_text=p['stem'], option_a=p['options'][0], option_b=p['options'][1],
        option_c=p['options'][2], option_d=p['options'][3], correct_option=p['correct'],
        marks=1, topic=top, subtopic=sub, exam_year=str(cell['year']),
        source='myschool', source_ref=str(qid), image_url=image_url,
        needs_image=needs_image, order=base + 1))
    db.session.commit()
    state['added'] += 1
    state['per_subject'][cell['subject']] = state['per_subject'].get(cell['subject'], 0) + 1
    if needs_image:
        state['needs_image'] = state.get('needs_image', 0) + 1
    if p['has_table']:
        state['tables'] += 1


def harvest_step(max_questions=6):
    """Advance the harvest by up to ``max_questions`` questions. Returns the
    public state. Safe to call repeatedly from the browser chunker."""
    from utils import myschool as ms
    state = get_state()
    if not state or state.get('status') != 'running':
        return _public(state)
    session = ms._session()
    processed = 0
    try:
        while processed < max_questions:
            if state['ci'] >= len(state['cells']):
                state['status'] = 'done'
                break
            cell = state['cells'][state['ci']]
            if state.get('ids') is None:
                state['current'] = {'subject': cell['subject'], 'year': cell['year']}
                # English & Literature: the listing badge names the year's set text
                # (English: the novel; Literature: the prose/drama/poetry text, which
                # varies by page) — capture it per question so the right title tags
                # each question.
                if ms.norm_subject(cell['subject']) in ('english language', 'literature in english'):
                    state['ids'], cell['texts'] = ms.list_ids_and_texts(
                        cell['slug'], state['exam'], cell['year'], session,
                        max_pages=state.get('max_pages', 60), delay=0.3)
                else:
                    state['ids'] = ms.list_question_ids(
                        cell['slug'], state['exam'], cell['year'], session,
                        max_pages=state.get('max_pages', 60), delay=0.3)
                found = state.setdefault('found', {})
                found[cell['subject']] = found.get(cell['subject'], 0) + len(state['ids'])
            if not state['ids']:
                state['ci'] += 1
                state['ids'] = None
                continue
            qid = state['ids'].pop(0)
            _process_one(cell, qid, state, session)
            processed += 1
        state['last_error'] = ''
    except Exception as exc:                     # network hiccup → pausable
        from models import db
        db.session.rollback()
        state['status'] = 'paused'
        state['last_error'] = f'{type(exc).__name__}: {exc}'[:200]
    state['updated_at'] = datetime.now().isoformat(timespec='seconds')
    save_state(state)
    return _public(state)


def pause_harvest():
    state = get_state()
    if state and state.get('status') == 'running':
        state['status'] = 'paused'
        save_state(state)
    return _public(state)


def resume_harvest():
    state = get_state()
    if state and state.get('status') == 'paused':
        state['status'] = 'running'
        state['last_error'] = ''
        save_state(state)
    return _public(state)


def _public(state):
    """Trim the internal state to what the UI needs (drops the big id/cell lists)."""
    if not state:
        return {'status': 'none'}
    total = len(state.get('cells') or [])
    done_cells = min(state.get('ci', 0), total)
    # subjects that turned up no questions at all — usually not offered under the
    # chosen exam on myschool (only surfaced once we've looked at them).
    found = state.get('found', {})
    empty = []
    if state.get('status') == 'done':
        empty = [s for s in state.get('subjects', []) if found.get(s, 0) == 0]
    return {
        'status': state.get('status', 'none'),
        'exam': state.get('exam'),
        'cells_total': total, 'cells_done': done_cells,
        'percent': (round(100 * done_cells / total, 1) if total else 0),
        'added': state.get('added', 0), 'duplicates': state.get('duplicates', 0),
        'skipped': state.get('skipped', 0),
        'needs_image': state.get('needs_image', 0),
        'tables': state.get('tables', 0), 'images': state.get('images', 0),
        'current': state.get('current'), 'per_subject': state.get('per_subject', {}),
        'empty_subjects': empty,
        'last_error': state.get('last_error', ''), 'updated_at': state.get('updated_at'),
    }
