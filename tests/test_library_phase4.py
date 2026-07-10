"""Library Phase 4 — bulk CSV import, reservations (queue → ready → fulfil),
class reading lists."""
import io
from datetime import date, timedelta

from config import Config
from models import (db, Book, BookLoan, BookReservation, ReadingListItem,
                    Student, SchoolClass)
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _csrf(client):
    with client.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


# --- bulk import ------------------------------------------------------------
def test_import_books_from_csv(app):
    client = _admin(app)
    token = _csrf(client)
    csv_text = (
        'Title,Author,ISBN,Category,Copies,Price,Source\n'
        'Things Fall Apart P4,Chinua Achebe,9780001,Novel,3,1500,Purchase\n'
        'Half of a Yellow Sun P4,Adichie,9780002,Novel,2,,Donation\n'
        ',No Title Row,,,,,\n'   # skipped — no title
    )
    data = {'_csrf_token': token,
            'file': (io.BytesIO(csv_text.encode('utf-8')), 'books.csv')}
    r = client.post('/library/import', data=data,
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    with app.app_context():
        b = Book.query.filter_by(title='Things Fall Apart P4').first()
        assert b is not None and b.copies_total == 3 and b.copies_available == 3
        assert b.source == 'Purchase'
        b2 = Book.query.filter_by(title='Half of a Yellow Sun P4').first()
        assert b2 is not None and b2.copies_total == 2 and b2.source == 'Donation'


def test_import_requires_title_column(app):
    client = _admin(app)
    token = _csrf(client)
    data = {'_csrf_token': token,
            'file': (io.BytesIO(b'Author,ISBN\nSomeone,123\n'), 'bad.csv')}
    r = client.post('/library/import', data=data,
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 400
    assert r.get_json()['ok'] is False


# --- reservations -----------------------------------------------------------
def _book_and_student(app, tag, *, available):
    with app.app_context():
        b = Book(title=f'RES {tag}', copies_total=1,
                 copies_available=(1 if available else 0))
        st = Student(student_id=f'RS{tag}', first_name='Res', surname=f'Zzres{tag}',
                     gender='Male', is_active=True)
        db.session.add_all([b, st])
        db.session.commit()
        return b.id, st.id


def test_reserve_available_book_marks_ready(app):
    bid, sid = _book_and_student(app, 'RDY', available=True)
    client = _admin(app)
    token = _csrf(client)
    r = client.post('/library/reserve',
                    data={'_csrf_token': token, 'book_id': bid,
                          'borrower_type': 'student', 'student_id': sid},
                    headers={'X-Requested-With': 'fetch'})
    assert r.get_json()['ok'] is True
    with app.app_context():
        res = BookReservation.query.filter_by(book_id=bid).first()
        assert res is not None and res.status == 'Ready'
        assert res.expires_on is not None


def test_reserve_unavailable_queues(app):
    bid, sid = _book_and_student(app, 'QUE', available=False)
    client = _admin(app)
    token = _csrf(client)
    r = client.post('/library/reserve',
                    data={'_csrf_token': token, 'book_id': bid,
                          'borrower_type': 'student', 'student_id': sid},
                    headers={'X-Requested-With': 'fetch'})
    assert r.get_json()['ok'] is True
    with app.app_context():
        res = BookReservation.query.filter_by(book_id=bid).first()
        assert res.status == 'Queued'


def test_returned_copy_promotes_next_queued(app):
    """A queued hold becomes Ready when a borrowed copy is returned."""
    with app.app_context():
        b = Book(title='PROMOTE P4', copies_total=1, copies_available=0)
        borrower = Student(student_id='RPB1', first_name='Cur', surname='Zzcur1',
                           gender='Male', is_active=True)
        waiting = Student(student_id='RPW1', first_name='Wait', surname='Zzwait1',
                          gender='Female', is_active=True)
        db.session.add_all([b, borrower, waiting])
        db.session.flush()
        loan = BookLoan(book_id=b.id, student_id=borrower.id, borrower_type='student',
                        borrowed_date=date.today() - timedelta(days=2),
                        due_date=date.today() + timedelta(days=5), status='Borrowed')
        res = BookReservation(book_id=b.id, student_id=waiting.id,
                              borrower_type='student', status='Queued')
        db.session.add_all([loan, res])
        db.session.commit()
        loan_id, res_id = loan.id, res.id

    client = _admin(app)
    token = _csrf(client)
    client.post(f'/library/loans/{loan_id}/return',
                data={'_csrf_token': token},
                headers={'X-Requested-With': 'fetch'})
    with app.app_context():
        assert db.session.get(BookReservation, res_id).status == 'Ready'


def test_reservation_fulfill_issues_loan(app):
    bid, sid = _book_and_student(app, 'FUL', available=True)
    with app.app_context():
        res = BookReservation(book_id=bid, student_id=sid, borrower_type='student',
                              status='Ready', expires_on=date.today() + timedelta(days=3))
        db.session.add(res)
        db.session.commit()
        res_id = res.id
    client = _admin(app)
    token = _csrf(client)
    r = client.post(f'/library/reservations/{res_id}/fulfill',
                    data={'_csrf_token': token},
                    headers={'X-Requested-With': 'fetch'})
    assert r.get_json()['ok'] is True
    with app.app_context():
        assert db.session.get(BookReservation, res_id).status == 'Fulfilled'
        assert BookLoan.query.filter_by(book_id=bid, student_id=sid, status='Borrowed').count() == 1
        assert db.session.get(Book, bid).copies_available == 0


def test_reservations_list_renders(app):
    bid, sid = _book_and_student(app, 'LST', available=False)
    with app.app_context():
        db.session.add(BookReservation(book_id=bid, student_id=sid,
                                       borrower_type='student', status='Queued'))
        db.session.commit()
    client = _admin(app)
    html = client.get('/library/reservations').get_data(as_text=True)
    assert '"page": "reservations"' in html and '"reservations"' in html
    assert 'RES LST' in html


# --- reading lists ----------------------------------------------------------
def test_reading_list_add_and_remove(app):
    with app.app_context():
        b = Book(title='Reader P4', copies_total=1, copies_available=1)
        cls = SchoolClass.query.filter_by(name='JSS1').first() or SchoolClass(name='JSS1', level=1)
        db.session.add_all([b, cls])
        db.session.commit()
        bid, cid = b.id, cls.id

    client = _admin(app)
    token = _csrf(client)
    r = client.post('/library/reading-lists/add',
                    data={'_csrf_token': token, 'class_id': cid, 'book_id': bid,
                          'note': 'Core text'},
                    headers={'X-Requested-With': 'fetch'})
    assert r.get_json()['ok'] is True
    with app.app_context():
        it = ReadingListItem.query.filter_by(class_id=cid, book_id=bid).first()
        assert it is not None and it.note == 'Core text'
        item_id = it.id

    # duplicate is rejected
    dup = client.post('/library/reading-lists/add',
                      data={'_csrf_token': token, 'class_id': cid, 'book_id': bid},
                      headers={'X-Requested-With': 'fetch'})
    assert dup.status_code == 400

    rm = client.post(f'/library/reading-lists/{item_id}/remove',
                     data={'_csrf_token': token},
                     headers={'X-Requested-With': 'fetch'})
    assert rm.get_json()['ok'] is True
    with app.app_context():
        assert db.session.get(ReadingListItem, item_id) is None


def test_reading_lists_page_renders(app):
    client = _admin(app)
    html = client.get('/library/reading-lists').get_data(as_text=True)
    assert '"page": "reading_lists"' in html and '"classes"' in html
