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


def test_match_students_unique_never_reuses_a_student():
    """The paste data-loss bug: when the roster is missing some pasted pupils, an
    independent best-match collapses several rows onto the SAME registered student.
    The duplicate overwrites the first at save time, so only a few scores survive.
    Unique matching must give each pupil to at most one row and leave the rest
    unmatched (to be picked by hand) rather than colliding."""
    from utils.waec_ocr import match_students_unique
    for s in (roster := [_S('Okechukwu', 'Chisom'), _S('Sharon', 'Ogboi', 'Efe')]):
        s.id = id(s)
    # 'Ikechukwu Favour' is not enrolled; it must NOT steal 'Okechukwu Chisom'.
    names = ['Okechukwu Chisom', 'Ogboi Efe', 'Ikechukwu Favour']
    out = match_students_unique(names, roster)
    assert out[0][0] is not None and out[0][0].first_name == 'Okechukwu'
    assert out[1][0] is not None and out[1][0].surname == 'Ogboi'
    assert out[2][0] is None                                 # unmatched, not a collision
    picked = [m.id for m, _ in out if m]
    assert len(picked) == len(set(picked))                   # every pupil used once


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


def test_sheet_columns_deduplicates_assessment_types(app):
    """A mis-seeded tenant can hold two active assessment types with the same short
    name (e.g. two 'EXAM'). The score sheet must show that column ONCE — otherwise
    a pasted value is split across the duplicate ids and looks lost on the report."""
    from models import AssessmentType
    ids = _setup(app)
    with app.app_context():
        # add a duplicate active 'EXAM' type alongside the one _setup created
        db.session.add(AssessmentType(name='Dup-Exam', short_name='EXAM', max_score=40,
                                      order=98, is_active=True))
        db.session.commit()
        cs = db.session.get(ClassSubject, ids['cs'])
        cols = _sheet_columns(cs)
        shorts = [at.short_name for at, _ in cols]
        assert shorts.count('EXAM') == 1                     # collapsed, not duplicated
        assert len(shorts) == len(set(shorts))               # no short name appears twice


def test_paste_save_survives_duplicate_assessment_types(app):
    """The '0 or sometimes 6 scores' bug. When a tenant has two active assessment
    types with the SAME order value, re-deriving the column list at save time could
    resolve a column to a different id than the review grid rendered — so every cell
    read back empty and the save reported a partial (or zero) count, non-deterministically.
    The save must persist exactly what the grid posted."""
    import re
    from models import AssessmentType, StudentScore
    ids = _setup(app)
    with app.app_context():
        # two active 'EXAM' types sharing an order value (the drift trigger)
        db.session.add(AssessmentType(name='Exam A', short_name='EXAM', max_score=40, order=50, is_active=True))
        db.session.add(AssessmentType(name='Exam B', short_name='EXAM', max_score=40, order=50, is_active=True))
        db.session.commit()
        cs = db.session.get(ClassSubject, ids['cs'])
        ncols = len(_sheet_columns(cs))
    c = _admin(app)
    with app.test_request_context():
        paste_url = url_for('subjects.scoresheet_paste')
        save_url = url_for('subjects.scoresheet_save')
    # every column gets 3 (within every max, including the duplicated EXAM/40)
    data = 'Aa One, ' + ', '.join(['3'] * ncols)
    body = c.post(paste_url, data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        '_csrf_token': auth_csrf(c), 'data': data,
    }).get_data(as_text=True)
    # submit the grid back exactly as it was rendered (what a browser posts)
    save = {'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
            '_csrf_token': auth_csrf(c), 'row_count': '1',
            'student_0': str(ids['a']), 'rowname_0': 'Aa One'}
    posted = 0
    for m in re.finditer(r'name="(cell_0_\d+)"[^>]*?value="([^"]*)"', body):
        save[m.group(1)] = m.group(2)
        if m.group(2).strip():
            posted += 1
    assert posted >= 1
    c.post(save_url, data=save, follow_redirects=True)
    with app.app_context():
        scores = StudentScore.query.filter_by(class_subject_id=ids['cs'], student_id=ids['a']).all()
        assert len(scores) == posted, f'{len(scores)} saved of {posted} posted (drift loss)'
        assert all(s.score == 3 for s in scores)


