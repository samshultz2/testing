"""Contributions UX overhaul: the 3-bucket payment status (Not Started / In
Progress / Paid) distinguishes students who've never paid from those partway
there, and the payments list supports a from/to date range in addition to
the exact-date filter."""
import re
import uuid
from datetime import date

from config import Config
from models import db, Student, AcademicSession, ContributionSettings, ContributionPayment
from tests.conftest import login_token, enroll_sss3
from utils.services.contributions import payment_status

ACCESS_CODE = '64665842'


def _client(app):
    with app.app_context():
        ContributionSettings.set('access_code', ACCESS_CODE)
        ContributionSettings.set('max_due', 20000)
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    tok = _ptoken(c)
    c.post('/contributions/access', data={'access_code': ACCESS_CODE, '_csrf_token': tok})
    return c


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _sss3_student(app, tag):
    with app.app_context():
        s = Student(student_id='ST' + uuid.uuid4().hex[:6].upper(), first_name='Status',
                    surname=f'Zz{tag}', gender='Male', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    enroll_sss3(app, sid)
    return sid


def _pay(app, sid, amount, when='2026-02-01'):
    with app.app_context():
        sess = AcademicSession.query.filter_by(is_active=True).first()
        db.session.add(ContributionPayment(session_id=sess.id if sess else None, student_id=sid,
                                           amount=amount, payment_date=date.fromisoformat(when)))
        db.session.commit()


def test_payment_status_buckets():
    assert payment_status(0, 20000) == 'Not Started'
    assert payment_status(None, 20000) == 'Not Started'
    assert payment_status(5000, 20000) == 'In Progress'
    assert payment_status(20000, 20000) == 'Paid'
    assert payment_status(25000, 20000) == 'Paid'   # overpaid still reads as Paid


def test_dashboard_reports_not_started_and_in_progress_counts(app):
    not_started = _sss3_student(app, 'NS')
    in_progress = _sss3_student(app, 'IP')
    paid = _sss3_student(app, 'PD')
    _pay(app, in_progress, 5000)
    _pay(app, paid, 20000)
    c = _client(app)
    data = c.get('/contributions/', headers={'X-Requested-With': 'fetch'}).get_json()
    s = data['stats']
    assert s['not_started_count'] >= 1 and s['in_progress_count'] >= 1 and s['fully_paid_count'] >= 1
    # The three buckets must partition every student (no double counting, none dropped).
    assert s['not_started_count'] + s['in_progress_count'] + s['fully_paid_count'] == s['total_students']
    by_id = {st['id']: st['status'] for st in data['students']}
    assert by_id[not_started] == 'Not Started'
    assert by_id[in_progress] == 'In Progress'
    assert by_id[paid] == 'Paid'


def test_defaulters_distinguishes_never_started(app):
    not_started = _sss3_student(app, 'DNS')
    in_progress = _sss3_student(app, 'DIP')
    _pay(app, in_progress, 5000)
    c = _client(app)
    data = c.get('/contributions/defaulters', headers={'X-Requested-With': 'fetch'}).get_json()
    assert data['not_started_count'] >= 1
    by_id = {s['id']: s['status'] for s in data['defaulters']}
    assert by_id[not_started] == 'Not Started'
    assert by_id[in_progress] == 'In Progress'


def test_payments_list_date_range_filter(app):
    # The test DB is shared for the whole suite run, so scope every assertion
    # to this test's own student (by its distinctive surname tag) rather than
    # assuming the payments list is otherwise empty.
    sid = _sss3_student(app, 'DR')
    _pay(app, sid, 1000, '2026-01-05')
    _pay(app, sid, 2000, '2026-01-15')
    _pay(app, sid, 3000, '2026-01-25')
    c = _client(app)
    data = c.get('/contributions/payments?from=2026-01-10&to=2026-01-20',
                 headers={'X-Requested-With': 'fetch'}).get_json()
    mine = [p for p in data['payments'] if 'ZzDR' in p['student_name']]
    assert sorted(p['amount'] for p in mine) == [2000]

    # The out-of-range payments for this same student must not appear.
    all_data = c.get('/contributions/payments', headers={'X-Requested-With': 'fetch'}).get_json()
    mine_all = sorted(p['amount'] for p in all_data['payments'] if 'ZzDR' in p['student_name'])
    assert mine_all == [1000, 2000, 3000]
