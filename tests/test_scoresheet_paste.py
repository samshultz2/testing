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
