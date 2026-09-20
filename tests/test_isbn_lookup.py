"""ISBN utilities — 10↔13 conversion and multi-source lookup fallback."""
from utils import isbn_lookup as il


def test_isbn13_to_10():
    assert il._isbn13_to_10('9780306406157') == '0306406152'
    assert il._isbn13_to_10('9791234567896') == ''        # 979 has no ISBN-10


def test_isbn10_to_13():
    assert il._isbn10_to_13('0306406152') == '9780306406157'


def test_alternate_form_roundtrip():
    assert il._alternate_isbn('9780306406157') == '0306406152'
    assert il._alternate_isbn('0306406152') == '9780306406157'
    # a valid Nigerian ISBN-13 still yields its ISBN-10 counterpart to try
    assert il._alternate_isbn('9789781535239') == '9781535237'


def _mute_all_sources(monkeypatch, **overrides):
    """Stub every source _sources() tries to a no-hit, except the ones named
    in ``overrides`` (source function name -> replacement callable)."""
    for name in ('_from_openlibrary', '_from_google', '_from_openlibrary_search',
                '_from_archive_org', '_from_crossref', '_from_isbndb'):
        monkeypatch.setattr(il, name, overrides.get(name, lambda isbn: None))


def test_lookup_tries_alternate_form(monkeypatch):
    """A book catalogued only under its ISBN-10 is still found when the ISBN-13
    is entered (and vice versa)."""
    isbn13 = '9789781535239'
    isbn10 = il._alternate_isbn(isbn13)
    seen = []

    def fake_openlibrary(isbn):
        seen.append(isbn)
        if isbn == isbn10:                       # only the alternate form has it
            return {'title': 'Nigerian Textbook', 'author': 'Local Author',
                    'source': 'Open Library'}
        return None

    _mute_all_sources(monkeypatch, _from_openlibrary=fake_openlibrary)
    res = il.lookup_isbn(isbn13)
    assert res and res['title'] == 'Nigerian Textbook'
    assert res['isbn'] == isbn13                 # original form preserved
    assert isbn10 in seen                        # the alternate form was tried


def test_lookup_falls_through_to_a_later_source(monkeypatch):
    """The first several sources missing the title doesn't stop the lookup —
    it keeps trying every remaining source before giving up."""
    _mute_all_sources(monkeypatch, _from_crossref=lambda isbn: {
        'title': 'Found By Crossref', 'author': '', 'source': 'Crossref'})
    res = il.lookup_isbn('9789781535239')
    assert res and res['title'] == 'Found By Crossref'


def test_lookup_prefers_earlier_source_when_several_hit(monkeypatch):
    """All sources run concurrently now (for latency, not correctness), so when
    more than one has the book the earlier-priority source's data still wins —
    not whichever happened to respond first."""
    _mute_all_sources(
        monkeypatch,
        _from_google=lambda isbn: {'title': 'From Google', 'source': 'Google Books'},
        _from_crossref=lambda isbn: {'title': 'From Crossref', 'source': 'Crossref'},
    )
    # _from_openlibrary precedes _from_google precedes _from_crossref in _sources()
    res = il.lookup_isbn('9789781535239')
    assert res['title'] == 'From Google'


def test_lookup_none_when_nowhere(monkeypatch):
    _mute_all_sources(monkeypatch)
    assert il.lookup_isbn('9789781535239') is None


def test_from_openlibrary_search_parses_docs(monkeypatch):
    monkeypatch.setattr(il, 'get_json', lambda url, **kw: _Res({'docs': [{
        'title': 'African Literature Today', 'author_name': ['Chinua Achebe'],
        'publisher': ['Heinemann', 'Africana'], 'first_publish_year': 1975,
        'subject': ['Fiction', 'African literature'], 'language': ['eng'],
    }]}))
    r = il._from_openlibrary_search('9780435905254')
    assert r['title'] == 'African Literature Today'
    assert r['author'] == 'Chinua Achebe'
    assert r['publisher'] == 'Heinemann, Africana'
    assert r['publication_year'] == 1975
    assert r['subject'] == 'Fiction'
    assert r['source'] == 'Open Library (search index)'


