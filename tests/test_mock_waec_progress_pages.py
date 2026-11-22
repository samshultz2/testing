"""The redesigned Mock WAEC student progress page (subject × mock grid, focus
list, sittings in date order) and the trends page's student climbers."""
import uuid
from datetime import date

from models import db
from models.mock_waec import MockWAECExam, MockWAECResult
from tests.conftest import enroll_sss3
from tests.test_mock_waec_broadsheet_extras import _admin, _session, _student


def _mk(app, sess, n, day):
    with app.app_context():
        ex = MockWAECExam(name=f'Mock {n}', exam_number=n, session_id=sess, exam_date=day)
        db.session.add(ex); db.session.commit()
        return ex.id


def _res(app, ex, sid, rows):
    with app.app_context():
        for subj, score, grade, absent in rows:
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=ex, subject=subj,
                                          score=score, grade=grade, is_absent=absent))
        db.session.commit()


def test_student_progress_grid_focus_and_order(app):
    sess = _session(app)
    n = 700 + int(uuid.uuid4().int % 200)
    later = _mk(app, sess, n, date(2026, 6, 1))           # lower id, later date
    earlier = _mk(app, sess, n + 1, date(2026, 1, 10))
    sid = _student(app, 'PG' + uuid.uuid4().hex[:5].upper(), 'Grace', 'Progress')
    enroll_sss3(app, sid)
    _res(app, earlier, sid, [('English Language', 55, 'C6', False), ('Mathematics', 40, 'E8', False),
                             ('Physics', 60, 'C5', False)])
    _res(app, later, sid, [('English Language', 70, 'B2', False), ('Mathematics', 47, 'D7', False),
                           ('Physics', None, None, True)])
    html = _admin(app).get(f'/mock-waec/student/{sid}').get_data(as_text=True)
    assert 'Subjects across mocks' in html and 'Focus before WAEC' in html
    assert 'ABS' in html and '+15' in html                 # English 55 → 70
    assert 'Mathematics · 47' in html                      # borderline 45–49
    # Sittings run in date order, not exam number or id order.
    assert html.index(f'href="/mock-waec/exam/{earlier}"') < html.index(f'href="/mock-waec/exam/{later}"')
    assert f'/mock-waec/exam/{later}/student/{sid}/slip' in html


def test_student_progress_empty_state(app):
    sid = _student(app, 'PE' + uuid.uuid4().hex[:5].upper(), 'Nobody', 'Yet')
    enroll_sss3(app, sid)
    html = _admin(app).get(f'/mock-waec/student/{sid}').get_data(as_text=True)
    assert 'No Mock WAEC results yet' in html


def test_trends_lists_class_arms_and_student_moves(app):
    # Seed its own two mocks so the page has trends to show, whatever other
    # tests ran first (it used to rely on their leftover data).
    sess = _session(app)
    n = 900 + int(uuid.uuid4().int % 90)
    first = _mk(app, sess, n, date(2019, 1, 10))          # earliest in the window
    second = _mk(app, sess, n + 1, date(2029, 12, 1))     # latest in the window
    sid = _student(app, 'PT' + uuid.uuid4().hex[:5].upper(), 'Climb', 'Trend')
    enroll_sss3(app, sid)
    _res(app, first, sid, [('English Language', 40, 'E8', False), ('Mathematics', 38, 'F9', False)])
    _res(app, second, sid, [('English Language', 72, 'B2', False), ('Mathematics', 66, 'B3', False)])
    # Its own session, so other tests' mocks (some undated) can't change which
    # sittings count as first and latest.
    html = _admin(app).get(f'/mock-waec/trends?session_id={sess}').get_data(as_text=True)
    assert 'Not enough mocks yet' not in html
    assert 'Class arms' in html and 'Progress trends' in html
    assert 'Students climbing' in html and 'Climb' in html
