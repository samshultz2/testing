"""Mock WAEC exams run over several days: a first-paper and an optional
last-paper date, shown as a range."""
import datetime as dt
import uuid

from models import db, AcademicSession
from models.mock_waec import MockWAECExam
from tests.test_medical_access import _admin, _csrf


def _session(app):
    with app.app_context():
        s = AcademicSession(name=f'MWD-{uuid.uuid4().hex[:6]}'); db.session.add(s); db.session.commit()
        return s.id


def _create(c, ssid, num, start, end=''):
    return c.post('/mock-waec/exam/create', data={'session_id': ssid, 'exam_number': num, 'exam_date': start,
                                                  'end_date': end, '_csrf_token': _csrf(c)})


def test_create_with_a_date_range_and_edit_it(app):
    ssid = _session(app)
    c = _admin(app)
    assert 'Last paper' in c.get('/mock-waec/exam/create').get_data(as_text=True)
    _create(c, ssid, 1, '2026-03-02', '2026-03-13')
    with app.app_context():
        e = MockWAECExam.query.filter_by(session_id=ssid, exam_number=1).one()
        assert (e.exam_date, e.end_date) == (dt.date(2026, 3, 2), dt.date(2026, 3, 13))
        eid = e.id
    assert '2 – 13 March 2026' in c.get(f'/mock-waec/exam/{eid}').get_data(as_text=True)
    # A last paper before the first is refused; clearing it makes a one-day exam.
    c.post(f'/mock-waec/exam/{eid}/edit', data={'name': 'X', 'exam_date': '2026-03-02', 'end_date': '2026-02-20',
                                                '_csrf_token': _csrf(c)})
    with app.app_context():
        assert db.session.get(MockWAECExam, eid).end_date == dt.date(2026, 3, 13)
    c.post(f'/mock-waec/exam/{eid}/edit', data={'name': 'X', 'exam_date': '2026-03-02', 'end_date': '',
                                                '_csrf_token': _csrf(c)})
    with app.app_context():
        assert db.session.get(MockWAECExam, eid).end_date is None


def test_end_before_start_is_rejected_on_create(app):
    ssid = _session(app)
    c = _admin(app)
    _create(c, ssid, 2, '2026-03-10', '2026-03-01')
    with app.app_context():
        assert MockWAECExam.query.filter_by(session_id=ssid, exam_number=2).count() == 0


def test_date_label_formats():
    E = lambda a, b=None: MockWAECExam(exam_date=a, end_date=b)
    assert E(dt.date(2026, 3, 2)).date_label() == '2 Mar 2026'
    assert E(dt.date(2026, 3, 2), dt.date(2026, 3, 2)).date_label() == '2 Mar 2026'
    assert E(dt.date(2026, 2, 27), dt.date(2026, 3, 6)).date_label() == '27 Feb – 6 Mar 2026'
    assert E(dt.date(2025, 12, 29), dt.date(2026, 1, 9)).date_label(long=True) == '29 December 2025 – 9 January 2026'
