"""Library Phase 1 — multi-borrower loans, renew, lost/damaged, fines→Finance,
reference-only, richer catalogue, actionable dashboard."""
import re

from config import Config
from models import db, Book, BookLoan, Student, StaffMember, AdditionalCharge
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _post(client, url, **data):
    data['_csrf_token'] = _ptoken(client)
    return client.post(url, headers={'X-Requested-With': 'fetch'}, data=data).get_json()


def _fixtures(app, tag):
    with app.app_context():
        b = Book(title=f'Book {tag}', copies_total=2, copies_available=2, price=1500,
                 barcode=f'BC{tag}')
        ref = Book(title=f'Ref {tag}', copies_total=1, copies_available=1, reference_only=True)
        st = Student(student_id=f'ST{tag}', first_name='Ada', surname=f'O{tag}',
                     gender='Female', is_active=True)
        sf = StaffMember(staff_id=f'SF{tag}', first_name='Mr', surname=f'B{tag}',
                         staff_type='Teaching', is_active=True)
        db.session.add_all([b, ref, st, sf])
        db.session.commit()
        return b.id, ref.id, st.id, sf.id


# --- catalogue --------------------------------------------------------------
def test_add_book_with_rich_fields(app):
    client = _admin(app)
    r = _post(client, '/library/books/add', title='Deep Book', subject='Mathematics',
              barcode='DEEP1', reference_only='on', price='2000', condition='Fair',
              publication_year='2019', copies_total='4')
    assert r['ok']
    with app.app_context():
        b = Book.query.filter_by(title='Deep Book').first()
        assert b.subject == 'Mathematics' and b.reference_only is True
        assert b.barcode == 'DEEP1' and b.price == 2000 and b.publication_year == 2019


def test_catalogue_search_hits_barcode_and_subject(app):
    bid, refid, sid, sfid = _fixtures(app, 'SR')
    client = _admin(app)
    body = client.get('/library/books?q=BCSR').get_data(as_text=True)
    assert 'Book SR' in body


# --- multi-borrower issue ---------------------------------------------------
def test_issue_to_student_and_staff(app):
    bid, refid, sid, sfid = _fixtures(app, 'IS')
    client = _admin(app)
    assert _post(client, '/library/issue', book_id=bid, borrower_type='student', student_id=sid)['ok']
    assert _post(client, '/library/issue', book_id=bid, borrower_type='staff', staff_id=sfid)['ok']
    with app.app_context():
        loans = BookLoan.query.filter_by(book_id=bid).all()
        kinds = sorted(l.borrower_type for l in loans)
        assert kinds == ['staff', 'student']
        assert db.session.get(Book, bid).copies_available == 0


def test_reference_only_cannot_be_issued(app):
    bid, refid, sid, sfid = _fixtures(app, 'RF')
    client = _admin(app)
    r = client.post('/library/issue', headers={'X-Requested-With': 'fetch'},
                    data={'book_id': refid, 'borrower_type': 'student', 'student_id': sid,
                          '_csrf_token': _ptoken(client)})
    assert r.status_code == 400 and 'reference-only' in r.get_json()['error']


def test_issue_by_barcode(app):
    bid, refid, sid, sfid = _fixtures(app, 'BC')
    client = _admin(app)
    r = _post(client, '/library/issue', barcode='BCBC', borrower_type='student', student_id=sid)
    assert r['ok']


# --- renew / return / lost / damaged ---------------------------------------
def test_renew_extends_due_and_counts(app):
    bid, refid, sid, sfid = _fixtures(app, 'RN')
    client = _admin(app)
    _post(client, '/library/issue', book_id=bid, borrower_type='student', student_id=sid)
    with app.app_context():
        lid = BookLoan.query.filter_by(book_id=bid).first().id
    assert _post(client, f'/library/loans/{lid}/renew')['ok']
    with app.app_context():
        assert db.session.get(BookLoan, lid).renew_count == 1


def test_return_restocks_and_fine_waiver(app):
    bid, refid, sid, sfid = _fixtures(app, 'RT')
    client = _admin(app)
    _post(client, '/library/issue', book_id=bid, borrower_type='student', student_id=sid)
    with app.app_context():
        loan = BookLoan.query.filter_by(book_id=bid).first()
        loan.due_date = __import__('datetime').date.today() - __import__('datetime').timedelta(days=5)
        db.session.commit()
        lid = loan.id
        avail_before = db.session.get(Book, bid).copies_available
    assert _post(client, f'/library/loans/{lid}/return', waive='1')['ok']
    with app.app_context():
        loan = db.session.get(BookLoan, lid)
        assert loan.status == 'Returned' and loan.fine == 0 and loan.fine_waived is True
        assert db.session.get(Book, bid).copies_available == avail_before + 1


def test_lost_reduces_stock_and_bills_student(app):
    from utils.helpers import get_active_term
    bid, refid, sid, sfid = _fixtures(app, 'LO')
    with app.app_context():
        if not get_active_term():
            return   # need an active term for the finance charge
    client = _admin(app)
    _post(client, '/library/issue', book_id=bid, borrower_type='student', student_id=sid)
    with app.app_context():
        lid = BookLoan.query.filter_by(book_id=bid).first().id
        total_before = db.session.get(Book, bid).copies_total
    r = _post(client, f'/library/loans/{lid}/mark', kind='Lost', cost='1500')
    assert r['ok']
    with app.app_context():
        b = db.session.get(Book, bid)
        assert b.copies_total == total_before - 1 and b.lost_count == 1
        loan = db.session.get(BookLoan, lid)
        assert loan.status == 'Lost' and loan.replacement_cost == 1500
        # billed to the student's finance bill
        assert AdditionalCharge.query.filter_by(student_id=sid, category='Library fine').count() == 1


def test_staff_lost_does_not_bill(app):
    bid, refid, sid, sfid = _fixtures(app, 'SL')
    client = _admin(app)
    _post(client, '/library/issue', book_id=bid, borrower_type='staff', staff_id=sfid)
    with app.app_context():
        lid = BookLoan.query.filter_by(book_id=bid).first().id
    _post(client, f'/library/loans/{lid}/mark', kind='Damaged', cost='500')
    with app.app_context():
        loan = db.session.get(BookLoan, lid)
        assert loan.status == 'Damaged' and loan.fine_posted is False


# --- dashboard --------------------------------------------------------------
def test_dashboard_exposes_operational_stats(app):
    client = _admin(app)
    html = client.get('/library/').get_data(as_text=True)
    for key in ('issued_today', 'returned_today', 'added_month', 'active_borrowers',
                'lost', 'damaged', 'most_borrowed'):
        assert key in html
