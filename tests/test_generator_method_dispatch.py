"""Timetable generation must run the engine the user SELECTED, not the one the
client JS happened to point the form at. Regression for: picking OR-Tools but the
fast method running (when JS didn't swap the form action — stale cache / CSP / error)."""
from config import Config
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c, auth_csrf(c)


def test_fast_endpoint_delegates_to_ortools_when_method_is_ortools(app, monkeypatch):
    import routes.generator.generation as G
    monkeypatch.setattr(G, 'run_ortools_generation', lambda: 'ORTOOLS-RAN')
    c, tok = _admin(app)
    # Post to the FAST endpoint but with method=ortools (what a stale/JS-less page sends).
    r = c.post('/generator/generate/run', data={'method': 'ortools', '_csrf_token': tok})
    assert r.get_data(as_text=True) == 'ORTOOLS-RAN'   # honoured the selection server-side


def test_fast_endpoint_runs_fast_when_method_not_ortools(app, monkeypatch):
    import routes.generator.generation as G
    monkeypatch.setattr(G, 'run_ortools_generation', lambda: 'ORTOOLS-RAN')
    c, tok = _admin(app)
    # method=fast (or absent) must NOT delegate to OR-Tools; with no classes the fast
    # path flashes + redirects to the generate page.
    r = c.post('/generator/generate/run',
               data={'method': 'fast', '_csrf_token': tok}, follow_redirects=False)
    assert r.get_data(as_text=True) != 'ORTOOLS-RAN'
    assert r.status_code in (302, 303)
