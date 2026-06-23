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
