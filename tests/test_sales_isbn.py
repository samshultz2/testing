"""Sales — add a bookshop product by ISBN/barcode with duplicate stock top-up."""
from config import Config
from models import db, Branch, Product
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_product_isbn_lookup_maps_meta(app, monkeypatch):
    import utils.isbn_lookup as il
    monkeypatch.setattr(il, 'lookup_isbn', lambda isbn: {
        'title': 'New Concept English', 'author': 'L.G. Alexander',
        'publisher': 'Longman', 'publication_year': 1997, 'source': 'Open Library',
        'isbn': isbn})
    c = _admin(app)
    j = c.get('/sales/api/isbn-lookup?isbn=9780175560807').get_json()
    assert j['found'] is True
    p = j['product']
    assert p['name'] == 'New Concept English'
    assert p['barcode'] == '9780175560807'
    assert p['category'] == 'Textbooks'
    assert 'Longman' in p['description'] and 'L.G. Alexander' in p['description']


def test_product_isbn_lookup_flags_existing(app, monkeypatch):
    import utils.isbn_lookup as il
    monkeypatch.setattr(il, 'lookup_isbn', lambda isbn: {
        'title': 'ZzShopBook', 'author': 'A', 'publisher': 'P', 'publication_year': None,
        'source': 'Google Books', 'isbn': isbn})
    with app.app_context():
        p = Product(branch_id=Branch.get_default().id, name='ZzShopBook', category='Textbooks',
                    barcode='9782222222225', unit_price=500, stock_qty=3, is_active=True)
        db.session.add(p); db.session.commit()
    c = _admin(app)
    j = c.get('/sales/api/isbn-lookup?isbn=978-2-222-22222-5').get_json()
    assert j['existing'] and j['existing'][0]['name'] == 'ZzShopBook'
    assert j['existing'][0]['restock_url']


def test_product_isbn_lookup_bad_isbn(app):
    c = _admin(app)
    assert c.get('/sales/api/isbn-lookup?isbn=1').status_code == 400
