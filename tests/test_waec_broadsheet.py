"""WAEC broadsheet — the grade matrix builder plus the on-screen page, the
server-side PDF and the Excel export (mirrors the mock-WAEC broadsheet)."""
from models import db, Branch, Student, WAECResult
from config import Config
from utils.analytics_service import AcademicAnalytics

_YR = 2266   # sentinel year owned solely by this test
_SEQ = [0]


def _seed(app):
    """Two students: one strong (5 credits incl. core), one weak."""
    with app.app_context():
        bid = Branch.get_default().id
        _SEQ[0] += 1
        a = Student(student_id=f'WBS-A{_SEQ[0]}', first_name='Ada', surname=f'Aaa{_SEQ[0]}',
                    gender='Female', is_active=True, branch_id=bid)
        b = Student(student_id=f'WBS-B{_SEQ[0]}', first_name='Bola', surname=f'Bbb{_SEQ[0]}',
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        rows = {
            a.id: {'English Language': 'B2', 'Mathematics': 'A1', 'Physics': 'C4',
                   'Chemistry': 'C6', 'Biology': 'B3'},          # 5 credits incl. core
            b.id: {'English Language': 'D7', 'Mathematics': 'F9', 'Physics': 'E8'},  # 0 credits
        }
        for sid, gmap in rows.items():
            for subj, g in gmap.items():
                db.session.add(WAECResult(student_id=sid, exam_year=_YR, subject=subj, grade=g))
        db.session.commit()
        return a.id, b.id


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_broadsheet_builder_shape(app):
    _seed(app)
    with app.app_context():
        bs = AcademicAnalytics.get_waec_broadsheet(_YR)
        assert bs and len(bs['rows']) == 2
        # core subjects come first in canonical order
        assert bs['subjects'][:2] == ['English Language', 'Mathematics']
        # rows are sorted by surname (Aaa before Bbb)
        strong, weak = bs['rows'][0], bs['rows'][1]
        assert strong['credits'] == 5 and strong['has_5_incl_core'] is True
        assert weak['credits'] == 0 and weak['has_5_incl_core'] is False
        # grade-only cells (no scores)
        assert strong['cells']['Mathematics'] == 'A1'
        # per-subject summary: Mathematics offered by 2, one credit (A1), one fail (F9)
        m = bs['subject_summary']['Mathematics']
        assert m['offered'] == 2 and m['passed'] == 1 and m['failed'] == 1
        assert bs['school']['students'] == 2 and bs['school']['with_5_incl_core'] == 1


def test_broadsheet_none_when_empty(app):
    with app.app_context():
        assert AcademicAnalytics.get_waec_broadsheet(1901) is None


def test_broadsheet_page_pdf_and_excel(app):
    _seed(app)
    c = _admin(app)
    # on-screen page
    r = c.get(f'/results/waec/broadsheet?year={_YR}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'WAEC Broadsheet' in body and 'Mathematics' in body
    # server-side PDF (inline)
    p = c.get(f'/results/waec/broadsheet.pdf?year={_YR}')
    assert p.status_code == 200 and p.data[:4] == b'%PDF'
    # Excel export
    x = c.get(f'/results/waec/broadsheet/export?year={_YR}')
    assert x.status_code == 200
    assert 'spreadsheet' in x.headers.get('Content-Type', '')
