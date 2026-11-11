"""Subject-Wise Performance & Grade Breakdown report, independently for
WAEC, JAMB, Mock WAEC and Mock JAMB — per-subject, per-branch grade/score-band
percentages plus an overall summary by branch."""
import datetime
import uuid

from config import Config
from models import db, Student, Branch, WAECResult, JAMBResult, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult
from models.mock_jamb import MockJAMBExam, MockJAMBResult
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _student(branch_id, tag):
    s = Student(student_id='GB' + uuid.uuid4().hex[:7].upper(), first_name='Br',
                surname=tag, gender='Female', branch_id=branch_id)
    db.session.add(s)
    return s


def _branch(name):
    b = Branch.query.filter_by(name=name).first()
    if not b:
        b = Branch(name=name, code=uuid.uuid4().hex[:8].upper())
        db.session.add(b); db.session.flush()
    return b


def _active_session():
    sess = AcademicSession.query.filter_by(is_active=True).first()
    if not sess:
        sess = AcademicSession(name='2081/2082', is_active=True)
        db.session.add(sess); db.session.flush()
    return sess


def test_waec_breakdown_groups_by_subject_and_branch_with_not_offered(app):
    yr = 2081
    with app.app_context():
        b1 = _branch('GB Alpha')
        b2 = _branch('GB Beta')
        db.session.flush()
        s1 = _student(b1.id, 'One'); s2 = _student(b1.id, 'Two'); s3 = _student(b2.id, 'Three')
        db.session.flush()
        db.session.add_all([
            WAECResult(student_id=s1.id, exam_year=yr, subject='Mathematics', grade='A1'),
            WAECResult(student_id=s2.id, exam_year=yr, subject='Mathematics', grade='F9'),
            WAECResult(student_id=s3.id, exam_year=yr, subject='English Language', grade='C4'),
        ])
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=waec&year={yr}').get_data(as_text=True)
    assert 'GB Alpha' in html and 'GB Beta' in html
    assert 'Mathematics' in html and 'English Language' in html
    # Beta never sat Mathematics -> "Not Offered" for that subject/branch pairing
    assert 'not offered' in html.lower()
    assert 'Overall Credit Pass (A1' in html


def test_jamb_breakdown_uses_score_bands(app):
    yr = 2082
    with app.app_context():
        b1 = _branch('GB Gamma')
        db.session.flush()
        s1 = _student(b1.id, 'Four')
        db.session.flush()
        db.session.add(JAMBResult(student_id=s1.id, exam_year=yr, total_score=180,
                                  subject1='English', subject1_score=92,
                                  subject2='Mathematics', subject2_score=18))
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=jamb&year={yr}').get_data(as_text=True)
    assert 'Score Band' in html
    assert '90-100' in html and '0-19' in html
    assert 'GB Gamma' in html
    assert 'Overall ≥50 Rate' in html


def test_mock_waec_breakdown_selects_current_session_sitting(app):
    with app.app_context():
        sess = _active_session()
        b1 = _branch('GB Delta')
        db.session.flush()
        ex = MockWAECExam(name='GB Mock', exam_number=7, session_id=sess.id,
                          exam_date=datetime.date.today(), branch_id=b1.id)
        db.session.add(ex); db.session.flush()
        s1 = _student(b1.id, 'Five')
        db.session.flush()
        db.session.add(MockWAECResult(student_id=s1.id, mock_exam_id=ex.id,
                                      subject='Chemistry', score=80, grade='B2'))
        db.session.commit()

    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown?exam=mock_waec').get_data(as_text=True)
    assert 'GB Delta' in html
    assert 'Chemistry' in html
    assert f'Mock 7' in html


def test_mock_jamb_breakdown_pivots_subject_slots(app):
    with app.app_context():
        sess_id = _active_session().id
        b1 = _branch('GB Epsilon')
        db.session.flush()
        ex = MockJAMBExam(name='GB JMock', exam_number=9, session_id=sess_id,
                          exam_date=datetime.date.today(), branch_id=b1.id)
        db.session.add(ex); db.session.flush()
        s1 = _student(b1.id, 'Six')
        db.session.flush()
        db.session.add(MockJAMBResult(student_id=s1.id, mock_exam_id=ex.id, total_score=140,
                                      subject1='Physics', subject1_score=55,
                                      subject2='Biology', subject2_score=40))
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=mock_jamb&mock={sess_id}_9').get_data(as_text=True)
    assert 'GB Epsilon' in html
    assert 'Physics' in html and 'Biology' in html


