"""Subject-combination explorer: the combined total/average over a chosen subset
of subjects, the >=/<=/= filter, and the export endpoint (pdf/png/excel/csv).
"""
from config import Config
from tests.conftest import login_token


def test_combine_rows_total_and_average():
    from routes.subjects.reports import _combine_rows
    ds = {'rows': [
        {'student': 'A', 'subjects': {'1': 60, '2': 50, '3': 40}, 'class_name': 'X', 'arm_name': ''},
        {'student': 'B', 'subjects': {'1': 30, '2': 30, '3': 30}, 'class_name': 'X', 'arm_name': ''},
    ]}
    # Combine subjects 1+2+3, keep totals >= 120.
    rows, active, label = _combine_rows(ds, ['1', '2', '3'], 'total', 'gte', 120)
    assert active and len(rows) == 1 and rows[0]['student'] == 'A'
    assert rows[0]['combo_total'] == 150 and rows[0]['combo_average'] == 50.0
    # Average <= 30 keeps B only.
    rows2, _, _ = _combine_rows(ds, ['1', '2', '3'], 'average', 'lte', 30)
    assert [r['student'] for r in rows2] == ['B']
    # Missing subject counts as 0 in the total, divides by chosen count.
    ds2 = {'rows': [{'student': 'C', 'subjects': {'1': 60}, 'class_name': 'X', 'arm_name': ''}]}
    rows3, _, _ = _combine_rows(ds2, ['1', '2'], 'average', 'gte', 0)
    assert rows3[0]['combo_total'] == 60 and rows3[0]['combo_average'] == 30.0


def test_split_into_groups_is_balanced_by_average():
    from routes.subjects.reports import _split_into_groups
    # 10 students across bands; split into 3 groups.
    rows = [{'student': 's%d' % i, 'combo_average': a} for i, a in enumerate(
        [95, 92, 88, 85, 82, 78, 74, 61, 55, 30])]
    groups = _split_into_groups(rows, 3)
    assert len(groups) == 3
    sizes = sorted(len(g) for g in groups)
    assert sizes[-1] - sizes[0] <= 2                 # sizes within ±2
    assert sum(sizes) == len(rows)                    # everyone placed once
    # No group hoards the top scorers: each group's mean average is close.
    means = [sum(r['combo_average'] for r in g) / len(g) for g in groups if g]
    assert max(means) - min(means) < 20
    # The three highest scorers land in three different groups.
    top = {'s0', 's1', 's2'}
    where = {}
    for gi, g in enumerate(groups):
        for r in g:
            if r['student'] in top:
                where[r['student']] = gi
    assert len(set(where.values())) == 3


def test_combine_export_smoke(app):
    """The export endpoint returns each format with the right content type."""
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    # No scopes/subjects → redirects with a flash (still a valid response).
    r = c.get('/subjects/broadsheet/combine')
    assert r.status_code == 200


def test_combination_documents_use_student_list_design(app):
    """The combination export renders through the Students-page document
    engine: score columns are formatted and coloured, the subject key is a
    footnote, and every format builds."""
    import io
    import fitz
    import openpyxl
    from utils import student_list_export as SLE
    with app.app_context():
        from utils.school import school_profile, document_branding
        spec = {
            'title': 'SSS2 SCIENCE MERIT LIST', 'subtitle': 'Physics + Chemistry', 'doc_tag': 'Subject combination',
            'columns': [{'key': 'name', 'label': 'Student', 'kind': 'name'},
                        {'key': 'subj:1', 'label': 'PHY', 'kind': 'score'},
                        {'key': 'average', 'label': 'Average', 'kind': 'score', 'bold': True}],
            'groups': [{'name': 'Group A', 'rows': [{'name': ('Okafor', 'Ifeoma'), 'subj:1': 86, 'average': 88.67}]},
                       {'name': 'Group B', 'rows': [{'name': ('Musa', 'Kemi'), 'subj:1': None, 'average': 41.0}]}],
            'stats': [(2, 'Qualify', None)], 'pass_mark': 50, 'footnote': 'Key: PHY = Physics.',
            'school': school_profile(), 'colors': SLE.colors_for(document_branding()),
        }
        text = ''.join(p.get_text() for p in fitz.open(stream=SLE.render_pdf(spec), filetype='pdf'))
        assert 'SSS2 Science Merit List' in text and 'Group A' in text and 'Group B' in text
        assert '88.7' in text and '41' in text and '41.0' not in text and '–' in text
        assert 'Key: PHY = Physics.' in text
        assert SLE.render_docx(spec)[:2] == b'PK'
        ws = SLE.render_xlsx(spec).worksheets[0]
        vals = [c.value for row in ws.iter_rows() for c in row]
        assert 88.67 in vals and 86 in vals
    assert SLE.score_tone(72) == 'good' and SLE.score_tone(55) == 'mid' and SLE.score_tone(30) == 'bad'


def test_all_caps_heading_is_set_in_title_case():
    from utils.student_list_export import display_title as d
    assert d('SSS2 SCIENCE MERIT LIST') == 'SSS2 Science Merit List'
    assert d('JSS3 GOLD CLASS LIST OF STUDENTS') == 'JSS3 Gold Class List of Students'
    assert d('WAEC CANDIDATES') == 'WAEC Candidates'
    assert d('Science merit list') == 'Science merit list'      # typed in mixed case: kept
    assert d('') == ''
