"""The WAEC result-slip parser must pull the candidate name from the waecdirect
layout — "Candidate's Name" (apostrophe-s, no colon), value in the next cell,
either same-line or next-line."""
from utils.waec_ocr import parse_waec_result


def test_name_same_line_after_label():
    text = (
        "Candidate's Information\n"
        "Examination Number 4132955002\n"
        "Candidate's Name ABRAHAM DESTINY ONYEMAEKI\n"
        "Examination WASSCE FOR SCHOOL CANDIDATES 2026\n"
        "Centre PIONEER EDUCATION CENTRE BENIN CITY.\n"
        "ENGLISH LANGUAGE B3\n"
    )
    out = parse_waec_result(text)
    assert out['name'] == 'Abraham Destiny Onyemaeki'


def test_name_on_next_line():
    text = (
        "Candidate's Name\n"
        "OKECHUKWU CONFIDENCE ECHE\n"
        "Examination Number\n"
        "4132955057\n"
        "GEOGRAPHY A1\n"
    )
    out = parse_waec_result(text)
    assert out['name'] == 'Okechukwu Confidence Eche'


def test_name_not_confused_with_headers():
    text = (
        "West African Examinations Council\n"
        "Candidate's Name JANE MARY DOE\n"
        "Centre SOME CENTRE\n"
    )
    out = parse_waec_result(text)
    assert out['name'] == 'Jane Mary Doe'
