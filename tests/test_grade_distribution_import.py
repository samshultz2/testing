"""Parsing/classification for importing a branch's own subject-wise grade
distribution sheet (paste, file upload, or OCR) into BranchGradeDistribution
rows — see utils/grade_distribution_import.py."""
from utils.grade_distribution_import import (
    parse_pasted_table, classify_header, match_subject_name, build_distribution_rows,
    merge_rows_by_subject,
)

WAEC_BANDS = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']


def test_parse_pasted_table_tab_separated():
    text = "Subject\tSAT\tA1\tB2\nMathematics\t129\t3\t52\nEnglish\t129\t1\t12"
    t = parse_pasted_table(text)
    assert t['headers'] == ['Subject', 'SAT', 'A1', 'B2']
    assert t['rows'] == [['Mathematics', '129', '3', '52'], ['English', '129', '1', '12']]


def test_parse_pasted_table_comma_separated():
    text = "Subject,SAT,A1,B2\nChemistry,100,15,44"
    t = parse_pasted_table(text)
    assert t['headers'] == ['Subject', 'SAT', 'A1', 'B2']
    assert t['rows'] == [['Chemistry', '100', '15', '44']]


def test_classify_header_candidates_and_bands():
    assert classify_header('SAT', WAEC_BANDS) == ('candidates', None)
    assert classify_header('No. Sat', WAEC_BANDS) == ('candidates', None)
    assert classify_header('A1', WAEC_BANDS) == ('band', ['A1'])
    assert classify_header('C4', WAEC_BANDS) == ('band', ['C4'])


def test_classify_header_combined_band_range():
    role, bands = classify_header('D7-E8', WAEC_BANDS)
    assert role == 'band' and bands == ['D7', 'E8']
    role, bands = classify_header('D7 / E8', WAEC_BANDS)
    assert role == 'band' and bands == ['D7', 'E8']


def test_classify_header_ignores_derived_columns():
    for h in ('Passes (A1-C6)', 'Credit Pass Rate', 'Credit%', 'Rank', 'S/N', 'Average'):
        assert classify_header(h, WAEC_BANDS)[0] == 'ignore'


def test_match_subject_name_aliases():
    catalog = ['Mathematics', 'Further Mathematics', 'Christian Religious Studies',
              'Livestock Farming', 'Digital Technologies', 'Civic Education']
    assert match_subject_name('MATHS', catalog) == 'Mathematics'
    assert match_subject_name('F/MATHS', catalog) == 'Further Mathematics'
    assert match_subject_name('CRS', catalog) == 'Christian Religious Studies'
    assert match_subject_name('LIVEST.', catalog) == 'Livestock Farming'
    assert match_subject_name('DIGITAL', catalog) == 'Digital Technologies'
    assert match_subject_name('CIVIC', catalog) == 'Civic Education'


def test_match_subject_name_unrecognised_kept_as_is():
    assert match_subject_name('Underwater Basket Weaving', ['Mathematics']) == 'Underwater Basket Weaving'


def test_build_distribution_rows_from_reference_style_sheet():
    """Mirrors the Pioneer Education Centre report shape: Subject, SAT,
    A1..C6, a combined D7-E8, then derived Passes/Credit% columns to ignore."""
    headers = ['Subject', 'SAT', 'A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7 - E8',
              'Passes(A1-C6)', 'Credit%']
    rows = [
        ['CHEM', '100', '15', '44', '36', '3', '', '', '', '100', '100.00%'],
        ['CIVIC', '129', '119', '5', '4', '', '', '', '1', '128', '99.22%'],
        ['TOTAL OVERALL', '1137', '339', '143', '369', '128', '74', '46', '38', '1099', ''],
    ]
    catalog = ['Chemistry', 'Civic Education']
    out = build_distribution_rows(headers, rows, WAEC_BANDS, subject_catalog=catalog)
    # the totals row must be dropped, not imported as a "subject"
    assert [r['subject'] for r in out] == ['Chemistry', 'Civic Education']

    chem = out[0]
    assert chem['candidates'] == 100
    assert chem['counts']['A1'] == 15 and chem['counts']['B2'] == 44 and chem['counts']['B3'] == 36
    assert chem['counts']['C4'] == 3
    assert chem['counts']['D7'] == 0 and chem['counts']['E8'] == 0   # blank combined cell

    civic = out[1]
    assert civic['candidates'] == 129
    assert civic['counts']['A1'] == 119
    # the combined "D7 - E8" = 1 splits across both bands (1 -> 1,0)
    assert civic['counts']['D7'] + civic['counts']['E8'] == 1


