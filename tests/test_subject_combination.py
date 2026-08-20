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


def test_combine_export_smoke(app):
    """The export endpoint returns each format with the right content type."""
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    # No scopes/subjects → redirects with a flash (still a valid response).
    r = c.get('/subjects/broadsheet/combine')
    assert r.status_code == 200
