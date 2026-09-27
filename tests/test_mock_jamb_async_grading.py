"""Optional async (queued) grading for Mock JAMB submissions -- mirrors CBT's
proven CBT_ASYNC_GRADING pattern (routes/cbt.py, docs/CBT_SCALE.md) so a whole
cohort submitting at the timer deadline doesn't grade synchronously on the web
workers. Off by default (grades inline immediately, unchanged behaviour) --
these tests force it on via monkeypatch rather than requiring real Redis."""
import re

from models import db, MockJAMBAttempt, MockJAMBResult
from tests.test_mock_jamb_sitting import _build_exam, _portal_login


def _csrf(c, eid):
    html = c.get(f'/exam/mock-jamb/{eid}').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def test_portal_submit_queues_instead_of_grading_inline_when_enabled(app, monkeypatch):
    """submit() must mark the attempt 'Submitting' and hand off to the job
    queue rather than grading on the request -- the whole point of the
    feature is keeping a deadline-submit spike off the web workers."""
    import utils.mock_jamb_sitting as mjs
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)
    tok = _csrf(c, eid)

    monkeypatch.setattr(mjs, 'async_grading_enabled', lambda: True)
    enqueued = {}
    def _fake_enqueue(kind, payload=None, **k):
        enqueued['kind'] = kind
        enqueued['payload'] = payload
        return 'queued'
    monkeypatch.setattr('utils.jobqueue.enqueue', _fake_enqueue)

    r = c.post(f'/exam/mock-jamb/{eid}/submit', data={'_csrf_token': tok})
    assert r.status_code == 302

    assert enqueued.get('kind') == 'mockjamb_grade'
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        assert att.status == 'Submitting'
        assert enqueued['payload'] == {'attempt_id': att.id}
        assert att.submitted_at is not None
        # not graded yet -- no result row, no total_score
        assert att.total_score == 0
        assert MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=eid).first() is None


def test_portal_submit_grades_inline_by_default(app, monkeypatch):
    """The feature is opt-in: with async grading NOT enabled (the default),
    submit() must still grade immediately, unchanged from before."""
    import utils.mock_jamb_sitting as mjs
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)
    tok = _csrf(c, eid)
    monkeypatch.setattr(mjs, 'async_grading_enabled', lambda: False)

    r = c.post(f'/exam/mock-jamb/{eid}/submit', data={'_csrf_token': tok})
    assert r.status_code == 302
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        assert att.status == 'Submitted'


def test_portal_done_shows_grading_page_then_self_heals(app, monkeypatch):
    """While a queued grade is in flight (status 'Submitting'), the done page
    must show the grading interim state, not 500 or redirect away -- and must
    self-heal (grade inline) once the worker grace period has elapsed, so a
    student is never stuck behind a dead/overloaded worker."""
    import datetime as dt
    from utils import timeutil
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)
    c.get(f'/exam/mock-jamb/{eid}')   # creates the attempt

    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        att.status = 'Submitting'
        att.submitted_at = timeutil.now()   # fresh -- still within grace
        db.session.commit()

    html = c.get(f'/exam/mock-jamb/{eid}/done').get_data(as_text=True)
    assert 'Submitting your mock' in html

    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        att.submitted_at = timeutil.now() - dt.timedelta(seconds=90)   # past the 60s grace
        db.session.commit()

    r = c.get(f'/exam/mock-jamb/{eid}/done')
    assert r.status_code == 200
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        assert att.status == 'Submitted'   # self-healed


def test_mockjamb_grade_job_handler_finalises_the_attempt(app):
    """The registered utils.jobqueue handler ('mockjamb_grade') is what the
    dedicated jobs worker actually runs when a job is drained -- verify it
    grades the right attempt correctly, not just that something was enqueued."""
    from routes.mock_jamb import _mockjamb_grade_job
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)
    c.get(f'/exam/mock-jamb/{eid}')

    from utils import timeutil
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        att.status = 'Submitting'
        att.submitted_at = timeutil.now()
        db.session.commit()
        att_id = att.id

        _mockjamb_grade_job(app, {'attempt_id': att_id})

        graded = db.session.get(MockJAMBAttempt, att_id)
        assert graded.status == 'Submitted'
        assert MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=eid).first() is not None


def test_auto_submit_expired_queues_when_async_enabled(app, monkeypatch):
    """The admin-triggered safety net (auto_submit_expired, called on
    view_exam/items page loads) must also queue rather than grade synchronously
    when async grading is on -- otherwise a whole cohort's expired attempts
    would still grade inline on one admin's page load."""
    import datetime as dt
    import utils.mock_jamb_sitting as mjs
    eid, sid, eng_id, mth_id = _build_exam(app)
    c = _portal_login(app, sid)
    c.get(f'/exam/mock-jamb/{eid}')

    from utils import timeutil
    with app.app_context():
        att = MockJAMBAttempt.query.filter_by(mock_exam_id=eid, student_id=sid).first()
        att.started_at = timeutil.now() - dt.timedelta(hours=5)   # long past deadline
        db.session.commit()
        att_id, exam_id = att.id, eid

    monkeypatch.setattr(mjs, 'async_grading_enabled', lambda: True)
    enqueued = []
    monkeypatch.setattr('utils.jobqueue.enqueue',
                        lambda kind, payload=None, **k: enqueued.append((kind, payload)) or 'queued')

    with app.app_context():
        from models import MockJAMBExam
        exam = db.session.get(MockJAMBExam, exam_id)
        graded = mjs.auto_submit_expired(exam=exam)
        assert graded == 1
        assert enqueued == [('mockjamb_grade', {'attempt_id': att_id})]
        att2 = db.session.get(MockJAMBAttempt, att_id)
        assert att2.status == 'Submitting'   # queued, not graded inline
