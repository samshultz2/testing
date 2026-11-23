"""Fetch a missing diagram from myschool.ng and attach it to a bank question.

For one question:
1. Find its page on myschool. Questions downloaded in the app (or pasted with
   their link) already know their myschool number. For others, the subject's
   listing for that exam and year is scanned and the question is matched by its
   wording. A scan that runs out of time resumes on the next call, because the
   page cache lives for the process.
2. Read the page for a figure (a hosted image or an inline picture). When the
   plain page has none — myschool draws many diagrams with JavaScript — and
   Playwright with Chromium is installed on the server, the page is rendered in
   a headless browser and read again.
3. Save a copy on this server and attach it; the question leaves the
   needs-images queue.

``fetch_figure(q)`` returns ``{status, message, url?, image_url?}`` where status
is one of ``attached``, ``no_image`` (page found, no diagram exposed),
``not_found``, ``searching`` (call again to continue) or ``error``.
"""
import re
import time

_EXAM_TYPE = {'JAMB': 'jamb', 'WAEC': 'waec', 'NECO': 'neco', 'Post-UTME': 'post-utme'}

# (slug, exam, year) -> {'ids': [...] | None, 'texts': {qid: norm}, 'pages_done': bool, 'scanned': set}
_CACHE = {}
_CACHE_TTL = 3600


def _norm(text):
    text = re.sub(r'<[^>]+>|\$[^$]*\$|\\\(.*?\\\)', ' ', text or '')
    return ' '.join(re.findall(r'[a-z0-9]+', text.lower()))


def _same(a, b):
    """Is listing/detail text ``b`` the same question as stem ``a``?"""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or (len(a) >= 25 and (a[:60] in b or b[:60] in a)):
        return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta) >= 5 and len(ta & tb) / max(len(ta | tb), 1) >= 0.75


def _entry(key):
    e = _CACHE.get(key)
    if not e or time.monotonic() - e['at'] > _CACHE_TTL:
        e = _CACHE[key] = {'at': time.monotonic(), 'ids': None, 'texts': {}, 'scanned': set()}
    return e


def _listing(slug, exam, year, session, e, deadline):
    """Fill the cache with this subject-year's question ids, and any question
    text the listing pages show beside each link."""
    from bs4 import BeautifulSoup
    from utils import myschool as ms
    if e['ids'] is not None:
        return
    ids, seen = [], set()
    for page in range(1, 61):
        if time.monotonic() > deadline:
            return                                   # resume next call
        html = ms.fetch(f"{ms.BASE}/{slug}?exam_type={exam}&exam_year={year}&page={page}", session)
        if not html:
            break
        soup = BeautifulSoup(html, 'html.parser')
        new = 0
        for a in soup.find_all('a', href=True):
            m = re.search(rf"/classroom/{re.escape(slug)}/(\d+)", a['href'])
            if not m or m.group(1) in seen:
                continue
            qid = m.group(1)
            seen.add(qid); ids.append(qid); new += 1
            node, text = a, ''
            for _ in range(6):                      # nearest block with real text
                node = node.parent
                if node is None:
                    break
                text = node.get_text(' ', strip=True)
                if len(text) > 30:
                    break
            if text:
                e['texts'][qid] = text
        if not new:
            break
    e['ids'] = ids


def find_question_page(q, session=None, budget_s=20):
    """(url, status). status: 'found', 'not_found', 'searching'."""
    from utils import myschool as ms
    subject = q.subject.name if q.subject is not None else ''
    slug = ms.subject_slug(subject)
    year = (q.exam_year or '').strip()
    ref = (q.source_ref or '').strip()
    exams = [_EXAM_TYPE[q.exam_body]] if _EXAM_TYPE.get(q.exam_body or '') else ['jamb', 'waec']
    if (q.source or '') == 'myschool' and ref.isdigit():
        return ms.question_url(slug, exams[0], year or '', ref), 'found'
    if not year.isdigit():
        return None, 'not_found'
    session = session or ms._session()
    deadline = time.monotonic() + budget_s
    for exam in exams:
        e = _entry((slug, exam, year))
        _listing(slug, exam, year, session, e, deadline)
        if e['ids'] is None:
            return None, 'searching'
        for qid, text in e['texts'].items():
            if _same(q.question_text, text):
                return ms.question_url(slug, exam, year, qid), 'found'
        # the listing didn't show the wording: open each question in turn
        for qid in e['ids']:
            if qid in e['scanned']:
                continue
            if time.monotonic() > deadline:
                return None, 'searching'
            html = ms.fetch(ms.question_url(slug, exam, year, qid), session)
            e['scanned'].add(qid)
            parsed = ms.parse_detail(html) if html else None
            if parsed:
                e['texts'][qid] = parsed['stem']
                e.setdefault('pages', {})[qid] = html
                if _same(q.question_text, parsed['stem']):
                    return ms.question_url(slug, exam, year, qid), 'found'
    return None, 'not_found'


def _browser_html(url):
    """The page as a browser sees it (after JavaScript), or None when Playwright
    and Chromium aren't installed on this server."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(args=['--no-sandbox'])
            try:
                page = br.new_page()
                page.goto(url, wait_until='networkidle', timeout=40000)
                page.wait_for_timeout(900)
                return page.content()
            finally:
                br.close()
    except Exception:
        return None


def browser_available():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def fetch_figure(q, session=None, budget_s=20):
    """Find, download and attach the diagram for bank question ``q``."""
    from models import db
    from utils import myschool as ms
    from utils import mock_figures
    session = session or ms._session()
    try:
        url, st = find_question_page(q, session, budget_s=budget_s)
    except Exception as exc:                          # network trouble
        return {'status': 'error', 'message': f'Could not reach myschool.ng ({exc.__class__.__name__}).'}
    if st == 'searching':
        return {'status': 'searching', 'message': 'Still looking through myschool.ng…'}
    if not url:
        why = ('it has no exam year' if not (q.exam_year or '').strip().isdigit()
               else 'no question with this wording was found')
        return {'status': 'not_found', 'message': f'Not found on myschool.ng — {why}.'}
    qid = mock_figures.myschool_qid(url)
    html = None
    for e in _CACHE.values():
        html = (e.get('pages') or {}).get(qid) or html
    html = html or ms.fetch(url, session)
    parsed = ms.parse_detail(html) if html else None
    img = parsed.get('image_url') if parsed else None
    used_browser = False
    if not img:
        rendered = _browser_html(url)
        if rendered:
            used_browser = True
            p2 = ms.parse_detail(rendered)
            img = p2.get('image_url') if p2 else None
    # remember where it came from, so the question links to its page from now on
    if qid and (q.source or '') != 'myschool':
        q.source, q.source_ref = 'myschool', qid
    if not img:
        db.session.commit()
        hint = ('' if used_browser or browser_available() else
                ' myschool draws many diagrams with JavaScript; open the page and save it by hand.')
        return {'status': 'no_image', 'url': url,
                'message': 'Found the question, but its page has no downloadable diagram.' + hint}
    saved = mock_figures.save_copy(img)
    if not saved:
        db.session.commit()
        return {'status': 'error', 'url': url, 'message': 'Found the diagram but could not download it.'}
    q.image_url = saved
    q.needs_image = False
    q.image_not_needed = False
    db.session.commit()
    return {'status': 'attached', 'url': url, 'image_url': saved,
            'message': 'Diagram added' + (' (rendered in a browser)' if used_browser else '') + '.'}
