"""Look up book metadata by ISBN across several public catalogues/aggregators
— Open Library (twice, via two differently-indexed endpoints), Google Books,
the Internet Archive, Crossref, and (optionally, once a key is configured)
ISBNdb — so a title missing from one source is often still found in another.
See ``_sources()`` for the exact list and try order.

Uses the stdlib-based ``utils.http`` client (proxy/timeout-safe) so a
mismatched ``requests`` can't hang the request. Returns a normalised dict the
book form can consume, or None when nothing is found / the lookup fails.
Never raises — every source is individually try/excepted so one failing or
timing out never blocks the rest.
"""
from __future__ import annotations

import re

from utils.http import get_json

_YEAR = re.compile(r'(\d{4})')


def normalise_isbn(raw):
    """Strip separators; keep digits and a trailing X. Returns '' if implausible."""
    s = re.sub(r'[^0-9Xx]', '', (raw or '')).upper()
    return s if len(s) in (10, 13) else ''


def _isbn13_to_10(isbn13):
    """The ISBN-10 equivalent of a 978-prefixed ISBN-13, or '' when there isn't
    one (979-prefixed codes have no ISBN-10)."""
    if len(isbn13) != 13 or not isbn13.startswith('978'):
        return ''
    core = isbn13[3:12]
    s = sum((10 - i) * int(d) for i, d in enumerate(core))
    check = (11 - (s % 11)) % 11
    return core + ('X' if check == 10 else str(check))


def _isbn10_to_13(isbn10):
    """The ISBN-13 (978-prefixed) equivalent of an ISBN-10."""
    if len(isbn10) != 10:
        return ''
    core = '978' + isbn10[:9]
    s = sum((1 if i % 2 == 0 else 3) * int(d) for i, d in enumerate(core))
    return core + str((10 - (s % 10)) % 10)


def _alternate_isbn(isbn):
    """The other ISBN form (10↔13) for the same book, or '' if none."""
    if len(isbn) == 13:
        return _isbn13_to_10(isbn)
    if len(isbn) == 10:
        return _isbn10_to_13(isbn)
    return ''


def _year(*values):
    for v in values:
        if v:
            m = _YEAR.search(str(v))
            if m:
                return int(m.group(1))
    return None


def _from_openlibrary(isbn):
    url = (f'https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}'
           '&format=json&jscmd=data')
    res = get_json(url, timeout=8)
    if not res.ok:
        return None
    data = res.json() or {}
    rec = data.get(f'ISBN:{isbn}')
    if not rec:
        return None
    authors = ', '.join(a.get('name', '') for a in (rec.get('authors') or []) if a.get('name'))
    publishers = ', '.join(p.get('name', '') for p in (rec.get('publishers') or []) if p.get('name'))
    subjects = ', '.join(s.get('name', '') for s in (rec.get('subjects') or []) if s.get('name'))
    return {
        'title': rec.get('title') or '', 'subtitle': rec.get('subtitle') or '',
        'author': authors, 'publisher': publishers,
        'publication_year': _year(rec.get('publish_date')),
        'subject': (subjects.split(',')[0].strip() if subjects else ''),
        'keywords': subjects, 'description': '', 'language': '',
        'source': 'Open Library',
    }


def _from_google(isbn):
    url = f'https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}'
    res = get_json(url, timeout=8)
    if not res.ok:
        return None
    items = (res.json() or {}).get('items') or []
    if not items:
        return None
    vi = items[0].get('volumeInfo') or {}
    langs = {'en': 'English', 'fr': 'French', 'ha': 'Hausa', 'yo': 'Yoruba', 'ig': 'Igbo'}
    cats = vi.get('categories') or []
    return {
        'title': vi.get('title') or '', 'subtitle': vi.get('subtitle') or '',
        'author': ', '.join(vi.get('authors') or []), 'publisher': vi.get('publisher') or '',
        'publication_year': _year(vi.get('publishedDate')),
        'subject': (cats[0] if cats else ''), 'keywords': ', '.join(cats),
        'description': (vi.get('description') or '')[:2000],
        'language': langs.get(vi.get('language'), vi.get('language') or ''),
        'source': 'Google Books',
    }


def _from_openlibrary_search(isbn):
    """Open Library's search index — a separately-built index from the bibkeys
    API above, so it sometimes has an edition the other one doesn't."""
    url = (f'https://openlibrary.org/search.json?isbn={isbn}&limit=1&'
           'fields=title,subtitle,author_name,publisher,first_publish_year,subject,language')
    res = get_json(url, timeout=8)
    if not res.ok:
        return None
    docs = (res.json() or {}).get('docs') or []
    if not docs or not docs[0].get('title'):
        return None
    d = docs[0]
    subjects = d.get('subject') or []
    return {
        'title': d.get('title') or '', 'subtitle': d.get('subtitle') or '',
        'author': ', '.join(d.get('author_name') or []),
        'publisher': ', '.join((d.get('publisher') or [])[:2]),
        'publication_year': d.get('first_publish_year'),
        'subject': (subjects[0] if subjects else ''), 'keywords': ', '.join(subjects[:10]),
        'description': '', 'language': ', '.join(d.get('language') or []),
        'source': 'Open Library (search index)',
    }


