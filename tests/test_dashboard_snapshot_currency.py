"""Dashboard exam-snapshot cards (JAMB/WAEC/Latest Mock) carry an
``is_current`` flag: whether the shown year/sitting is the active session's
own, or just the most recent real results on file — which is normal and
expected right after a new session starts, before that session's own
WAEC/JAMB/mocks have happened or been entered. The frontend uses this to add
a "latest available" note instead of implying the numbers are fresh.

Uses the private helpers directly (routes.main._dash_*_snapshot) with
``get_active_session`` monkeypatched to a fake session, so this never touches
the shared test DB's real "active" AcademicSession row (the app fixture's DB
is session-scoped and shared across the whole suite). Each call runs inside
a super_admin test_request_context so the branch-scoping helpers those
functions call (session-backed) see "all branches" rather than filtering
everything out for lack of a logged-in session.
"""
import uuid
from datetime import date

from flask import session

import routes.main as m
from models import db, AcademicSession, Student, WAECResult, JAMBResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult


class _FakeSession:
    def __init__(self, name, id=-999):
        self.name = name
        self.id = id


def _central_call(app, fn):
    with app.test_request_context():
        session['role'] = 'super_admin'
        return fn()


def _seed_jamb_waec(app, year):
    with app.app_context():
        s = Student(student_id='SNP' + uuid.uuid4().hex[:7].upper(), first_name='A',
                    surname='Snap', gender='Male', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(JAMBResult(student_id=s.id, exam_year=year, total_score=220))
        db.session.add(WAECResult(student_id=s.id, exam_year=year, subject='Mathematics', grade='A1'))
        db.session.commit()


def test_jamb_and_waec_current_when_session_matches(app, monkeypatch):
    year = 2150  # between test_dashboard_context's 2099 and the 2264+ sentinel cluster
    _seed_jamb_waec(app, year)
    monkeypatch.setattr(m, 'get_active_session', lambda: _FakeSession(f'{year - 1}/{year}'))
    js = _central_call(app, m._dash_jamb_snapshot)
    ws = _central_call(app, m._dash_waec_snapshot)
    assert js['year'] == year and js['is_current'] is True
    assert ws['year'] == year and ws['is_current'] is True


def test_jamb_and_waec_not_current_when_session_is_ahead(app, monkeypatch):
    """The active session's own exam year hasn't happened/been entered yet —
    the snapshot still shows the last real results, flagged as not current."""
    year = 2151
    _seed_jamb_waec(app, year)
    monkeypatch.setattr(m, 'get_active_session', lambda: _FakeSession(f'{year}/{year + 1}'))
    js = _central_call(app, m._dash_jamb_snapshot)
    ws = _central_call(app, m._dash_waec_snapshot)
    assert js['year'] == year and js['is_current'] is False
    assert ws['year'] == year and ws['is_current'] is False


def test_jamb_current_when_no_active_session_to_compare(app, monkeypatch):
    """Can't tell either way (no active session) => don't flag it as stale."""
    year = 2152
    _seed_jamb_waec(app, year)
    monkeypatch.setattr(m, 'get_active_session', lambda: None)
    js = _central_call(app, m._dash_jamb_snapshot)
    assert js['is_current'] is True


def test_mock_snapshot_current_flag_matches_session_id(app, monkeypatch):
    with app.app_context():
        sess_a = AcademicSession(name='SnapMockA ' + uuid.uuid4().hex[:5])
        sess_b = AcademicSession(name='SnapMockB ' + uuid.uuid4().hex[:5])
        db.session.add_all([sess_a, sess_b]); db.session.flush()
        s = Student(student_id='SNP' + uuid.uuid4().hex[:7].upper(), first_name='B',
                    surname='Mock', gender='Female', is_active=True)
        db.session.add(s); db.session.flush()
        # A date far in the future so this is unambiguously the "latest" mock
        # exam globally (the shared test DB accumulates rows from other tests).
        ex = MockJAMBExam(name='SnapMock', exam_number=1, session_id=sess_a.id,
                          exam_date=date(2099, 12, 31))
        db.session.add(ex); db.session.flush()
        db.session.add(MockJAMBResult(student_id=s.id, mock_exam_id=ex.id, total_score=200))
        db.session.commit()
        sess_a_id, sess_b_id = sess_a.id, sess_b.id

    monkeypatch.setattr(m, 'get_active_session', lambda: _FakeSession('Active', id=sess_a_id))
    assert _central_call(app, m._dash_mock_snapshot)['is_current'] is True

    monkeypatch.setattr(m, 'get_active_session', lambda: _FakeSession('Active', id=sess_b_id))
    assert _central_call(app, m._dash_mock_snapshot)['is_current'] is False
