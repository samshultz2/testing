"""Mock WAEC broadsheet: the score+grade matrix, its per-subject summary block,
the printable page, the wide Excel export, and fast grid entry."""
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
                          exam_date=date(2025, 2, 1))
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


def test_broadsheet_analytics_shape(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=11)
    a = _student(app, 'BS' + uuid.uuid4().hex[:5].upper(), 'Ada', 'Aaa')
    b = _student(app, 'BS' + uuid.uuid4().hex[:5].upper(), 'Ben', 'Bbb')
    _seed_results(app, exam_id, a, {'Mathematics': 80, 'English Language': 70, 'Biology': 30})
    _seed_results(app, exam_id, b, {'Mathematics': 40, 'English Language': 55})

    with app.app_context():
        bs = MockWAECAnalytics.get_broadsheet(exam_id)
        # Core subjects lead the column order.
        assert bs['subjects'][:2] == ['English Language', 'Mathematics']
        assert [r['student'].first_name for r in bs['rows']] == ['Ada', 'Ben']   # surname order

        maths = bs['subject_summary']['Mathematics']
        assert maths['offered'] == 2 and maths['passed'] == 1 and maths['failed'] == 1
        assert maths['avg_score'] == 60.0 and maths['avg_grade'] == 'C4'   # (80+40)/2

        bio = bs['subject_summary']['Biology']
        assert bio['offered'] == 1 and bio['passed'] == 0 and bio['failed'] == 1

        # Whole-exam grade spread counts every entry.
        assert sum(bs['grade_distribution'].values()) == 5
        assert bs['school']['students'] == 2


def test_broadsheet_page_and_export(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=12)
    sid = _student(app, 'BS' + uuid.uuid4().hex[:5].upper(), 'Chika', 'Ccc')
    _seed_results(app, exam_id, sid, {'Mathematics': 72, 'English Language': 64})
    c = _admin(app)

    html = c.get(f'/mock-waec/exam/{exam_id}/broadsheet').get_data(as_text=True)
    assert 'Chika' in html and 'No. who offered' in html and 'Average grade' in html

    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/export')
    assert r.status_code == 200 and 'spreadsheet' in r.headers.get('Content-Type', '')


def test_grid_entry_saves_with_derived_grades(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=13)
    sid = _student(app, 'GR' + uuid.uuid4().hex[:5].upper(), 'Dele', 'Ddd')
    enroll_sss3(app, sid)
    c = _admin(app)

    # The grid page renders an input for this student.
    assert c.get(f'/mock-waec/exam/{exam_id}/grid').status_code == 200

    tok = auth_csrf(c)
    r = c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save',
        'col': ['Mathematics', 'English Language'],
        f'score_{sid}_mathematics': '75',
        f'score_{sid}_english-language': '48',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rows = {x.subject: x for x in MockWAECResult.query.filter_by(
            mock_exam_id=exam_id, student_id=sid).all()}
        assert rows['Mathematics'].score == 75 and rows['Mathematics'].grade == 'A1'
        assert rows['English Language'].score == 48 and rows['English Language'].grade == 'D7'