def _from_archive_org(isbn):
    """The Internet Archive's own catalogue (distinct from Open Library, which
    it also runs) — includes many library collections it has scanned or taken
    donations from, including African university and school libraries."""
    url = ('https://archive.org/advancedsearch.php?q=isbn%3A' + isbn
          + '&fl%5B%5D=title&fl%5B%5D=creator&fl%5B%5D=publisher&fl%5B%5D=date'
            '&fl%5B%5D=subject&fl%5B%5D=language&rows=1&page=1&output=json')
    res = get_json(url, timeout=8)
    if not res.ok:
        return None
    docs = ((res.json() or {}).get('response') or {}).get('docs') or []
    if not docs or not docs[0].get('title'):
        return None
    d = docs[0]
    creator = d.get('creator')
    author = ', '.join(creator) if isinstance(creator, list) else (creator or '')
    subject = d.get('subject')
    subjects = subject if isinstance(subject, list) else ([subject] if subject else [])
    publisher = d.get('publisher')
    return {
        'title': d.get('title') or '', 'subtitle': '',
        'author': author, 'publisher': (publisher[0] if isinstance(publisher, list) else publisher) or '',
        'publication_year': _year(d.get('date')),
        'subject': (subjects[0] if subjects else ''), 'keywords': ', '.join(subjects[:10]),
        'description': '', 'language': ', '.join(d.get('language') or []) if isinstance(d.get('language'), list) else (d.get('language') or ''),
        'source': 'Internet Archive',
    }


def _from_crossref(isbn):
    """Crossref indexes some publishers' book/monograph metadata (deposited
    alongside their journal articles) under a work's registered ISBNs."""
    url = f'https://api.crossref.org/works?filter=isbn:{isbn}&rows=1'
    res = get_json(url, timeout=8)
    if not res.ok:
        return None
    items = ((res.json() or {}).get('message') or {}).get('items') or []
    if not items:
        return None
    it = items[0]
    titles = it.get('title') or []
    if not titles:
        return None
    authors = ', '.join(
        ' '.join(filter(None, [a.get('given'), a.get('family')])) for a in (it.get('author') or []))
    pub_date = it.get('published-print') or it.get('published-online') or it.get('published') or {}
    parts = (pub_date.get('date-parts') or [[]])[0]
    year = parts[0] if parts else None
    subjects = it.get('subject') or []
    return {
        'title': titles[0], 'subtitle': '',
        'author': authors, 'publisher': it.get('publisher') or '',
        'publication_year': year,
        'subject': (subjects[0] if subjects else ''), 'keywords': ', '.join(subjects[:10]),
        'description': '', 'language': it.get('language') or '',
        'source': 'Crossref',
    }


def _from_isbndb(isbn):
    """Optional: ISBNdb (isbndb.com) has far broader small-press/regional
    publisher coverage than the free sources above — which is where most
    Nigerian textbook publishers actually turn up. It needs a paid API key;
    configure ISBNDB_API_KEY (Config / env) to turn this source on, otherwise
    it's silently skipped."""
    from config import Config
    key = (Config.ISBNDB_API_KEY or '').strip()
    if not key:
        return None
    res = get_json(f'https://api2.isbndb.com/book/{isbn}', headers={'Authorization': key}, timeout=8)
    if not res.ok:
        return None
    book = (res.json() or {}).get('book') or {}
    title = book.get('title') or ''
    if not title:
        return None
    title_long = book.get('title_long') or ''
    subjects = book.get('subjects') or []
    return {
        'title': title, 'subtitle': (title_long[len(title):].lstrip(' :-') if title_long.startswith(title) else ''),
        'author': ', '.join(book.get('authors') or []), 'publisher': book.get('publisher') or '',
        'publication_year': _year(book.get('date_published')),
        'subject': (subjects[0] if subjects else ''), 'keywords': ', '.join(subjects),
        'description': (book.get('synopsis') or book.get('overview') or '')[:2000],
        'language': book.get('language') or '',
        'source': 'ISBNdb',
    }


def _sources():
    """Tried in order; the first source with a real hit (a title) wins. Free,
    keyless sources first, then the ones that need registration/an optional
    key — see _from_isbndb's docstring for the one meant to fill in Nigerian-
    publisher gaps once a key is configured.

    Referenced by name here (rather than a module-level tuple built once at
    import time) so tests can monkeypatch e.g. ``isbn_lookup._from_google``
    and have ``lookup_isbn`` pick up the replacement."""
    return (_from_openlibrary, _from_google, _from_openlibrary_search,
           _from_archive_org, _from_crossref, _from_isbndb)


def _safe_fetch(fetch, form):
    try:
        return fetch(form)
    except Exception:
        return None


def lookup_isbn(raw_isbn):
    """Normalised book metadata for an ISBN, or None. Best-effort across up to
    six catalogues/aggregators (see ``_sources()``) — each is wrapped so one
    source erroring or timing out never blocks the rest.

    Tries both the given ISBN and its 10↔13 counterpart, since a title is
    often catalogued under only one of the two forms. Every (source, ISBN
    form) combination — up to a dozen network calls — runs concurrently
    rather than one after another: sequentially, a book genuinely absent from
    every catalogue (common for locally-published Nigerian titles, which is
    exactly the case that now tries the most sources) could block the request
    for the sum of every source's timeout. Whichever combination is both a
    real hit and highest-priority (earliest source, then the original ISBN
    form before its alternate) wins."""
    isbn = normalise_isbn(raw_isbn)
    if not isbn:
        return None
    forms = [isbn]
    alt = _alternate_isbn(isbn)
    if alt:
        forms.append(alt)
    sources = _sources()
    combos = [(si, fi, fetch, form) for si, fetch in enumerate(sources) for fi, form in enumerate(forms)]

    from concurrent.futures import ThreadPoolExecutor, as_completed
    best_priority, best_result = None, None
    with ThreadPoolExecutor(max_workers=len(combos)) as ex:
        futures = {ex.submit(_safe_fetch, fetch, form): (si, fi) for si, fi, fetch, form in combos}
        for fut in as_completed(futures):
            priority = futures[fut]
            found = fut.result()
            if found and found.get('title') and (best_priority is None or priority < best_priority):
                best_priority, best_result = priority, found
    if best_result:
        best_result['isbn'] = isbn
        return best_result
    return None
