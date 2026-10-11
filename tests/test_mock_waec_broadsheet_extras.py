"""Mock WAEC broadsheet "what else should be on it" additions: AB (absent)
marking from the grid, the arm/position/subjects-sat/remark columns, and the
watermark/page-number/printed-on/exam-date toggles — all independently
selectable the same way the signature and Credits/Average toggles already are."""
import re
import uuid
from datetime import date

from config import Config
from models import db, Student, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, MockWAECAnalytics, waec_grade_from_score
from tests.conftest import login_token, auth_csrf, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _session(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='2025/2026', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _exam(app, session_id, n):
    with app.app_context():
        ex = MockWAECExam(name=f'Mock {n}', exam_number=n, session_id=session_id,
                          exam_date=date(2026, 2, 15))
        db.session.add(ex); db.session.commit()
        return ex.id


def _student(app, adm, first, surname):
    with app.app_context():
        s = Student(student_id=adm, first_name=first, surname=surname, gender='Male')
        db.session.add(s); db.session.commit()
        return s.id


def _seed_results(app, exam_id, sid, scores):
    with app.app_context():
        for subj, sc in scores.items():
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id,
                                          subject=subj, score=sc, grade=waec_grade_from_score(sc)))
        db.session.commit()


def _slug(subj):
    return re.sub(r'[^a-z0-9]+', '-', subj.lower()).strip('-')


def test_grid_marks_and_clears_absence(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=90)
    sid = _student(app, 'AB' + uuid.uuid4().hex[:5].upper(), 'Ada', 'Absent')
    enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)

    # Check AB for Mathematics -> a result row is created with is_absent=True
    # and no score, even though the score box itself was left blank.
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'absent_{sid}_{_slug("Mathematics")}': 'on',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row is not None and row.is_absent is True
        assert row.score is None and row.grade is None

    # Entering a real score afterwards (AB unchecked) clears the absence.
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'score_{sid}_{_slug("Mathematics")}': '72',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row.is_absent is False and row.score == 72 and row.grade == 'B2'


def test_grid_absence_wins_over_a_stray_score_value(app):
    """If both the AB box and a leftover score value are posted for the same
    cell, absence must win -- a student can't be both absent and scored."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=91)
    sid = _student(app, 'AW' + uuid.uuid4().hex[:5].upper(), 'Win', 'Absence')
    enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'absent_{sid}_{_slug("Mathematics")}': 'on',
        f'score_{sid}_{_slug("Mathematics")}': '55',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row.is_absent is True and row.score is None


def test_broadsheet_arm_position_subjects_sat_remark(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=92)
    top = _student(app, 'TP' + uuid.uuid4().hex[:5].upper(), 'Top', 'Scorer')
    low = _student(app, 'LW' + uuid.uuid4().hex[:5].upper(), 'Low', 'Scorer')
    enroll_sss3(app, top)
    enroll_sss3(app, low)
    _seed_results(app, exam_id, top, {'Mathematics': 90, 'English Language': 85,
                                      'Biology': 80, 'Chemistry': 75, 'Physics': 70})
    _seed_results(app, exam_id, low, {'Mathematics': 30, 'English Language': 35})

    with app.app_context():
        bs = MockWAECAnalytics.get_broadsheet(exam_id)
        by_id = {r['student'].id: r for r in bs['rows']}
        assert by_id[top]['position'] == 1
        assert by_id[low]['position'] == 2
        assert by_id[top]['subjects_sat'] == 5
        assert by_id[top]['remark'] == 'Qualifies'      # 5 credits incl. both core subjects
        assert by_id[low]['remark'] == 'Not Qualified'  # only 2 subjects, both failed
        # Arm is resolved (possibly '') without raising even with no SSS3/term
        # setup beyond what enroll_sss3 creates.
        assert 'arm' in by_id[top]

    c = _admin(app)
    # Everything new, combined in as few requests as possible (the export
    # route is rate-limited -- see the broadsheet rate-limit lesson in
    # test_mock_waec_broadsheet.py).
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?'
             'arm_col=1&position=1&subjects_sat=1&remark=1&exam_date=1')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
    r2 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?'
              'arm_col=0&position=0&subjects_sat=0&remark=0&watermark=0&'
              'page_numbers=0&printed_on=0&exam_date=0')
    assert r2.status_code == 200 and r2.get_data()[:5] == b'%PDF-'


def test_broadsheet_preview_exposes_new_toggles(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=93)
    prev = _admin(app).get(f'/mock-waec/exam/{exam_id}/broadsheet/print').get_data(as_text=True)
    for label in ('Exam date', 'Class arm column', 'Position column',
                  'Subjects sat column', 'Remark column', 'Watermark',
                  'Page numbers', 'Printed-on footer'):
        assert label in prev
    blank_prev = _admin(app).get(f'/mock-waec/exam/{exam_id}/broadsheet/blank').get_data(as_text=True)
    assert 'Class arm column' in blank_prev and 'Watermark' in blank_prev
    # Position/Subjects-sat/Remark are filled-in-sheet-only (no scores on a
    # blank recording sheet to rank or qualify on).
    assert 'Position column' not in blank_prev and 'Remark column' not in blank_prev


def test_blank_broadsheet_renders_with_arm_and_watermark_toggles(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=94)
    sid = _student(app, 'BK' + uuid.uuid4().hex[:5].upper(), 'Blank', 'Arm')
    enroll_sss3(app, sid)
    with app.app_context():
        db.session.get(Student, sid).waec_subjects = 'Mathematics,English Language'
        db.session.commit()
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?arm_col=1&watermark=1&page_numbers=1')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
    r2 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?arm_col=0&watermark=0')
    assert r2.status_code == 200 and r2.get_data()[:5] == b'%PDF-'


def test_broadsheet_shows_ab_for_absent_subject(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=95)
    sid = _student(app, 'MA' + uuid.uuid4().hex[:5].upper(), 'Marked', 'Absent')
    enroll_sss3(app, sid)
    with app.app_context():
        r = MockWAECResult(student_id=sid, mock_exam_id=exam_id, subject='Mathematics',
                           score=None, grade=None, is_absent=True)
        db.session.add(r); db.session.commit()
        bs = MockWAECAnalytics.get_broadsheet(exam_id)
        row = next(r for r in bs['rows'] if r['student'].id == sid)
        assert row['credits'] == 0 and row['average_score'] is None
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