def test_from_openlibrary_search_no_docs(monkeypatch):
    monkeypatch.setattr(il, 'get_json', lambda url, **kw: _Res({'docs': []}))
    assert il._from_openlibrary_search('9780435905254') is None


def test_from_archive_org_parses_docs(monkeypatch):
    monkeypatch.setattr(il, 'get_json', lambda url, **kw: _Res({'response': {'docs': [{
        'title': 'Things Fall Apart', 'creator': ['Chinua Achebe'],
        'publisher': ['Heinemann'], 'date': '1958-01-01T00:00:00Z',
        'subject': ['Fiction', 'Nigeria'], 'language': ['eng'],
    }]}}))
    r = il._from_archive_org('9780385474542')
    assert r['title'] == 'Things Fall Apart'
    assert r['author'] == 'Chinua Achebe'
    assert r['publisher'] == 'Heinemann'
    assert r['publication_year'] == 1958
    assert r['source'] == 'Internet Archive'


def test_from_archive_org_no_docs(monkeypatch):
    monkeypatch.setattr(il, 'get_json', lambda url, **kw: _Res({'response': {'docs': []}}))
    assert il._from_archive_org('9780385474542') is None


def test_from_crossref_parses_items(monkeypatch):
    monkeypatch.setattr(il, 'get_json', lambda url, **kw: _Res({'message': {'items': [{
        'title': ['Principles of Economics'],
        'author': [{'given': 'N.', 'family': 'Mankiw'}],
        'publisher': 'Cengage', 'published-print': {'date-parts': [[2020, 1, 1]]},
        'subject': ['Economics'],
    }]}}))
    r = il._from_crossref('9781305585126')
    assert r['title'] == 'Principles of Economics'
    assert r['author'] == 'N. Mankiw'
    assert r['publication_year'] == 2020
    assert r['source'] == 'Crossref'


def test_from_crossref_no_items(monkeypatch):
    monkeypatch.setattr(il, 'get_json', lambda url, **kw: _Res({'message': {'items': []}}))
    assert il._from_crossref('9781305585126') is None


def test_from_isbndb_skipped_without_key(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, 'ISBNDB_API_KEY', '')
    called = []
    monkeypatch.setattr(il, 'get_json', lambda *a, **k: called.append(1) or _Res({}))
    assert il._from_isbndb('9780385474542') is None
    assert not called                            # no request made without a key


def test_from_isbndb_parses_book_when_key_configured(monkeypatch):
    from config import Config
    monkeypatch.setattr(Config, 'ISBNDB_API_KEY', 'test-key-123')
    seen_headers = {}

    def fake_get_json(url, headers=None, **kw):
        seen_headers.update(headers or {})
        return _Res({'book': {
            'title': 'Fundamentals of Physics', 'title_long': 'Fundamentals of Physics: Extended',
            'authors': ['David Halliday', 'Robert Resnick'], 'publisher': 'Wiley',
            'date_published': '2013-05-01', 'subjects': ['Physics', 'Science'],
            'synopsis': 'A comprehensive physics textbook.',
        }})
    monkeypatch.setattr(il, 'get_json', fake_get_json)
    r = il._from_isbndb('9781118230718')
    assert r['title'] == 'Fundamentals of Physics'
    assert r['subtitle'] == 'Extended'
    assert r['author'] == 'David Halliday, Robert Resnick'
    assert r['publication_year'] == 2013
    assert r['source'] == 'ISBNdb'
    assert seen_headers.get('Authorization') == 'test-key-123'


class _Res:
    """Minimal HttpResult stand-in for mocking ``get_json`` in these tests."""
    def __init__(self, body, ok=True):
        self._body = body
        self.ok = ok

    def json(self):
        return self._body
