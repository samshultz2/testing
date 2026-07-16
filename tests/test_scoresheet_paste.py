"""Paste-CSV score entry: parser + preview matching (reuses the scan review grid)."""
from flask import url_for

from models import db, ClassSubject, Student
from routes.subjects import _parse_pasted_scores, _sheet_columns
from tests.conftest import auth_csrf
from tests.test_results_workflow import _setup, _admin


def test_parse_pasted_scores_basic():
    rows = _parse_pasted_scores("WF1, 80, 55\nWF2, 40, 30", num_columns=2)
    assert rows == [{'identifier': 'WF1', 'cells': ['80', '55']},
                    {'identifier': 'WF2', 'cells': ['40', '30']}]


def test_parse_pasted_scores_blanks_header_and_limit():
    text = ("Name, CA1, CA2\n"          # header -> skipped
            "WF1, -, 12, 99\n"          # dash -> '', extra col beyond 2 dropped
            "  \n"                       # blank -> skipped
            "WF2, absent, 7")
    rows = _parse_pasted_scores(text, num_columns=2)
    assert rows == [{'identifier': 'WF1', 'cells': ['', '12']},
                    {'identifier': 'WF2', 'cells': ['', '7']}]


def test_paste_preview_matches_students_and_values(app):
    ids = _setup(app)
    c = _admin(app)
    with app.test_request_context():
        cs = db.session.get(ClassSubject, ids['cs'])
        cols = _sheet_columns(cs)
        ncols = len(cols)
        first_at = cols[0][0].id
        paste_url = url_for('subjects.scoresheet_paste')
    # First column = 80 for WF1, 40 for WF2; remaining columns dashes.
    line = lambda adm, first: adm + ', ' + ', '.join([str(first)] + ['-'] * (ncols - 1))
    r = c.post(paste_url, data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        '_csrf_token': auth_csrf(c),
        'data': line('WF1', 80) + '\n' + line('WF2', 40),
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/scores/scan/save' in body              # rendered the review/confirm grid (save form)
    assert f'name="cell_0_{first_at}"' in body and 'value="80"' in body
    assert 'value="40"' in body
    assert 'name="row_count" value="2"' in body
    # both students were matched on their admission number (selected in dropdown)
    with app.app_context():
        a = db.session.get(Student, ids['a'])
        assert f'value="{a.id}" selected' in body


# --- name matching (the AI/CSV paste bug: rows matched on names, not numbers) ---
class _S:
    def __init__(self, first, sur, mid=''):
        self.first_name, self.surname, self.middle_name = first, sur, mid

    @property
    def full_name(self):
        return f'{self.surname} {self.first_name} {self.middle_name}'.strip()


def test_match_student_is_order_and_middlename_robust():
    from utils.waec_ocr import match_student
    roster = [_S('Ada', 'Obi', 'Chidinma'), _S('Emeka', 'Nwosu'), _S('John', 'Bull')]
    # order flipped, middle name absent -> still matches
    assert match_student('Ada Obi', roster)[0].full_name.startswith('Obi')
    assert match_student('Nwosu Emeka', roster)[0].first_name == 'Emeka'
    assert match_student('ADA   OBI', roster)[0].first_name == 'Ada'      # case + spacing
    # a genuinely unknown name must NOT be matched to anyone
    assert match_student('Totally Unknown', roster)[0] is None


def test_paste_matches_students_by_name_when_numbers_differ(app):
    """The reported bug: the pasted rows carry NAMES (school uses its own numbers),
    so matching must be by name — and every matched row must be selectable/saveable."""
    ids = _setup(app)
    c = _admin(app)
    with app.test_request_context():
        cs = db.session.get(ClassSubject, ids['cs'])
        ncols = len(_sheet_columns(cs))
        paste_url = url_for('subjects.scoresheet_paste')
    line = lambda nm, first: nm + ', ' + ', '.join([str(first)] + ['-'] * (ncols - 1))
    # paste with names in "Firstname Surname" order (register stores "Surname First…")
    r = c.post(paste_url, data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        '_csrf_token': auth_csrf(c),
        'data': line('Aa One', 71) + '\n' + line('Bb Two', 83),   # theory over 70 also fine
    })
    body = r.get_data(as_text=True)
    with app.app_context():
        a = db.session.get(Student, ids['a']); b = db.session.get(Student, ids['b'])
        assert f'value="{a.id}" selected' in body and f'value="{b.id}" selected' in body
    assert 'value="71"' in body and 'value="83"' in body


def test_save_reports_rows_left_unmatched(app):
    """Rows with scores but no student selected must be reported, not silently dropped."""
    ids = _setup(app)
    c = _admin(app)
    with app.test_request_context():
        cs = db.session.get(ClassSubject, ids['cs'])
        first_at = _sheet_columns(cs)[0][0].id
        save_url = url_for('subjects.scoresheet_save')
    r = c.post(save_url, data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        '_csrf_token': auth_csrf(c), 'row_count': '1',
        'student_0': '',                       # unmatched
        'rowname_0': 'Unknown Pupil',
        f'cell_0_{first_at}': '65',            # but it carries a score
    }, follow_redirects=True)
    body = r.get_data(as_text=True)
    assert 'Unknown Pupil' in body and 'not saved' in body.lower()
