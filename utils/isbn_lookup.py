"""Look up book metadata by ISBN from public catalogues.

Tries Open Library first, then Google Books. Uses the stdlib-based
``utils.http`` client (proxy/timeout-safe) so a mismatched ``requests`` can't
hang the request. Returns a normalised dict the book form can consume, or None
when nothing is found / the lookup fails. Never raises.
"""
from __future__ import annotations

import re

from utils.http import get_json

_YEAR = re.compile(r'(\d{4})')


def normalise_isbn(raw):
    """Strip separators; keep digits and a trailing X. Returns '' if implausible."""
    s = re.sub(r'[^0-9Xx]', '', (raw or '')).upper()
    return s if len(s) in (10, 13) else ''


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


def lookup_isbn(raw_isbn):
    """Normalised book metadata for an ISBN, or None. Best-effort across sources."""
    isbn = normalise_isbn(raw_isbn)
    if not isbn:
        return None
    for fetch in (_from_openlibrary, _from_google):
        try:
            found = fetch(isbn)
        except Exception:
            found = None
        if found and found.get('title'):
            found['isbn'] = isbn
            return found
    return None
