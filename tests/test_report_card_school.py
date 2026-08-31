"""Report card shows the real school identity (not the 'School Name' placeholder)
on the page and in the PDF, and the PDF carries the full school details."""
import re
from models import db, SchoolSettings, StudentScore, TermSummary
from tests.test_results_workflow import _setup, _admin, _pt


def _prime_school(app):
    with app.app_context():
        SchoolSettings.set('school_name', 'Greenfield International Academy')
        SchoolSettings.set('school_address', '12 Palm Avenue, Lagos')
        SchoolSettings.set('school_phone', '+234 801 234 5678')
        SchoolSettings.set('school_email', 'info@greenfield.edu.ng')
        db.session.commit()


def _enter_and_compute(app, ids, c):
    # enter a score + auto-compute the term summary so the report card builds
    c.post('/subjects/bulk-entry', data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], '_csrf_token': _pt(c),
        f's_{ids["a"]}_{ids["cs"]}_{ids["at"]}': '80',
        f's_{ids["b"]}_{ids["cs"]}_{ids["at"]}': '55',
    }, follow_redirects=True)


def test_report_card_page_uses_real_school_name(app):
    _prime_school(app)
    ids = _setup(app)
    c = _admin(app)
    _enter_and_compute(app, ids, c)
    html = c.get(f'/subjects/report-card/{ids["a"]}?term_id={ids["term"]}').get_data(as_text=True)
    assert 'Greenfield International Academy' in html
    assert '12 Palm Avenue, Lagos' in html
    assert '+234 801 234 5678' in html
    assert 'School Name' not in html            # placeholder must be gone


def test_report_card_pdf_has_school_details(app):
    _prime_school(app)
    ids = _setup(app)
    c = _admin(app)
    _enter_and_compute(app, ids, c)
    r = c.get(f'/subjects/report-card/{ids["a"]}/pdf?term_id={ids["term"]}')
    assert r.status_code == 200
    assert 'application/pdf' in r.headers['Content-Type']
    body = r.get_data()
    assert body[:4] == b'%PDF'
    # school identity is embedded (reportlab writes plain text streams)
    import fitz
    doc = fitz.open(stream=body, filetype='pdf')
    text = doc.load_page(0).get_text()
    assert 'Greenfield International Academy' in text
    assert 'Palm Avenue' in text
    assert '801 234 5678' in text.replace('  ', ' ')


def test_number_formatting_helper():
    from utils.numfmt import fmt_num
    assert fmt_num(34.0) == '34'
    assert fmt_num(34) == '34'
    assert fmt_num(34.3) == '34.30'
    assert fmt_num(34.333) == '34.33'
    assert fmt_num(0) == '0'
    assert fmt_num(None) == ''
    assert fmt_num(None, blank='—') == '—'
    assert fmt_num('') == ''
    assert fmt_num('abc') == 'abc'


def test_report_card_page_shows_whole_numbers(app):
    _prime_school(app)
    ids = _setup(app)
    c = _admin(app)
    _enter_and_compute(app, ids, c)   # student a scores 80 (whole)
    html = c.get(f'/subjects/report-card/{ids["a"]}?term_id={ids["term"]}').get_data(as_text=True)
    # a whole score must render as 80, never 80.0
    assert '80.0' not in html
    assert '>80<' in html or '80' in html
