"""Export-quality regressions: CSV downloads carry a UTF-8 BOM (Excel renders
accented names correctly) and every download's filename is quoted + RFC 5987
encoded so spaces (term names) don't truncate it."""
from utils.web_exports import csv_response, xlsx_response, _disposition, formula_guard


def test_csv_response_has_bom_and_charset(app):
    with app.test_request_context():
        r = csv_response('name,score\nAmíná,90\n', 'report.csv')
    body = r.get_data()
    assert body[:3] == b'\xef\xbb\xbf'                     # UTF-8 BOM for Excel
    assert 'charset=utf-8' in r.headers.get('Content-Type', '')
    assert 'Amíná'.encode('utf-8') in body       # accented name preserved


def test_disposition_quotes_filenames_with_spaces(app):
    cd = _disposition('First Term collections.csv', inline=False)['Content-Disposition']
    assert 'filename="First Term collections.csv"' in cd   # quoted -> no truncation
    assert "filename*=UTF-8''First%20Term" in cd           # RFC 5987 encoded copy


def test_disposition_strips_header_injection(app):
    cd = _disposition('evil\r\nSet-Cookie: x=1.csv', inline=False)['Content-Disposition']
    assert '\r' not in cd and '\n' not in cd               # control chars stripped


def test_formula_guard_still_neutralises_injection():
    assert formula_guard('=cmd|calc') == "'=cmd|calc"
    assert formula_guard('Normal Name') == 'Normal Name'
    assert formula_guard(42) == 42
