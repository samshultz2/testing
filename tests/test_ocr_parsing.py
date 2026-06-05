"""OCR result parsing — WAEC and JAMB across the layouts we support."""
from utils.waec_ocr import parse_waec_result, parse_jamb_result


def grades(parsed):
    return {r['subject']: r['grade'] for r in parsed['subjects']}


def scores(parsed):
    return {r['subject']: r['score'] for r in parsed['subjects']}


def test_waec_same_line():
    text = "Candidate Name: John Doe\nMathematics B2\nEnglish Language C4\nBiology A1"
    g = grades(parse_waec_result(text))
    assert g['Mathematics'] == 'B2'
    assert g['English Language'] == 'C4'
    assert g['Biology'] == 'A1'


def test_waec_split_column_layout():
    text = "Subject/Grade\nECONOMICS\nB2\nGEOGRAPHY\nC6\nENGLISH LANGUAGE\nB3"
    g = grades(parse_waec_result(text))
    assert g == {'Economics': 'B2', 'Geography': 'C6', 'English Language': 'B3'}


def test_waec_ocr_confused_a1():
    # Tesseract often reads "A1" as "Al"
    text = "Biology Al\nChemistry C6"
    g = grades(parse_waec_result(text))
    assert g['Biology'] == 'A1'


def test_waec_inline_sms_and_codes():
    text = "ENG C6, MAT B3, BIO A1, CHE C5"
    g = grades(parse_waec_result(text))
    assert g == {'English Language': 'C6', 'Mathematics': 'B3', 'Biology': 'A1', 'Chemistry': 'C5'}


def test_waec_name_not_from_subject_line():
    text = "ECONOMICS\nB2\nENGLISH LANGUAGE\nB3"
    assert parse_waec_result(text)['name'] == ''


def test_jamb_sms_format():
    text = ("Dear Adesoye Adewole Bashir, Reg Number: 202660687983CG. "
            "Your 2026 UTME Result: ENG: 56, MAT: 49, PHY: 55, CHE: 40, Aggregate: 200")
    p = parse_jamb_result(text)
    assert p['name'] == 'Adesoye Adewole Bashir'
    assert p['total_score'] == 200
    s = scores(p)
    assert s['English Language'] == 56
    assert s['Mathematics'] == 49
    assert s['Physics'] == 55
    assert s['Chemistry'] == 40


def test_jamb_tabular_with_total_label():
    text = ("Candidate Name: Jane Roe\nUse of English 68\nMathematics 72\n"
            "Physics 55\nChemistry 61\nTotal Score: 256")
    p = parse_jamb_result(text)
    assert p['total_score'] == 256
    assert scores(p)['English Language'] == 68
    assert len(p['subjects']) == 4


def test_jamb_reg_number_not_a_score():
    text = "Reg Number: 202660687983CG\nENG: 50, MAT: 50"
    p = parse_jamb_result(text)
    assert all(0 <= r['score'] <= 100 for r in p['subjects'])
    assert scores(p) == {'English Language': 50, 'Mathematics': 50}