def test_no_data_shows_empty_state(app):
    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown?exam=waec&year=1904').get_data(as_text=True)
    assert 'No WAEC results recorded' in html


def test_exam_type_switcher_links_present(app):
    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown').get_data(as_text=True)
    assert 'exam=waec' in html and 'exam=jamb' in html
    assert 'exam=mock_waec' in html and 'exam=mock_jamb' in html


def test_download_buttons_present_when_data_exists(app):
    yr = 2084
    with app.app_context():
        b1 = _branch('GB Zeta')
        db.session.flush()
        s1 = _student(b1.id, 'Seven')
        db.session.flush()
        db.session.add(WAECResult(student_id=s1.id, exam_year=yr, subject='Mathematics', grade='A1'))
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=waec&year={yr}').get_data(as_text=True)
    assert '/subject-branch-breakdown/export.pdf' in html
    assert '/subject-branch-breakdown/export.docx' in html
    assert '/subject-branch-breakdown/export.xlsx' in html
    assert '/subject-branch-breakdown/export.png' in html


def test_export_without_data_redirects_with_flash(app):
    c = _admin(app)
    r = c.get('/results/subject-branch-breakdown/export.pdf?exam=waec&year=1904')
    assert r.status_code == 302
    assert '/subject-branch-breakdown' in r.headers['Location']


def test_export_rejects_unknown_format(app):
    c = _admin(app)
    r = c.get('/results/subject-branch-breakdown/export.bogus?exam=waec')
    assert r.status_code == 404


def test_waec_export_pdf_docx_xlsx_png(app):
    yr = 2085
    with app.app_context():
        b1 = _branch('GB Eta')
        b2 = _branch('GB Theta')
        db.session.flush()
        s1 = _student(b1.id, 'Eight'); s2 = _student(b2.id, 'Nine')
        db.session.flush()
        db.session.add_all([
            WAECResult(student_id=s1.id, exam_year=yr, subject='Mathematics', grade='A1'),
            WAECResult(student_id=s2.id, exam_year=yr, subject='English Language', grade='C6'),
        ])
        db.session.commit()

    c = _admin(app)
    r = c.get(f'/results/subject-branch-breakdown/export.pdf?exam=waec&year={yr}')
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert r.get_data()[:4] == b'%PDF'

    r = c.get(f'/results/subject-branch-breakdown/export.docx?exam=waec&year={yr}')
    assert r.status_code == 200
    assert r.mimetype == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    from docx import Document
    import io
    doc = Document(io.BytesIO(r.get_data()))
    # Same design as the PDF: a header picture, then editable tables for the
    # subject breakdown and the branch ranking & summary.
    heads = {t.rows[0].cells[0].text: [c_.text for c_ in t.rows[0].cells] for t in doc.tables}
    subj = heads['SUBJECT']
    assert subj[:3] == ['SUBJECT', 'BRANCH', 'N'] and 'A1' in subj and subj[-1] == 'CREDIT RATE'
    rank = heads['RANK']
    assert rank[:3] == ['RANK', 'BRANCH', 'ENTRIES'] and 'WEIGHTED GPA' in rank
    assert doc.inline_shapes   # the header picture

    r = c.get(f'/results/subject-branch-breakdown/export.xlsx?exam=waec&year={yr}')
    assert r.status_code == 200
    assert r.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    from openpyxl import load_workbook
    import io as _io
    wb = load_workbook(_io.BytesIO(r.get_data()))
    assert wb.sheetnames == ['Overview', 'Grade Breakdown', 'Summary', 'Branch Ranking']

    r = c.get(f'/results/subject-branch-breakdown/export.png?exam=waec&year={yr}')
    assert r.status_code == 200
    assert r.mimetype in ('image/png', 'application/zip')