def test_paste_review_grid_saves_every_row_not_just_the_first(app):
    """Regression for the real data-loss bug: the review grid named each score input
    by COLUMN index, so every row emitted identical field names — on submit they
    collided and only the first row's scores survived (the app reported "saved 6",
    then 0 on retry). Render the grid, post it back verbatim, and require BOTH
    pupils' distinct scores to persist."""
    import re
    from html.parser import HTMLParser
    from models import StudentScore
    ids = _setup(app)                                        # enrols Aa One + Bb Two
    c = _admin(app)
    with app.test_request_context():
        cs = db.session.get(ClassSubject, ids['cs'])
        cols = _sheet_columns(cs)
        ncols = len(cols)
        first_at = cols[0][0].id
        paste_url = url_for('subjects.scoresheet_paste')
        save_url = url_for('subjects.scoresheet_save')
    line = lambda nm, first: nm + ', ' + ', '.join([str(first)] + ['-'] * (ncols - 1))
    body = c.post(paste_url, data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        '_csrf_token': auth_csrf(c),
        'data': line('Aa One', 4) + '\n' + line('Bb Two', 5),   # distinct values per pupil
    }).get_data(as_text=True)

    # Harvest EVERY posted field straight from the rendered grid (what a browser sends).
    class _F(HTMLParser):
        def __init__(self): super().__init__(); self.data = {}
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in ('input', 'select') and a.get('name'):
                if tag == 'input' and a.get('type') != 'checkbox':
                    self.data[a['name']] = a.get('value', '')
        # selects: capture the selected option
        def _sel(self): pass
    # inputs
    f = _F(); f.feed(body); posted = f.data
    # selected dropdown options (student_N)
    for m in re.finditer(r'name="(student_\d+)".*?</select>', body, re.S):
        block = m.group(0)
        sel = re.search(r'<option value="(\d+)"[^>]*selected', block)
        posted[m.group(1)] = sel.group(1) if sel else ''
    posted['_csrf_token'] = auth_csrf(c)
    # the two rows must carry DISTINCT cell field names (row-indexed, not column-indexed)
    assert any(k.startswith('cell_0_') for k in posted)
    assert any(k.startswith('cell_1_') for k in posted)

    c.post(save_url, data=posted, follow_redirects=True)
    with app.app_context():
        sa = StudentScore.query.filter_by(student_id=ids['a'], class_subject_id=ids['cs'],
                                          assessment_type_id=first_at).first()
        sb = StudentScore.query.filter_by(student_id=ids['b'], class_subject_id=ids['cs'],
                                          assessment_type_id=first_at).first()
        assert sa and sa.score == 4, 'first pupil not saved'
        assert sb and sb.score == 5, 'second pupil lost to field-name collision'


def test_paste_does_not_collide_unenrolled_row_onto_a_pupil(app):
    """End-to-end: pasting a name that isn't on the register must leave that row
    unmatched instead of hijacking an enrolled pupil's slot — so the enrolled rows
    all still save (the '...it only saved 0/6 scores' report)."""
    from models import StudentScore
    ids = _setup(app)                                        # enrolls only Aa One + Bb Two
    c = _admin(app)
    with app.test_request_context():
        cs = db.session.get(ClassSubject, ids['cs'])
        cols = _sheet_columns(cs)
        ncols = len(cols)
        first_at = cols[0][0].id
        paste_url = url_for('subjects.scoresheet_paste')
        save_url = url_for('subjects.scoresheet_save')
    line = lambda nm, first: nm + ', ' + ', '.join([str(first)] + ['-'] * (ncols - 1))
    data = '\n'.join([line('Aa One', 4), line('Zz Nine', 3), line('Bb Two', 5)])
    r = c.post(paste_url, data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        '_csrf_token': auth_csrf(c), 'data': data,
    })
    body = r.get_data(as_text=True)
    with app.app_context():
        a = db.session.get(Student, ids['a']); b = db.session.get(Student, ids['b'])
        # both enrolled pupils matched exactly once; the intruder stole neither.
        assert body.count(f'value="{a.id}" selected') == 1
        assert body.count(f'value="{b.id}" selected') == 1
    # Simulate saving the reviewed grid (rows in paste order: 0=Aa,1=Zz,2=Bb).
    save = {'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
            '_csrf_token': auth_csrf(c), 'row_count': '3'}
    with app.app_context():
        save[f'student_0'] = str(ids['a']); save['rowname_0'] = 'Aa One'
        save[f'student_1'] = ''; save['rowname_1'] = 'Zz Nine'
        save[f'student_2'] = str(ids['b']); save['rowname_2'] = 'Bb Two'
        save[f'cell_0_{first_at}'] = '4'
        save[f'cell_1_{first_at}'] = '3'
        save[f'cell_2_{first_at}'] = '5'
    c.post(save_url, data=save, follow_redirects=True)
    with app.app_context():
        sa = StudentScore.query.filter_by(student_id=ids['a'], class_subject_id=ids['cs'],
                                          assessment_type_id=first_at).first()
        sb = StudentScore.query.filter_by(student_id=ids['b'], class_subject_id=ids['cs'],
                                          assessment_type_id=first_at).first()
        assert sa and sa.score == 4                           # enrolled rows both saved
        assert sb and sb.score == 5


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
