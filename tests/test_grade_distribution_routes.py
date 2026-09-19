"""Route-level coverage for importing a branch's own subject-wise grade
distribution sheet (paste/file/photo -> review -> save) and its merge into
the Subject-Wise Grade Breakdown report alongside branches that have
per-student WAEC/JAMB rows in the DB — see routes/results/analytics.py's
grade_distribution_import(_save) and _branch_grade_breakdown(uploaded=)."""
import io
import uuid

from config import Config
from models import db, Student, Branch, WAECResult, BranchGradeDistribution
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _branch(name):
    b = Branch.query.filter_by(name=name).first()
    if not b:
        b = Branch(name=name, code=uuid.uuid4().hex[:8].upper())
        db.session.add(b); db.session.flush()
    return b


def _student(branch_id, tag):
    s = Student(student_id='GD' + uuid.uuid4().hex[:7].upper(), first_name='Br',
                surname=tag, gender='Female', branch_id=branch_id)
    db.session.add(s)
    return s


def test_import_form_renders(app):
    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown/import?exam=waec').get_data(as_text=True)
    assert 'Import Branch Report' in html
    assert 'Paste Text' in html and 'Upload File' in html and 'Scan Photo' in html


def test_paste_tab_has_copyable_ai_prompt_matching_the_exam_bands(app):
    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown/import?exam=waec').get_data(as_text=True)
    assert 'id="aiPrompt"' in html and 'id="copyPrompt"' in html
    # the prompt must spell out WAEC's exact band order so the AI's reply
    # pastes straight into build_distribution_rows() without remapping
    assert 'Subject\tSAT\tA1\tB2\tB3\tC4\tC5\tC6\tD7\tE8\tF9' in html

    html_jamb = c.get('/results/subject-branch-breakdown/import?exam=jamb').get_data(as_text=True)
    assert '90-100' in html_jamb and '0-19' in html_jamb


def test_paste_flow_goes_to_review_with_parsed_rows(app):
    yr = 2087
    with app.app_context():
        b = _branch('GD New Benin')
        db.session.commit()
        bid = b.id
    c = _admin(app)
    text = "Subject\tSAT\tA1\tB2\tB3\tC4\tC5\tC6\tD7\tE8\tF9\nMathematics\t20\t3\t5\t6\t2\t1\t1\t1\t1\t0"
    r = c.post('/results/subject-branch-breakdown/import?exam=waec',
              data={'branch_id': bid, 'exam_year': yr, 'method': 'paste', 'data': text,
                    '_csrf_token': auth_csrf(c)})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Review Import' in body
    assert 'value="Mathematics"' in body
    assert f'value="{yr}"' in body


def test_save_flow_persists_and_replaces_on_reimport(app):
    yr = 2088
    with app.app_context():
        b = _branch('GD Siluko')
        db.session.commit()
        bid = b.id
    c = _admin(app)

    def _post(subject, candidates, a1):
        return c.post('/results/subject-branch-breakdown/import/save', data={
            'exam': 'waec', 'branch_id': bid, 'exam_year': yr, 'source': 'paste',
            '_csrf_token': auth_csrf(c),
            'subject[]': [subject], 'candidates[]': [str(candidates)],
            f'band_0_A1': str(a1), 'band_0_B2': '0', 'band_0_B3': '0', 'band_0_C4': '0',
            'band_0_C5': '0', 'band_0_C6': '0', 'band_0_D7': '0', 'band_0_E8': '0', 'band_0_F9': '0',
        })

    r = _post('Chemistry', 10, 4)
    assert r.status_code == 302

    with app.app_context():
        rows = BranchGradeDistribution.query.filter_by(branch_id=bid, exam='waec', exam_year=yr).all()
        assert len(rows) == 1
        assert rows[0].subject == 'Chemistry' and rows[0].candidates == 10
        assert rows[0].counts()['A1'] == 4

    # Re-importing the SAME period replaces rather than duplicating/accumulating.
    r2 = _post('Chemistry', 10, 7)
    assert r2.status_code == 302
    with app.app_context():
        rows = BranchGradeDistribution.query.filter_by(branch_id=bid, exam='waec', exam_year=yr).all()
        assert len(rows) == 1
        assert rows[0].counts()['A1'] == 7


def test_uploaded_distribution_merges_into_grade_breakdown_alongside_db_branch(app):
    """A branch with real per-student WAECResult rows (DB-derived) and a
    different branch with only an uploaded summary sheet must appear
    together on the same Grade Breakdown table."""
    yr = 2089
    with app.app_context():
        db_branch = _branch('GD Jemila')
        upload_branch = _branch('GD Upload Branch')
        db.session.flush()
        s1 = _student(db_branch.id, 'One')
        db.session.flush()
        db.session.add(WAECResult(student_id=s1.id, exam_year=yr, subject='Physics', grade='A1'))
        db.session.add(BranchGradeDistribution(
            branch_id=upload_branch.id, exam='waec', exam_year=yr, subject='Physics', candidates=20,
            band_counts='{"A1": 5, "B2": 10, "B3": 5, "C4": 0, "C5": 0, "C6": 0, "D7": 0, "E8": 0, "F9": 0}',
            source='paste'))
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=waec&year={yr}').get_data(as_text=True)
    assert 'GD Jemila' in html and 'GD Upload Branch' in html
    assert 'Physics' in html
    assert 'From an imported branch report' in html   # the uploaded-branch indicator