def test_build_distribution_rows_defaults_candidates_from_band_sum_when_no_sat_column():
    headers = ['Subject', 'A1', 'B2']
    rows = [['Physics', '4', '6']]
    out = build_distribution_rows(headers, rows, WAEC_BANDS)
    assert out[0]['candidates'] == 10


def test_build_distribution_rows_skips_blank_subject_rows():
    headers = ['Subject', 'SAT', 'A1']
    rows = [['', '10', '1'], ['Biology', '10', '1']]
    out = build_distribution_rows(headers, rows, WAEC_BANDS)
    assert len(out) == 1 and out[0]['subject'] == 'Biology'


def test_match_subject_name_general_mathematics_is_mathematics():
    """The exact bug reported: 'General Mathematics' (WAEC's own official
    paper name) must resolve to the school's catalogued 'Mathematics', not
    sit beside it as a lookalike duplicate subject."""
    catalog = ['Mathematics', 'Further Mathematics']
    for variant in ('General Mathematics', 'GENERAL MATHS', 'Gen. Maths', 'Core Mathematics'):
        assert match_subject_name(variant, catalog) == 'Mathematics'


def test_match_subject_name_common_alternate_names():
    from utils.helpers import WAEC_SUBJECTS
    cases = {
        'Use of English': 'English Language', 'English': 'English Language',
        'Lit': 'Literature in English', 'Literature': 'Literature in English',
        'CRK': 'Christian Religious Studies', 'Bible Knowledge': 'Christian Religious Studies',
        'IRK': 'Islamic Religious Studies',
        'Agric': 'Agricultural Science', 'Agriculture': 'Agricultural Science',
        'Govt': 'Government', 'Civics': 'Civic Education',
        'Accounts': 'Accounting', 'Book Keeping': 'Accounting',
        'Add Maths': 'Further Mathematics', 'Further Maths': 'Further Mathematics',
        'Hist': 'History', 'Art': 'Visual Arts', 'Geog': 'Geography',
        'ICT': 'Computer Studies', 'PHE': 'Physical Education',
    }
    for raw, expected in cases.items():
        assert match_subject_name(raw, WAEC_SUBJECTS) == expected, raw


def test_build_distribution_rows_merges_alias_duplicates_within_one_sheet():
    """A sheet that (by mistake) lists both spellings must merge into one
    subject row, not two."""
    headers = ['Subject', 'SAT', 'A1', 'B2']
    rows = [
        ['Mathematics', '10', '3', '2'],
        ['General Mathematics', '5', '1', '1'],
    ]
    out = build_distribution_rows(headers, rows, WAEC_BANDS, subject_catalog=['Mathematics'])
    assert len(out) == 1
    assert out[0]['subject'] == 'Mathematics'
    assert out[0]['candidates'] == 15
    assert out[0]['counts']['A1'] == 4 and out[0]['counts']['B2'] == 3


def test_merge_rows_by_subject_sums_counts():
    rows = [
        {'subject': 'Mathematics', 'candidates': 10, 'counts': {'A1': 2, 'B2': 3}},
        {'subject': 'Mathematics', 'candidates': 5, 'counts': {'A1': 1, 'C4': 2}},
        {'subject': 'Physics', 'candidates': 8, 'counts': {'B2': 4}},
    ]
    out = merge_rows_by_subject(rows)
    assert len(out) == 2
    maths = next(r for r in out if r['subject'] == 'Mathematics')
    assert maths['candidates'] == 15
    assert maths['counts'] == {'A1': 3, 'B2': 3, 'C4': 2}
