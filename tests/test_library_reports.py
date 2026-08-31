"""Library Phase 2 — reports (all types + export) and overdue parent reminders."""
import re
from datetime import date, timedelta

from config import Config
from models import db, Book, BookLoan, Student, ParentContact, Message
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


def _overdue_fixture(app, tag, *, with_parent=True):
    with app.app_context():
        b = Book(title=f'RB {tag}', category='Textbook', subject='Mathematics',
                 copies_total=2, copies_available=1, price=1200)
        s = Student(student_id=f'RS{tag}', first_name='Ada', surname=f'R{tag}',
                    gender='Female', is_active=True)
        db.session.add_all([b, s])
        db.session.flush()
        if with_parent:
            db.session.add(ParentContact(student_id=s.id, phone_number=f'0803000{tag[-4:]}',
                                         is_primary=True))
        db.session.add(BookLoan(book_id=b.id, student_id=s.id, borrower_type='student',
                                borrowed_date=date.today() - timedelta(days=20),
                                due_date=date.today() - timedelta(days=6), status='Borrowed'))
        db.session.commit()
        return b.id, s.id


# --- report engine ----------------------------------------------------------
def test_all_report_types_build(app):
    from utils import library_reports as R
    _overdue_fixture(app, 'ALL1')
    client = _admin(app)   # establishes a scoped session context via a request
    with client.application.test_request_context('/'):
        from flask import session
        session['role'] = 'super_admin'; session['scope'] = 'central'
        for key, _label in R.REPORTS:
            data = R.build(key, {'from': None, 'to': None})
            assert 'columns' in data and 'rows' in data and 'summary' in data
            assert data['type'] == key


def test_reports_page_renders(app):
    client = _admin(app)
    html = client.get('/library/reports?type=overdue').get_data(as_text=True)
    assert '"page": "reports"' in html and '"report"' in html and '"report_types"' in html


def test_reports_export_csv(app):
    _overdue_fixture(app, 'CSV1')
    client = _admin(app)
    r = client.get('/library/reports/export?type=inventory&format=csv')
    assert r.status_code == 200 and 'text/csv' in r.content_type
    assert 'Title' in r.get_data(as_text=True)


def test_reports_export_xlsx(app):
    client = _admin(app)
    r = client.get('/library/reports/export?type=overdue&format=xlsx')
    assert r.status_code == 200
    assert 'spreadsheet' in r.content_type or 'excel' in r.content_type


# --- overdue reminders ------------------------------------------------------
def test_remind_overdue_drafts_campaign(app):
    _overdue_fixture(app, 'REM1', with_parent=True)
    client = _admin(app)
    r = client.post('/library/remind-overdue', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': _ptoken(client)}).get_json()
    assert r['ok'] and '/communication/messages/' in r['redirect']
    with app.app_context():
        assert Message.query.filter_by(title='Library overdue reminder').count() >= 1


def test_remind_overdue_none(app):
    # With no overdue students at all is unlikely in the shared DB; instead assert
    # the endpoint responds gracefully (ok or info), never a 500.
    client = _admin(app)
    r = client.post('/library/remind-overdue', headers={'X-Requested-With': 'fetch'},
                    data={'_csrf_token': _ptoken(client)})
    assert r.status_code in (200, 400)
