"""Content-aware re-alignment of pasted student rows missing a comma.

When a hand-typed/pasted register drops a comma, the row has fewer cells than
the header and a naive index-based importer shifts every later value left (so an
address lands in the Religion column and the last real value is silently lost).
``rows_from_pasted_text`` now re-aligns short rows by anchoring strongly-typed
columns (gender / date of birth / phone) and inserting blanks for the omitted
cells. These tests pin that behaviour at the unit level (no DB needed).
"""
from utils.excel_utils import (
    rows_from_pasted_text, _realign_short_row, _looks_like, preview_student_rows,
)

HEADER = ('Surname', 'First Name', 'Middle Name', 'Gender', 'DOB',
          'Address', 'Parent Phone', 'Religion')


def _fields(header):
    from utils.excel_utils import _HEADER_ALIASES, _norm_header
    return [_HEADER_ALIASES.get(_norm_header(c)) for c in header]


def test_looks_like_typed_columns():
    assert _looks_like('gender', 'M') and _looks_like('gender', 'Female')
    assert not _looks_like('gender', 'Christian')
    assert _looks_like('dob', '2010-05-12') and _looks_like('dob', '12 May 2010')
    assert not _looks_like('dob', '12 Main Street')
    assert _looks_like('parent_phone', '08012345678')
    assert _looks_like('parent_phone', '08035341749, 07013850785')
    assert not _looks_like('parent_phone', 'Mrs. Bello')


def test_missing_middle_name_inserts_blank_not_shift():
    fields = _fields(HEADER)
    # Middle Name omitted: 7 cells for an 8-column header.
    row = ('Smith', 'Jane', 'M', '2011-03-04', '5 Oak Rd', '08087654321', 'Muslim')
    out = _realign_short_row(row, fields)
    assert len(out) == len(HEADER)
    # Gender/DOB/Phone stay in their own columns; the blank lands at Middle Name.
    assert out == ('Smith', 'Jane', '', 'M', '2011-03-04', '5 Oak Rd', '08087654321', 'Muslim') \
        or list(out) == ['Smith', 'Jane', '', 'M', '2011-03-04', '5 Oak Rd', '08087654321', 'Muslim']


def test_rows_from_pasted_text_realigns_short_data_row():
    text = ('Surname,First Name,Middle Name,Gender,DOB,Address,Parent Phone,Religion\n'
            'Doe,John,Michael,M,2010-05-12,12 Main St,08012345678,Christian\n'
            'Smith,Jane,M,2011-03-04,5 Oak Rd,08087654321,Muslim')
    rows = rows_from_pasted_text(text)
    assert len(rows) == 3
    assert all(len(r) == 8 for r in rows)            # short row padded to header width
    smith = rows[2]
    assert smith[2] == ''                            # Middle Name blank-filled
    assert smith[3] == 'M' and smith[4] == '2011-03-04'   # gender/dob anchored
    assert smith[6] == '08087654321'                 # phone not shifted


def test_omitted_typed_value_blanks_its_own_column():
    # Gender value itself omitted -> the Gender column should be blank, DOB intact.
    text = ('Surname,First Name,Gender,DOB,Address,Parent Phone\n'
            'Smith,Jane,2011-03-04,5 Oak Rd,08087654321')
    rows = rows_from_pasted_text(text)
    smith = rows[1]
    assert smith[2] == '' and smith[3] == '2011-03-04'
    assert smith[4] == '5 Oak Rd' and smith[5] == '08087654321'


def test_no_strong_column_leaves_rows_untouched():
    # Nothing typed to anchor on -> conservative: never invent commas.
    text = 'Surname,First Name\nDoe,John\nSmith'
    rows = rows_from_pasted_text(text)
    assert rows[1] == ('Doe', 'John')
    assert rows[2] == ('Smith',)                     # length preserved, no false repair


def test_correct_rows_are_not_modified():
    text = ('Surname,First Name,Gender,DOB\n'
            'Doe,John,M,2010-05-12\n'
            'Bello,Aisha,F,2012-01-01')
    rows = rows_from_pasted_text(text)
    assert rows[1] == ('Doe', 'John', 'M', '2010-05-12')
    assert rows[2] == ('Bello', 'Aisha', 'F', '2012-01-01')


def test_preview_flags_remaining_misalignment():
    # A typed column still holding the wrong shape after realignment is warned on.
    # Here Religion (free text) value 'Christian' sits where Gender is expected
    # because two early values were merged — the realigner can't fix it, so the
    # preview should warn rather than silently import a misaligned row.
    rows = [
        ('Surname', 'First Name', 'Gender', 'DOB'),
        ('Doe', 'John', 'Christian', 'notadate'),
    ]
    pre = preview_student_rows(rows)
    assert pre['rows'][0].get('warn')                # surfaced for the UI