def test_jamb_export_uses_score_bands(app):
    yr = 2086
    with app.app_context():
        b1 = _branch('GB Iota')
        db.session.flush()
        s1 = _student(b1.id, 'Ten')
        db.session.flush()
        db.session.add(JAMBResult(student_id=s1.id, exam_year=yr, total_score=180,
                                  subject1='English', subject1_score=92))
        db.session.commit()

    c = _admin(app)
    r = c.get(f'/results/subject-branch-breakdown/export.xlsx?exam=jamb&year={yr}')
    assert r.status_code == 200
    from openpyxl import load_workbook
    import io
    wb = load_workbook(io.BytesIO(r.get_data()))
    ws = wb['Grade Breakdown']
    all_values = [c.value for row in ws.iter_rows() for c in row]
    assert any(v and '90-100' in str(v) for v in all_values)


def test_composite_ranking_computes_weighted_gpa_and_sorts_branches():
    """The second, differently-weighted summary: best band worth len(bands)
    points down to 1 for the worst, composite = weighted total / entries,
    ranked highest-first."""
    from routes.results.analytics import _branch_grade_breakdown

    entries = [
        ('Mathematics', 'A1', 'Jemila'), ('Mathematics', 'B2', 'Jemila'), ('Physics', 'B3', 'Jemila'),
        ('Mathematics', 'C6', 'New Benin'), ('Mathematics', 'F9', 'New Benin'),
    ]
    bands = WAECResult.VALID_GRADES
    pass_bands = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
    result = _branch_grade_breakdown(entries, bands, pass_bands,
                                     pass_label='Overall Credit Pass (A1–C6)', band_label='Grade')
    ranking = result['ranking']
    assert [r['branch'] for r in ranking] == ['Jemila', 'New Benin']   # best GPA first
    assert ranking[0]['rank'] == 1 and ranking[1]['rank'] == 2
    # Jemila: A1(9) + B2(8) + B3(7) = 24 / 3 entries = 8.0
    assert ranking[0]['gpa'] == 8.0
    assert ranking[0]['top3_pct'] == 100.0
    # New Benin: C6(4) + F9(1) = 5 / 2 entries = 2.5
    assert ranking[1]['gpa'] == 2.5
    assert ranking[1]['top3_pct'] == 0.0
    assert 'Composite Branch Performance Ranking' in result['ranking_title']
    assert len(result['ranking_criteria']['bullets']) == 3


def test_composite_ranking_appears_on_the_live_page_and_all_exports(app):
    yr = 2087
    with app.app_context():
        b1 = _branch('GB Kappa')
        b2 = _branch('GB Lambda')
        db.session.flush()
        s1 = _student(b1.id, 'Eleven'); s2 = _student(b2.id, 'Twelve')
        db.session.flush()
        db.session.add_all([
            WAECResult(student_id=s1.id, exam_year=yr, subject='Mathematics', grade='A1'),
            WAECResult(student_id=s2.id, exam_year=yr, subject='Mathematics', grade='F9'),
        ])
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=waec&year={yr}').get_data(as_text=True)
    assert 'Composite Branch Performance Ranking' in html
    assert 'Weighted GPA Scale' in html
    assert 'Criteria &amp; Weighting System' in html

    r = c.get(f'/results/subject-branch-breakdown/export.pdf?exam=waec&year={yr}')
    assert r.status_code == 200 and r.get_data()[:4] == b'%PDF'

    r = c.get(f'/results/subject-branch-breakdown/export.png?exam=waec&year={yr}')
    assert r.status_code == 200
    assert r.mimetype in ('image/png', 'application/zip')


