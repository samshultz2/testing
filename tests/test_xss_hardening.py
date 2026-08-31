"""XSS-audit hardening regression tests.

Covers the three tiers:
- Tier 1: the client innerHTML sinks are escaped (regression guard on the files).
- Tier 2: pdf_escape neutralises reportlab markup, and a report card PDF with a
  malicious name renders without error.
- Tier 3: strip_tags removes HTML tags on write WITHOUT entity-encoding (so it
  can't double-encode against the autoescaping output layer).
"""
import os

from utils.security import strip_tags
from utils.web_exports import pdf_escape

_ROOT = os.path.dirname(os.path.dirname(__file__))


def _read(rel):
    with open(os.path.join(_ROOT, rel), encoding='utf-8') as f:
        return f.read()


# --- Tier 3: input tag-stripping (the anti-double-encode guard) -------------

def test_strip_tags_removes_tags_but_preserves_plain_text():
    # HTML/JS payload → tags gone, inner text kept
    assert strip_tags('<script>alert(1)</script>Ada') == 'alert(1)Ada'
    assert strip_tags('<img src=x onerror=alert(1)>Bola') == 'Bola'
    # CRUCIAL: no entity-encoding — apostrophes/ampersands survive so the value
    # renders correctly through Jinja/React autoescape (no double-encoding).
    assert strip_tags("O'Brien & Sons") == "O'Brien & Sons"
    assert '&amp;' not in strip_tags('Tom & Jerry')
    assert '&#' not in strip_tags("O'Brien")
    # comparison / math text is not eaten (no letter right after '<')
    assert strip_tags('score < 5 and x > 3') == 'score < 5 and x > 3'
    assert strip_tags('Mary-Jane Watson') == 'Mary-Jane Watson'
    assert strip_tags(None) == '' and strip_tags('') == ''
    # control chars stripped
    assert strip_tags('a\x00b\x07c') == 'abc'


# --- Tier 2: reportlab markup escaping --------------------------------------

def test_pdf_escape_neutralises_markup():
    assert pdf_escape('<b>x</b>') == '&lt;b&gt;x&lt;/b&gt;'
    assert pdf_escape('A & B') == 'A &amp; B'
    assert pdf_escape(None) == ''
    assert pdf_escape(42) == '42'


def test_report_card_pdf_renders_with_malicious_name(app):
    """A student named with an HTML/reportlab payload must not break PDF
    generation (pdf_escape keeps reportlab's Paragraph parser happy)."""
    from types import SimpleNamespace
    from utils.report_pdf import report_card_pdf
    payload = '<b>x</b><font color="red">Ada</font> & <O\'Brien>'
    student = SimpleNamespace(full_name=payload, student_id='STU-1', stream='Science')
    term = SimpleNamespace(name='First Term', full_name='First Term 2025/2026',
                           session=SimpleNamespace(name='2025/2026'))
    report_data = {
        'term_summary': None, 'assignment': SimpleNamespace(display_name='SSS1 A'),
        'no_in_class': 10, 'assessment_types': [], 'subjects': [],
        'total_subjects': 0, 'total_score': 0, 'average': 0, 'overall_grade': 'A',
        'grade_scale': [], 'result_status': 'PASS',
    }
    with app.app_context():
        buf = report_card_pdf(student, report_data, term, payload, [], {})
    data = buf.getvalue()
    assert data[:4] == b'%PDF'          # a valid PDF was produced, no parser crash


# --- Tier 1: client innerHTML sinks stay escaped (regression guards) --------

def test_shared_escapers_defined_in_app_js():
    js = _read('static/js/app.js')
    assert 'window.escapeHtml' in js and 'window.safeUrl' in js


def test_client_sinks_are_escaped():
    monitor = _read('templates/cbt/monitor.html')
    assert 'esc(r.name)' in monitor and 'esc(r.sid)' in monitor
    assert '>\'+r.name+\'' not in monitor           # no raw name interpolation

    jamb = _read('templates/results/jamb_dashboard.html')
    assert 'window.escapeHtml(s.name)' in jamb
    assert '${s.name}' not in jamb

    waec = _read('templates/results/waec_dashboard.html')
    assert 'window.escapeHtml(s.name)' in waec
    assert "+ s.name +" not in waec

    # generator arm modals build options safely (no innerHTML += of arm names)
    for f in ('templates/generator/add_clash_rule.html',
              'templates/generator/add_combined_rule.html'):
        src = _read(f)
        assert 'new Option(' in src
        assert '<option value="${arm' not in src
