"""Mock WAEC broadsheet readiness extras: change since the previous mock, ABS,
borderline (45-49) papers, grade counts, subject teacher and readiness status
— always on the page, switchable in the PDF and Excel exports."""
import io
import uuid
from datetime import date

from models import db, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, MockWAECAnalytics, waec_grade_from_score
from utils.mock_broadsheet_extras import enrich, readiness
from tests.test_mock_waec_broadsheet_extras import _admin, _student

CORE = {'English Language': 0, 'Mathematics': 0}


def _setup(app):
    with app.app_context():
        s = AcademicSession(name=f'RB-{uuid.uuid4().hex[:6]}'); db.session.add(s); db.session.flush()
        m1 = MockWAECExam(name='M1', exam_number=1, session_id=s.id, exam_date=date(2026, 1, 10))
        m2 = MockWAECExam(name='M2', exam_number=2, session_id=s.id, exam_date=date(2026, 3, 2))
        db.session.add_all([m1, m2]); db.session.commit()
        ids = (m1.id, m2.id)
    tag = uuid.uuid4().hex[:5].upper()
    a = _student(app, 'RBA' + tag, 'Ada', 'Ready')
    b = _student(app, 'RBB' + tag, 'Bayo', 'Short')

    def put(exam_id, sid, scores, absent=()):
        with app.app_context():
            for subj, sc in scores.items():
                db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id, subject=subj,
                                              score=sc, grade=waec_grade_from_score(sc)))
            for subj in absent:
                db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id, subject=subj,
                                              score=None, grade=None, is_absent=True))
            db.session.commit()
    five = ['Physics', 'Chemistry', 'Biology']
    # Mock 1: Ada 3 credits; Bayo 5 credits.
    put(ids[0], a, {'English Language': 55, 'Mathematics': 40, 'Physics': 60, 'Chemistry': 30, 'Biology': 52})
    put(ids[0], b, {'English Language': 60, 'Mathematics': 60, 'Physics': 60, 'Chemistry': 60, 'Biology': 60})
    # Mock 2: Ada qualifies (5 credits incl. both); Bayo misses Maths (absent) and scores 47 in Physics.
    put(ids[1], a, {'English Language': 66, 'Mathematics': 58, 'Physics': 62, 'Chemistry': 51, 'Biology': 70})
    put(ids[1], b, {'English Language': 61, 'Physics': 47, 'Chemistry': 55, 'Biology': 60}, absent=['Mathematics'])
    return ids, a, b


def test_readiness_labels():
    assert readiness(6, [])['label'] == 'Qualifies'
    assert readiness(5, ['Mathematics'])['label'] == 'Needs Maths'
    assert readiness(5, ['English Language', 'Mathematics'])['label'] == 'Needs English & Maths'
    assert readiness(4, [])['label'] == '1 credit short'
    assert readiness(3, [])['label'] == '2 credits short'
    assert readiness(4, ['Mathematics'])['label'] == 'Needs Maths'     # the Maths credit makes five
    assert readiness(1, ['English Language'])['label'] == 'Not on track'


def test_enrich_compares_with_the_previous_mock(app):
    (m1, m2), a, b = _setup(app)
    with app.test_request_context():
        bs = enrich(MockWAECAnalytics.get_broadsheet(m2))
        rows = {r['student'].id: r for r in bs['rows']}
        assert bs['prev_exam'].id == m1
        assert rows[a]['prev']['d_credits'] == 2 and rows[a]['readiness']['key'] == 'ok'
        assert rows[b]['prev']['d_credits'] == -2
        assert rows[b]['absent'] == ['Mathematics'] and rows[b]['borderline'] == ['Physics']
        assert rows[b]['readiness']['label'] == '2 credits short'
        maths = bs['subject_summary']['Mathematics']
        assert maths['absent'] == 1 and maths['failed'] == 0          # an absence isn't a fail
        assert bs['subject_summary']['Physics']['borderline'] == 1
        # The first mock has nothing to compare with.
        assert enrich(MockWAECAnalytics.get_broadsheet(m1))['prev_exam'] is None


def test_page_shows_everything(app):
    (m1, m2), a, b = _setup(app)
    html = _admin(app).get(f'/mock-waec/exam/{m2}/broadsheet').get_data(as_text=True)
    for frag in ('>ABS<', 'td class="g d7 bl"', '± First', 'Qualifies', '2 credits short',
                 'Number at each grade', 'Subject teacher', 'Borderline (45–49)', 'No. absent', 'data-show="border"'):
        assert frag in html, frag


def _xlsx(c, url):
    from openpyxl import load_workbook
    r = c.get(url)
    assert r.status_code == 200
    return [[('' if v is None else str(v)) for v in row]
            for row in load_workbook(io.BytesIO(r.get_data())).active.iter_rows(values_only=True)]


def test_excel_follows_the_switches(app):
    (m1, m2), a, b = _setup(app)
    c = _admin(app)
    rows = _xlsx(c, f'/mock-waec/exam/{m2}/broadsheet/export')
    head = rows[0]
    assert 'Readiness' in head and any(h.startswith('Credits ± First') for h in head)
    flat = [x for r in rows for x in r]
    assert 'ABS' in flat and 'No. with A1' in flat and 'No. absent' in flat and '−2' in flat
    rows = _xlsx(c, f'/mock-waec/exam/{m2}/broadsheet/export?readiness=0&change=0&grade_counts=0&absent_row=0')
    flat = [x for r in rows for x in r]
    assert 'Readiness' not in rows[0] and not any(h.startswith('Credits ±') for h in rows[0])
    assert 'No. with A1' not in flat and 'No. absent' not in flat


def test_pdf_follows_the_switches(app):
    import fitz
    (m1, m2), a, b = _setup(app)
    c = _admin(app)

    def text(q=''):
        r = c.get(f'/mock-waec/exam/{m2}/broadsheet.pdf?{q}')
        assert r.status_code == 200
        with fitz.open(stream=r.get_data(), filetype='pdf') as d:
            return ' '.join(p.get_text() for p in d)
    on = text()
    assert 'ABS' in on and 'No. with A1' in on and 'No. absent' in on and 'Shaded score' in on
    assert 'Readiness' in on and 'Change since' in on
    off = text('readiness=0&change=0&grade_counts=0&absent_row=0&borderline=0')
    assert 'No. with A1' not in off and 'No. absent' not in off and 'Shaded score' not in off
    assert 'Readiness' not in off and 'Change since' not in off
