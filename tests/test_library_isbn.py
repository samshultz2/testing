"""Library — add a book by ISBN/barcode with auto-fill + duplicate handling."""
from config import Config
from models import db, Book, Branch
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def test_normalise_isbn():
    from utils.isbn_lookup import normalise_isbn
    assert normalise_isbn('978-0-14-020652-3') == '9780140206523'
    assert normalise_isbn('0 306 40615 2') == '0306406152'
    assert normalise_isbn('12345') == ''          # implausible length


def test_isbn_lookup_autofills(app, monkeypatch):
    import utils.isbn_lookup as il
    monkeypatch.setattr(il, 'lookup_isbn', lambda isbn: {
        'title': 'Things Fall Apart', 'author': 'Chinua Achebe',
        'publisher': 'Heinemann', 'publication_year': 1958, 'subtitle': '',
        'subject': 'Fiction', 'keywords': 'Fiction', 'description': '', 'language': 'English',
        'source': 'Open Library', 'isbn': isbn})
    c = _admin(app)
    j = c.get('/library/api/isbn-lookup?isbn=9780385474542').get_json()
    assert j['found'] is True
    assert j['book']['title'] == 'Things Fall Apart'
    assert j['book']['author'] == 'Chinua Achebe'
    assert j['existing'] == []


def test_isbn_lookup_flags_existing_by_isbn(app, monkeypatch):
    import utils.isbn_lookup as il
    monkeypatch.setattr(il, 'lookup_isbn', lambda isbn: {
        'title': 'ZzDupTitle', 'author': 'A', 'publisher': '', 'publication_year': None,
        'subtitle': '', 'subject': '', 'keywords': '', 'description': '', 'language': '',
        'source': 'Google Books', 'isbn': isbn})
    with app.app_context():
        b = Book(branch_id=Branch.get_default().id, title='ZzDupTitle', author='A',
                 isbn='9781111111113', copies_total=3, copies_available=3, is_active=True)
        db.session.add(b); db.session.commit()
    c = _admin(app)
    j = c.get('/library/api/isbn-lookup?isbn=978-1-111-11111-3').get_json()
    labels = {e['title'] for e in j['existing']}
    assert 'ZzDupTitle' in labels
    assert j['existing'][0]['add_copies_url']


def test_isbn_lookup_rejects_bad_isbn(app):
    c = _admin(app)
    r = c.get('/library/api/isbn-lookup?isbn=99')
    assert r.status_code == 400


def test_add_copies_increments(app):
    c = _admin(app); tok = _csrf(c)
    with app.app_context():
        b = Book(branch_id=Branch.get_default().id, title='ZzAddCopies', copies_total=2,
                 copies_available=1, is_active=True)
        db.session.add(b); db.session.commit()
        bid = b.id
    c.post(f'/library/books/{bid}/add-copies', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': tok, 'count': 4})
    with app.app_context():
        b = db.session.get(Book, bid)
        assert b.copies_total == 6 and b.copies_available == 5