def test_ranking_table_paginates_across_png_pages_instead_of_dropping_rows():
    """A school with enough branches that the ranking table alone overflows a
    single A4 page must spill onto additional pages with the header repeated
    — not silently drop the branches past the first page's bottom margin
    (the PNG renderer draws pages by hand, unlike the PDF/docx exporters
    whose table libraries paginate automatically)."""
    from routes.results.analytics import _branch_grade_breakdown
    from utils.grade_breakdown_export import grade_breakdown_png_pages

    entries = []
    bands = WAECResult.VALID_GRADES
    pass_bands = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
    for i in range(70):
        entries.append(('Mathematics', bands[i % len(bands)], f'PgBranch {i}'))
        entries.append(('Mathematics', bands[(i + 1) % len(bands)], f'PgBranch {i}'))
    result = _branch_grade_breakdown(entries, bands, pass_bands,
                                     pass_label='Overall Credit Pass (A1–C6)', band_label='Grade')
    assert len(result['ranking']) == 70
    assert any(r['rank'] == 70 for r in result['ranking'])

    meta = {'school_name': 'Pagination Test School'}
    pages = grade_breakdown_png_pages(meta, result, 'Grade', 'Overall Credit Pass (A1–C6)')
    # With 70 branches the ranking table alone can't fit on one page — this
    # must produce more than one page rather than raising or truncating.
    assert len(pages) > 1
    for p in pages:
        assert p[:8] == b'\x89PNG\r\n\x1a\n'


def test_students_without_a_branch_count_under_the_default_branch(app):
    """Results of students with no branch set must not vanish from the report."""
    from models import Branch
    with app.app_context():
        s = Student(student_id='NB' + uuid.uuid4().hex[:6].upper(), first_name='Nobranch', surname='Gb',
                    gender='Female', is_active=True, branch_id=None)
        db.session.add(s); db.session.flush()
        db.session.add_all([WAECResult(student_id=s.id, exam_year=2093, subject='Physics', grade='B3'),
                            WAECResult(student_id=s.id, exam_year=2093, subject='Chemistry', grade='F9')])
        db.session.commit()
        name = Branch.get_default().name
    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown?exam=waec&year=2093').get_data(as_text=True)
    assert 'data-name="physics"' in html and 'data-name="chemistry"' in html
    assert name in html


def test_best_branch_ties_broken_by_grade_quality_not_entries():
    """All branches 100% credit: the branch with better grades wins, not the one
    with more entries; a 3-entry branch can't win on a fluke."""
    from routes.results.analytics import _branch_grade_breakdown, _WAEC_PASS_GRADES
    from models import WAECResult
    e = ([('Commerce', 'A1', 'Jemila')] * 11 + [('Commerce', g, 'Benin') for g in ['A1'] * 3 + ['B3'] * 5 + ['C6'] * 4]
         + [('Commerce', 'A1', 'Upper')] * 3)
    r = _branch_grade_breakdown(e, WAECResult.VALID_GRADES, _WAEC_PASS_GRADES)
    assert r['subject_overall']['Commerce']['best'] == 'Jemila'
    assert r['subject_overall']['Commerce']['tie'] is True
    # identical rate and grades → nobody highlighted
    r = _branch_grade_breakdown([('Art', 'B2', 'X')] * 6 + [('Art', 'B2', 'Y')] * 6, WAECResult.VALID_GRADES, _WAEC_PASS_GRADES)
    assert r['subject_overall']['Art']['best'] is None


def test_exports_mark_the_same_best_branch():
    import io
    from routes.results.analytics import _branch_grade_breakdown, _WAEC_PASS_GRADES
    from models import WAECResult
    from utils import grade_breakdown_export as G
    from openpyxl import load_workbook
    from docx import Document
    import fitz
    e = ([('Commerce', 'A1', 'Jemila')] * 11 + [('Commerce', g, 'Benin') for g in ['A1'] * 3 + ['B3'] * 5 + ['C6'] * 4]
         + [('Commerce', 'A1', 'Upper')] * 3)
    r = _branch_grade_breakdown(e, WAECResult.VALID_GRADES, _WAEC_PASS_GRADES, band_label='Grade')
    meta = {'school_name': 'S', 'logo_path': None, 'subtitle': 'WAEC'}
    # same design as the PDF: a BEST tag in the column next to the branch
    ws = load_workbook(io.BytesIO(_save(G.grade_breakdown_xlsx(meta, r, 'Grade', 'Credit'))))['Grade Breakdown']
    assert [row[1].value for row in ws.iter_rows() if row[2].value == 'BEST'] == ['Jemila']
    doc = Document(io.BytesIO(G.grade_breakdown_docx(meta, r, 'Grade', 'Credit')))
    # Word mirrors the PDF design: the branch name followed by a BEST tag.
    assert {' '.join(c.text.split()) for t in doc.tables for row in t.rows for c in row.cells
            if 'BEST' in c.text} == {'Jemila BEST'}
    txt = ' '.join(fitz.open(stream=G.grade_breakdown_pdf(meta, r, 'Grade', 'Credit'), filetype='pdf')[0].get_text().split())
    assert 'Jemila BEST' in txt and 'Benin BEST' not in txt


