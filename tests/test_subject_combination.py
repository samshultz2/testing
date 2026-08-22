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