def test_uploaded_distribution_wins_over_db_rows_for_same_branch_subject(app):
    """When the SAME branch has both a DB row and an uploaded aggregate for the
    same subject, the uploaded figure (the branch's own authoritative count)
    replaces the DB-derived one rather than being added to it."""
    from routes.results.analytics import _branch_grade_breakdown

    entries = [('Biology', 'A1', 'X Branch')]                 # 1 DB-derived A1
    uploaded = {('Biology', 'X Branch'): {'n': 10, 'counts': {'A1': 2, 'B2': 8}}}
    bands = WAECResult.VALID_GRADES
    pass_bands = {'A1', 'B2', 'B3', 'C4', 'C5', 'C6'}
    result = _branch_grade_breakdown(entries, bands, pass_bands, uploaded=uploaded)
    cell = result['table']['Biology']['X Branch']
    assert cell['n'] == 10                      # the uploaded total, not 1 (DB) + 10
    assert cell['uploaded'] is True
    assert cell['pct']['A1'] == 20.0 and cell['pct']['B2'] == 80.0


def test_manage_page_lists_batches_and_edit_delete_links(app):
    yr = 2090
    with app.app_context():
        b = _branch('GD Manage Branch')
        db.session.flush()
        db.session.add(BranchGradeDistribution(
            branch_id=b.id, exam='waec', exam_year=yr, subject='Physics', candidates=12,
            band_counts='{"A1": 5, "B2": 7}', source='paste'))
        db.session.commit()
        bid = b.id

    c = _admin(app)
    html = c.get('/results/subject-branch-breakdown/imports?exam=waec').get_data(as_text=True)
    assert 'GD Manage Branch' in html
    assert f'Exam Year {yr}' in html
    assert '1' in html            # n_subjects
    # Jinja autoescapes '&' to '&amp;' in the rendered href
    assert f'/results/subject-branch-breakdown/import/edit?exam=waec&amp;branch_id={bid}&amp;exam_year={yr}' in html


def test_edit_loads_existing_batch_normalized_into_review_grid(app):
    """Two stored rows that both mean 'Mathematics' (the exact bug reported —
    "General Mathematics" imported as a separate subject) must load into the
    edit grid already merged into one Mathematics row."""
    yr = 2091
    with app.app_context():
        b = _branch('GD Edit Branch')
        db.session.flush()
        db.session.add_all([
            BranchGradeDistribution(branch_id=b.id, exam='waec', exam_year=yr, subject='Mathematics',
                                    candidates=10, band_counts='{"A1": 2, "B2": 3}', source='paste'),
            BranchGradeDistribution(branch_id=b.id, exam='waec', exam_year=yr, subject='General Mathematics',
                                    candidates=5, band_counts='{"A1": 1}', source='paste'),
        ])
        db.session.commit()
        bid = b.id

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown/import/edit?exam=waec&branch_id={bid}&exam_year={yr}').get_data(as_text=True)
    assert 'Edit Import' in html
    # merged into ONE subject-row input, not two (a second value="Mathematics"
    # legitimately appears once more, in the <option> of the subject datalist)
    assert html.count('name="subject[]" list="subjectList" value="Mathematics"') == 1
    assert 'value="15"' in html                           # candidates summed: 10 + 5
    assert 'name="band_0_A1" value="3"' in html            # A1 counts summed: 2 + 1


def test_delete_removes_the_whole_batch(app):
    yr = 2092
    with app.app_context():
        b = _branch('GD Delete Branch')
        db.session.flush()
        db.session.add(BranchGradeDistribution(
            branch_id=b.id, exam='waec', exam_year=yr, subject='Chemistry', candidates=9,
            band_counts='{"A1": 9}', source='paste'))
        db.session.commit()
        bid = b.id

    c = _admin(app)
    r = c.post('/results/subject-branch-breakdown/import/delete', data={
        'exam': 'waec', 'branch_id': bid, 'exam_year': yr, '_csrf_token': auth_csrf(c)})
    assert r.status_code == 302
    with app.app_context():
        assert BranchGradeDistribution.query.filter_by(branch_id=bid, exam='waec', exam_year=yr).count() == 0


def test_already_stored_alias_mismatch_merges_on_the_live_breakdown_page(app):
    """The read-time fix: rows already saved BEFORE the alias table knew about
    "General Mathematics" must still merge correctly on the Grade Breakdown
    page itself, with no re-import required."""
    yr = 2093
    with app.app_context():
        b = _branch('GD Legacy Branch')
        db.session.flush()
        db.session.add_all([
            BranchGradeDistribution(branch_id=b.id, exam='waec', exam_year=yr, subject='Mathematics',
                                    candidates=10, band_counts='{"A1": 4}', source='paste'),
            BranchGradeDistribution(branch_id=b.id, exam='waec', exam_year=yr, subject='General Mathematics',
                                    candidates=6, band_counts='{"A1": 2}', source='paste'),
        ])
        db.session.commit()

    c = _admin(app)
    html = c.get(f'/results/subject-branch-breakdown?exam=waec&year={yr}').get_data(as_text=True)
    # exactly one Mathematics row-group for this branch, not two, and the
    # candidate counts are summed (10 + 6 = 16)
    assert html.count('>Mathematics<') == 1
    assert '>16<' in html
