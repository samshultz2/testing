"""JAMB / Mock JAMB exports end with a score-band breakdown (300+, 250–299,
200–249, 150–199, 100–149, below 100) counted over only the candidates in the
export, and it is an option in the export dialog."""
from datetime import date
from io import BytesIO

from docx import Document
from openpyxl import load_workbook

from models import db, AcademicSession, JAMBResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from utils import exam_results_doc as ERD
from tests.test_results_export_design import _client, _students, _text, _clean_limits


def test_band_counts_and_running_totals():
    bd = ERD.score_breakdown([400, 300, 299, 250, 249, 200, 199, 150, 149, 100, 99, 0, None])
    assert [r['n'] for r in bd['rows']] == [2, 2, 2, 2, 2, 2]
    assert bd['n'] == 12
    assert [r['cum'] for r in bd['rows']] == [2, 4, 6, 8, 10, 12]
    assert bd['rows'][-1]['cum_pct'] == 100


def test_option_in_both_dialog_lists():
    for t in ('students', 'subjects'):
        assert 'breakdown' in {k for k, _l, on in ERD.SCORE_COLS[t] if on}


def _seed_jamb(app, year):
    a, b, c = _students(app, ['Bandtop', 'Bandmid', 'Bandlow'])
    with app.app_context():
        for sid, tot in ((a, 312), (b, 231), (c, 95)):
            db.session.add(JAMBResult(student_id=sid, exam_year=year, total_score=tot,
                                      subject1='Use of English', subject1_score=tot // 4,
                                      subject2='Mathematics', subject2_score=tot // 4,
                                      subject3='Physics', subject3_score=tot // 4,
                                      subject4='Chemistry', subject4_score=tot - 3 * (tot // 4)))
        db.session.commit()


def test_jamb_pdf_word_excel_breakdown_only_counts_exported(app):
    _clean_limits(app)
    _seed_jamb(app, 2071)
    c = _client(app)
    base = '/results/jamb/export?year=2071'
    txt = _text(c.get(base + '&format=pdf&type=students').data)
    assert 'SCORE-BAND BREAKDOWN' in txt and '3 candidates in this export' in txt
    # Range filter → only the exported candidates are counted
    txt = _text(c.get(base + '&format=pdf&type=students&min_score=200').data)
    assert '2 candidates in this export' in txt and 'Bandlow' not in txt
    # Unticked → left out
    txt = _text(c.get(base + '&format=pdf&type=students&cols=rank,subjects').data)
    assert 'SCORE-BAND BREAKDOWN' not in txt
    # Subject analysis carries it too
    txt = _text(c.get(base + '&format=pdf&type=subjects').data)
    assert 'SCORE-BAND BREAKDOWN' in txt and '3 candidates in this export' in txt
    d = Document(BytesIO(c.get(base + '&format=word&type=students').data))
    band = [[cell.text for cell in r.cells] for r in d.tables[-1].rows]
    assert band[0][0] == 'TOTAL SCORE' and band[1][2] == '1' and band[-1][2] == '1'
    ws = load_workbook(BytesIO(c.get(base).data)).active
    vals = [[cell.value for cell in row] for row in ws.iter_rows()]
    i = next(k for k, r in enumerate(vals) if r[0] == 'Score-band breakdown')
    labels = {r[0]: r[1] for r in vals[i:]}
    assert labels['300 and above'] == 1 and labels['200 – 249'] == 1 and labels['Below 100'] == 1
    assert labels['Total'] == 3


def test_mock_jamb_breakdown(app):
    _clean_limits(app)
    a, b = _students(app, ['Mockband1', 'Mockband2'])
    with app.app_context():
        ss = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name='BD 71/72', is_active=True)
        db.session.add(ss); db.session.flush()
        ex = MockJAMBExam(name='BD Mock', exam_number=9, session_id=ss.id, exam_date=date(2071, 3, 1))
        db.session.add(ex); db.session.flush()
        for sid, tot in ((a, 262), (b, 140)):
            db.session.add(MockJAMBResult(student_id=sid, mock_exam_id=ex.id, total_score=tot,
                                          subject1='Use of English', subject1_score=tot // 4))
        db.session.commit()
        eid = ex.id
    c = _client(app)
    base = f'/mock-jamb/exam/{eid}/export?'
    txt = _text(c.get(base + 'format=pdf&type=students').data)
    assert 'SCORE-BAND BREAKDOWN' in txt and '2 candidates in this export' in txt
    txt = _text(c.get(base + 'format=pdf&type=students&max_score=200').data)
    assert '1 candidate in this export' in txt
    ws = load_workbook(BytesIO(c.get(base).data)).active
    labels = {r[0].value: r[1].value for r in ws.iter_rows() if r[0].value}
    assert labels['250 – 299'] == 1 and labels['100 – 149'] == 1 and labels['Total'] == 2
    assert c.get(base + 'format=word&type=subjects').data[:2] == b'PK'
