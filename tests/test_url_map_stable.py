"""Safety net for the monolith-splitting refactor: the full set of URL rules
(endpoint, path, methods) must stay byte-identical. This catches any route that a
file split accidentally drops, renames, duplicates, or whose methods change — the
key guard for the untested generator blueprint.

If you intentionally add/remove a route, regenerate the snapshot:
    python -c "import json; from app import create_app; a=create_app(); \
      rows=sorted([r.endpoint, str(r.rule), sorted(m for m in r.methods if m not in ('HEAD','OPTIONS'))] \
      for r in a.url_map.iter_rules()); json.dump(rows, open('tests/url_map_snapshot.json','w'), indent=0)"
"""
import json
import os


def _current(app):
    rows = []
    for r in app.url_map.iter_rules():
        methods = sorted(m for m in r.methods if m not in ('HEAD', 'OPTIONS'))
        rows.append([r.endpoint, str(r.rule), methods])
    rows.sort()
    return rows


def test_url_map_matches_snapshot(app):
    snap_path = os.path.join(os.path.dirname(__file__), 'url_map_snapshot.json')
    expected = json.load(open(snap_path))
    actual = _current(app)

    exp_eps = {tuple([r[0], r[1]]) for r in expected}
    act_eps = {tuple([r[0], r[1]]) for r in actual}
    missing = exp_eps - act_eps
    added = act_eps - exp_eps
    assert not missing, f'routes disappeared after refactor: {sorted(missing)[:10]}'
    assert not added, f'unexpected new routes: {sorted(added)[:10]}'
    # also assert methods are unchanged
    assert actual == expected, 'a route\'s methods changed vs the snapshot'