def _save(wb):
    import io
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def test_small_branch_with_better_grades_gets_top_grades_note():
    """3 of 3 A1 can't be 'best' (under 5 entries) but is noted; the larger
    100%-credit branch stays best. No note when the small branch did worse."""
    import io
    from routes.results.analytics import _branch_grade_breakdown, _WAEC_PASS_GRADES
    from models import WAECResult
    from utils import grade_breakdown_export as G
    from docx import Document
    e = ([('Geography', g, 'Jemila') for g in ['A1'] * 9 + ['B2'] * 9 + ['B3'] * 2]
         + [('Geography', 'A1', 'Upper')] * 3)
    r = _branch_grade_breakdown(e, WAECResult.VALID_GRADES, _WAEC_PASS_GRADES, band_label='Grade')
    o = r['subject_overall']['Geography']
    assert o['best'] == 'Jemila'
    assert o['top_small']['branch'] == 'Upper' and o['top_small']['text'] == '3 of 3 A1'
    assert G.top_note(r, 'Geography') == 'Top grades: Upper — 3 of 3 A1 (small group)'
    paras = ' '.join(p.text for p in Document(io.BytesIO(G.grade_breakdown_docx({'school_name': 'S', 'logo_path': None, 'subtitle': 'W'}, r, 'Grade', 'Credit'))).paragraphs)
    assert 'Top grades: Upper' in paras
    # small branch that did worse → no note
    e2 = [('Geography', 'A1', 'Jemila')] * 20 + [('Geography', 'C6', 'Upper')] * 3
    r2 = _branch_grade_breakdown(e2, WAECResult.VALID_GRADES, _WAEC_PASS_GRADES, band_label='Grade')
    assert r2['subject_overall']['Geography']['top_small'] is None


def test_page_shows_top_grades_note(app):
    yr = 2094
    with app.app_context():
        b1 = _branch('GB TopBig'); b2 = _branch('GB TopSmall')
        db.session.flush()
        big = [_student(b1.id, f'Big{i}') for i in range(6)]
        small = [_student(b2.id, f'Small{i}') for i in range(3)]
        db.session.flush()
        for i, s in enumerate(big):
            db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Geography', grade='A1' if i < 2 else 'B3'))
        for s in small:
            db.session.add(WAECResult(student_id=s.id, exam_year=yr, subject='Geography', grade='A1'))
        db.session.commit()
    html = _admin(app).get(f'/results/subject-branch-breakdown?exam=waec&year={yr}').get_data(as_text=True)
    assert 'Top grades:' in html and 'GB TopSmall — 3 of 3 A1' in html


