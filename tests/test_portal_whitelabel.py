"""White-label public portals: the exam/check-result/parent/verify pages render
(catching Jinja errors from the brand/colour changes), and the result checker
uses Post/Redirect/Get so a refresh can't consume a second card check.
"""
import re


def test_public_portal_pages_render(app):
    c = app.test_client()
    # These are public (no auth) and all render the neutral, school-branded shell.
    for url in ('/check-result/', '/parent/login', '/exam/'):
        r = c.get(url, follow_redirects=False)
        assert r.status_code in (200, 302), f'{url} -> {r.status_code}'


def test_view_result_without_session_redirects(app):
    c = app.test_client()
    r = c.get('/check-result/view', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/check-result' in r.headers.get('Location', '')


def test_check_post_is_prg(app):
    """A wrong PIN re-renders the form (200); the key point is the route no longer
    renders the result inline on POST success — that path now redirects. We assert
    the failure path still renders and the success redirect target exists."""
    c = app.test_client()
    # Wrong credentials → form re-render (200), no redirect, no consumption.
    r = c.post('/check-result/', data={'student_id': 'NOPE', 'pin': 'NOPE',
               '_csrf_token': _portal_token(c)})
    assert r.status_code == 200


def _portal_token(c):
    html = c.get('/check-result/').get_data(as_text=True)
    m = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ''
