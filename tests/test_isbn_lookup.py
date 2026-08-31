"""ISBN utilities — 10↔13 conversion and dual-form lookup fallback."""
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

    monkeypatch.setattr(il, '_from_openlibrary', fake_openlibrary)
    monkeypatch.setattr(il, '_from_google', lambda isbn: None)
    res = il.lookup_isbn(isbn13)
    assert res and res['title'] == 'Nigerian Textbook'
    assert res['isbn'] == isbn13                 # original form preserved
    assert isbn10 in seen                        # the alternate form was tried


def test_lookup_none_when_nowhere(monkeypatch):
    monkeypatch.setattr(il, '_from_openlibrary', lambda isbn: None)
    monkeypatch.setattr(il, '_from_google', lambda isbn: None)
    assert il.lookup_isbn('9789781535239') is None