def test_composite_ranking_lists_small_branches_unranked_after_the_others():
    """Same 5-entry minimum as 'best branch': 4 perfect A1 entries can't top a
    31-entry branch in the composite ranking — listed last, unranked."""
    import io
    from routes.results.analytics import _branch_grade_breakdown, _WAEC_PASS_GRADES
    from models import WAECResult
    from utils import grade_breakdown_export as G
    import fitz
    e = ([('Commerce', 'A1', 'Jemila')] * 11 + [('Commerce', g, 'Benin') for g in ['A1'] * 3 + ['B3'] * 5 + ['C6'] * 4]
         + [('Commerce', 'A1', 'Upper')] * 4)
    r = _branch_grade_breakdown(e, WAECResult.VALID_GRADES, _WAEC_PASS_GRADES, band_label='Grade')
    assert [(x['branch'], x['rank'], x['small']) for x in r['ranking']] == [
        ('Jemila', 1, False), ('Benin', 2, False), ('Upper', '—', True)]
    assert any('fewer than 5' in b for b in r['ranking_criteria']['bullets'])
    meta = {'school_name': 'S', 'logo_path': None, 'subtitle': 'W'}
    doc = fitz.open(stream=G.grade_breakdown_pdf(meta, r, 'Grade', 'Credit'), filetype='pdf')
    assert 'Not ranked' in ' '.join(p.get_text() for p in doc)
    G.grade_breakdown_docx(meta, r, 'Grade', 'Credit')
    G.grade_breakdown_xlsx(meta, r, 'Grade', 'Credit')
    G.grade_breakdown_png_pages(meta, r, 'Grade', 'Credit')
    # every branch small -> all ranked normally, no note
    r2 = _branch_grade_breakdown([('Commerce', 'A1', 'A')] * 2 + [('Commerce', 'C6', 'B')] * 3,
                                 WAECResult.VALID_GRADES, _WAEC_PASS_GRADES, band_label='Grade')
    assert [x['rank'] for x in r2['ranking']] == [1, 2] and not r2['ranking_criteria']['has_small']


def test_empty_session_year_is_selected_in_dropdown_with_shortcut_to_latest(app):
    """The page defaults to the live session's exam year even before it has
    results. That year must be the one selected in the dropdown — otherwise
    the browser shows the first listed year while the page is really on
    another, and picking that year does nothing. The empty page links to the
    latest year that has results."""
    with app.app_context():
        sess = _active_session()
        old_name = sess.name
        sess.name = '2097/2098'
        b = _branch('GB Year Pick')
        db.session.flush()
        s1 = _student(b.id, 'YearPick')
        db.session.flush()
        db.session.add(WAECResult(student_id=s1.id, exam_year=2096, subject='Biology', grade='B3'))
        db.session.commit()
    try:
        c = _admin(app)
        html = c.get('/results/subject-branch-breakdown?exam=waec').get_data(as_text=True)
        assert 'Exam Year 2098' in html
        assert '<option value="2098" selected>' in html
        assert 'No WAEC results recorded for this year yet' in html
        assert 'results</a>' in html and 'year=' in html   # "View <latest> results" shortcut
        # choosing a year that has data works directly
        html2 = c.get('/results/subject-branch-breakdown?exam=waec&year=2096').get_data(as_text=True)
        assert '<option value="2096" selected>' in html2 and 'GB Year Pick' in html2
    finally:
        with app.app_context():
            s = AcademicSession.query.filter_by(is_active=True).first()
            s.name = old_name
            db.session.commit()


def test_years_with_keeps_the_shown_year():
    from utils.helpers import years_with
    assert years_with([2026, 2025], 2027) == [2027, 2026, 2025]
    assert years_with([2026, 2025], 2025) == [2026, 2025]
    assert years_with([], 2027) == [2027]
    assert years_with([2026], None) == [2026]


def test_waec_and_jamb_lists_select_the_session_year_even_with_no_results(app):
    """Same bug as the grade breakdown on the WAEC and JAMB lists: the page
    shows the live session's year, so the dropdown must have it selected."""
    with app.app_context():
        sess = _active_session()
        old_name = sess.name
        sess.name = '2095/2099'
        b = _branch('GB List Year')
        db.session.flush()
        s1 = _student(b.id, 'ListYear')
        db.session.flush()
        db.session.add(WAECResult(student_id=s1.id, exam_year=2093, subject='Biology', grade='B3'))
        db.session.add(JAMBResult(student_id=s1.id, exam_year=2093, total_score=200,
                                  subject1='English', subject1_score=60))
        db.session.commit()
    try:
        c = _admin(app)
        for url in ('/results/waec', '/results/jamb'):
            html = c.get(url).get_data(as_text=True)
            assert '<option value="2099" selected>' in html, url
            assert '<option value="2093" >' in html or '<option value="2093">' in html, url
    finally:
        with app.app_context():
            s = AcademicSession.query.filter_by(is_active=True).first()
            s.name = old_name
            db.session.commit()