def test_grid_lists_only_enrolled_sss3(app):
    """Only SSS3 students sit Mock WAEC: a student not enrolled in SSS3 must not
    appear on the entry grid (no silent fall-back to the whole school)."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=16)
    enrolled = _student(app, 'OK' + uuid.uuid4().hex[:5].upper(), 'Hadi', 'Hhh')
    enroll_sss3(app, enrolled)
    outsider = _student(app, 'NO' + uuid.uuid4().hex[:5].upper(), 'Zara', 'Zzz')
    c = _admin(app)
    html = c.get(f'/mock-waec/exam/{exam_id}/grid').get_data(as_text=True)
    assert f'score_{enrolled}_' in html
    assert f'score_{outsider}_' not in html


def test_analytics_page_and_method(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=15)
    a = _student(app, 'AN' + uuid.uuid4().hex[:5].upper(), 'Femi', 'Fff')
    b = _student(app, 'AN' + uuid.uuid4().hex[:5].upper(), 'Gozie', 'Ggg')
    _seed_results(app, exam_id, a, {'Mathematics': 80, 'English Language': 70, 'Biology': 75, 'Chemistry': 60, 'Physics': 55})
    _seed_results(app, exam_id, b, {'Mathematics': 30, 'English Language': 35, 'Biology': 20})

    with app.app_context():
        an = MockWAECAnalytics.get_analytics(exam_id)
        assert an['empty'] is False
        assert len(an['credit_histogram']) == 10
        # Student A has 5 credits incl. core; B has none.
        assert an['core']['both_pct'] == 50.0
        # Hardest subject has the lowest pass rate.
        assert an['hardest'][0]['pass_rate'] <= an['easiest'][0]['pass_rate']

    c = _admin(app)
    html = c.get(f'/mock-waec/exam/{exam_id}/analytics').get_data(as_text=True)
    assert 'Subject difficulty' in html and 'Credits per student' in html


def test_grid_blank_leaves_untouched(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=14)
    sid = _student(app, 'GR' + uuid.uuid4().hex[:5].upper(), 'Efe', 'Eee')
    _seed_results(app, exam_id, sid, {'Mathematics': 60})
    c = _admin(app)
    tok = auth_csrf(c)
    # Submit a blank Maths cell — the existing 60 must survive.
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'score_{sid}_mathematics': '',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row is not None and row.score == 60


def test_per_student_crud(app):
    """Edit, add and delete a single student's subject results."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=20)
    sid = _student(app, 'CR' + uuid.uuid4().hex[:5].upper(), 'Uche', 'Crud')
    _seed_results(app, exam_id, sid, {'Mathematics': 40, 'English Language': 55})
    c = _admin(app)
    base = f'/mock-waec/exam/{exam_id}/student/{sid}/edit'
    assert c.get(base).status_code == 200

    with app.app_context():
        mid = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first().id

    # EDIT: bump Maths to 78 -> grade re-derives to A1.
    tok = auth_csrf(c)
    c.post(base, data={'_csrf_token': tok, f'score_{mid}': '78'}, follow_redirects=True)
    with app.app_context():
        m = db.session.get(MockWAECResult, mid)
        assert m.score == 78 and m.grade == 'A1'

    # ADD: a missing subject (grade auto-derived).
    c.post(base, data={'_csrf_token': tok, 'add': '1', 'subject': 'Biology',
                       'score': '63', 'grade': ''}, follow_redirects=True)
    with app.app_context():
        bio = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Biology').first()
        assert bio is not None and bio.score == 63 and bio.grade == 'C4'

    # DELETE: remove Maths.
    c.post(base, data={'_csrf_token': tok, 'delete_id': str(mid)}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(MockWAECResult, mid) is None


def test_result_slip_and_print_views(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=21)
    sid = _student(app, 'SL' + uuid.uuid4().hex[:5].upper(), 'Ada', 'Slip')
    _seed_results(app, exam_id, sid, {'Mathematics': 72, 'English Language': 64, 'Biology': 30})
    c = _admin(app)

    # Preview wrappers (HTML) offer the COMPETENCE-heading toggle + embed the PDF.
    prev = c.get(f'/mock-waec/exam/{exam_id}/student/{sid}/slip').get_data(as_text=True)
    assert 'COMPETENCE RESULT' in prev and '/slip.pdf' in prev
    assert c.get(f'/mock-waec/exam/{exam_id}/slips').status_code == 200
    assert 'COMPETENCE RESULT' in c.get(f'/mock-waec/exam/{exam_id}/broadsheet/print').get_data(as_text=True)

    # Server-side PDFs render (preview = inline) for slip, all slips and broadsheet.
    for path in (f'/mock-waec/exam/{exam_id}/student/{sid}/slip.pdf',
                 f'/mock-waec/exam/{exam_id}/slips.pdf',
                 f'/mock-waec/exam/{exam_id}/broadsheet.pdf',
                 f'/mock-waec/exam/{exam_id}/broadsheet.pdf?title=0&cols=0'):
        r = c.get(path)
        assert r.status_code == 200
        assert r.headers['Content-Type'] == 'application/pdf'
        assert r.get_data()[:5] == b'%PDF-'
    # Download variant attaches the file.
    dl = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?download=1')
    assert 'attachment' in dl.headers.get('Content-Disposition', '')


def test_blank_recording_sheet_and_pdf_options(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=22)
    sid = _student(app, 'BK' + uuid.uuid4().hex[:5].upper(), 'Ola', 'Blank')
    enroll_sss3(app, sid)
    with app.app_context():
        st = db.session.get(Student, sid)
        st.waec_subjects = 'Mathematics,English Language,Biology'
        db.session.commit()
    c = _admin(app)

    # Blank recording sheet: a PDF even with no results recorded yet.
    bp = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank')
    assert bp.status_code == 200 and 'Include in the PDF' in bp.get_data(as_text=True)
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf')
    assert r.status_code == 200 and r.headers['Content-Type'] == 'application/pdf'
    assert r.get_data()[:5] == b'%PDF-'

    # Detail flags are accepted on every results PDF and still render.
    _seed_results(app, exam_id, sid, {'Mathematics': 70})
    for q in ('address=0&contact=0&motto=0&summary=0&title=0',):
        assert c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?{q}').status_code == 200
        assert c.get(f'/mock-waec/exam/{exam_id}/student/{sid}/slip.pdf?{q}&signatures=0').status_code == 200


def test_exam_crud_controls(app):
    """Create exists; the dashboard and view now expose Edit + Delete, and both
    the update and delete actions work end-to-end."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=30)
    sid = _student(app, 'EX' + uuid.uuid4().hex[:5].upper(), 'Ife', 'Crud')
    _seed_results(app, exam_id, sid, {'Mathematics': 70})
    c = _admin(app)

    # Controls are surfaced (admin sees the delete form).
    idx = c.get('/mock-waec/').get_data(as_text=True)
    assert f'/exam/{exam_id}/edit' in idx and f'/exam/{exam_id}/delete' in idx
    view = c.get(f'/mock-waec/exam/{exam_id}').get_data(as_text=True)
    assert f'/exam/{exam_id}/delete' in view

    # UPDATE: rename + mark completed.
    tok = auth_csrf(c)
    c.post(f'/mock-waec/exam/{exam_id}/edit', data={
        '_csrf_token': tok, 'name': 'Renamed Mock', 'is_completed': 'on'},
        follow_redirects=True)
    with app.app_context():
        ex = db.session.get(MockWAECExam, exam_id)
        assert ex.name == 'Renamed Mock' and ex.is_completed is True

    # DELETE: exam and its results go.
    r = c.post(f'/mock-waec/exam/{exam_id}/delete', data={'_csrf_token': tok},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert db.session.get(MockWAECExam, exam_id) is None
        assert MockWAECResult.query.filter_by(mock_exam_id=exam_id).count() == 0


def test_broadsheet_orientation_and_blank_columns(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=41)
    sid = _student(app, 'OR' + uuid.uuid4().hex[:5].upper(), 'Tobi', 'Land')
    enroll_sss3(app, sid)
    with app.app_context():
        db.session.get(Student, sid).waec_subjects = 'Mathematics,English Language,Biology'
        db.session.commit()
    _seed_results(app, exam_id, sid, {'Mathematics': 70})
    c = _admin(app)
    # Both orientations render for filled and blank broadsheets.
    for orient in ('landscape', 'portrait'):
        a = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?orient={orient}')
        b = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?orient={orient}')
        assert a.status_code == 200 and a.get_data()[:5] == b'%PDF-'
        assert b.status_code == 200 and b.get_data()[:5] == b'%PDF-'
    # Preview pages expose the orientation control.
    assert 'orientSel' in c.get(f'/mock-waec/exam/{exam_id}/broadsheet/print').get_data(as_text=True)


def test_blank_sheet_portrait_one_wide_many_subjects(app):
    """Regression: portrait + one-wide-page + many subjects must not blow up the
    layout — it splits across sheets instead of crushing the columns."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=42)
    sid = _student(app, 'PW' + uuid.uuid4().hex[:5].upper(), 'Many', 'Subs')
    enroll_sss3(app, sid)
    with app.app_context():
        db.session.get(Student, sid).waec_subjects = (
            'English Language,Mathematics,Civic Education,Biology,Physics,Chemistry,'
            'Agricultural Science,Christian Religious Studies,Literature in English,'
            'Economics,Commerce,Geography,Government,Further Mathematics,Data Processing')
        db.session.commit()
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?orient=portrait&cols=0')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
    r2 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?orient=landscape&cols=0')
    assert r2.status_code == 200 and r2.get_data()[:5] == b'%PDF-'


def test_blank_sheet_summary_and_grade_key(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=43)
    sid = _student(app, 'BG' + uuid.uuid4().hex[:5].upper(), ' Keys', 'Grade')
    enroll_sss3(app, sid)
    with app.app_context():
        db.session.get(Student, sid).waec_subjects = 'Mathematics,English Language,Biology'
        db.session.commit()
    c = _admin(app)
    # Preview offers the summary-rows and grade-key toggles.
    prev = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank').get_data(as_text=True)
    assert 'Blank summary rows' in prev and 'Grade key' in prev
    # Renders with them on (default) and off.
    for q in ('', '?summary=0&grades=0'):
        r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf{q}')
        assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'


def test_subject_outlook_from_mock_waec(app):
    """WAEC subject outlook is projected from the student's Mock WAEC sittings."""
    ssid = _session(app)
    sid = _student(app, 'OL' + uuid.uuid4().hex[:5].upper(), 'Ola', 'Outlook')
    for n, scores in ((1, {'Mathematics': 58, 'English Language': 52, 'Biology': 40}),
                      (2, {'Mathematics': 66, 'English Language': 60, 'Biology': 48})):
        eid = _exam(app, ssid, n=70 + n)
        _seed_results(app, eid, sid, scores)
    with app.app_context():
        ol = MockWAECAnalytics.subject_outlook(sid)
        assert ol['total_subjects'] == 3
        subs = {p['subject']: p for p in ol['subject_predictions']}
        # Maths improved 58 -> 66, so the projection should land in the credit range.
        assert subs['Mathematics']['trend'] == 'improving'
        assert subs['Mathematics']['predicted_grade'] in ('C4', 'C5', 'C6', 'B3', 'B2')
        assert ol['summary']['overall_outlook'] in ('Excellent', 'Good', 'Fair', 'Needs Improvement')


def test_analytics_statistics_depth(app):
    """Mock WAEC analytics carries the deeper stats ported from real WAEC:
    std-dev, quartiles (overall, per-student, per-subject) and top/bottom lists."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=81)
    for i, (m, e) in enumerate([(80, 70), (40, 55), (60, 62), (75, 48)]):
        sid = _student(app, f'ST{i}' + uuid.uuid4().hex[:4], f'S{i}', 'Stat')
        _seed_results(app, exam_id, sid, {'Mathematics': m, 'English Language': e})
    with app.app_context():
        a = MockWAECAnalytics.get_analytics(exam_id)
        o = a['score_stats']['overall']
        assert {'n', 'mean', 'std_dev', 'q1', 'median', 'q3', 'min', 'max'} <= set(o)
        assert o['std_dev'] > 0 and o['n'] == 8
        assert 'std_dev' in a['subject_stats']['Mathematics']
        assert len(a['top_performers']) == 4 and len(a['bottom_performers']) == 4
        # Top performer's average is >= bottom performer's.
        assert a['top_performers'][0]['average_score'] >= a['bottom_performers'][0]['average_score']
    c = _admin(app)
    html = c.get(f'/mock-waec/exam/{exam_id}/analytics').get_data(as_text=True)
    assert 'Score statistics' in html and 'Std dev' in html
