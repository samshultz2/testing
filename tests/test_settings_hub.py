"""Settings hub health strip, branch counts, audit summary, error-log clear, share links."""
from tests.test_settings_react import _admin, _ptoken

JSON = {'Accept': 'application/json'}


def _json(client, url):
    r = client.get(url, headers=JSON)
    assert r.status_code == 200, url
    return r.get_json()


def test_settings_index_has_health_and_links(app):
    client = _admin(app)
    d = _json(client, '/settings/')
    assert 'health' in d and 'errors_24h' in d['health']
    assert d['urls']['error_log'] == '/error-log'
    assert d['urls']['share'] == '/share'


def test_branches_carry_counts(app):
    from models import db, Branch
    with app.app_context():
        if not Branch.query.filter_by(name='HubCountBr').first():
            db.session.add(Branch(name='HubCountBr', code='HCB', is_active=True))
            db.session.commit()
    client = _admin(app)
    d = _json(client, '/settings/branches')
    b = next(x for x in d['branches'] if x['name'] == 'HubCountBr')
    assert {'students', 'staff', 'classes'} <= set(b)
    assert 'unassigned' in d


def test_audit_has_day_groups_and_stats(app):
    client = _admin(app)
    d = _json(client, '/settings/audit')
    assert {'today', 'week', 'people', 'risky', 'week_iso'} <= set(d['stats'])
    for l in d['logs']:
        assert l['day'] and l['time']
    # The classic /audit url shows the same screen.
    assert '"page": "audit"' in client.get('/audit').get_data(as_text=True)


def test_error_log_groups_repeats_and_clears(app):
    from utils.error_tracking import record_error, clear_errors, recent_errors
    with app.app_context():
        clear_errors()
        for _ in range(3):
            record_error('client', 'HubRepeatErr', where='/x', user='u1')
    client = _admin(app)
    html = client.get('/error-log').get_data(as_text=True)
    assert 'HubRepeatErr' in html and '×3' in html
    assert html.count('data-message="HubRepeatErr"') == 1
    r = client.post('/error-log/clear', data={'_csrf_token': _ptoken(client)})
    assert r.status_code in (302, 303)
    with app.app_context():
        assert not any(e['message'] == 'HubRepeatErr' for e in recent_errors(200))


def test_share_lists_portal_links(app):
    client = _admin(app)
    html = client.get('/share').get_data(as_text=True)
    assert 'Direct links' in html and '/parent/login' in html


def test_school_page_suggests_next_term_start(app):
    from datetime import date
    from models import db, Term, AcademicSession
    from utils.helpers import get_active_term
    with app.app_context():
        t = get_active_term()
        if not t:
            return
        if not t.end_date:
            t.end_date = date(2031, 7, 20)
        sess = AcademicSession.query.filter_by(name='2099/2100').first()
        if not sess:
            sess = AcademicSession(name='2099/2100')
            db.session.add(sess); db.session.flush()
            db.session.add(Term(name='First Term', session_id=sess.id, start_date=date(2099, 9, 14), end_date=date(2099, 12, 15)))
        db.session.commit()
        expected = Term.query.filter(Term.start_date > t.end_date).order_by(Term.start_date).first()
    client = _admin(app)
    d = _json(client, '/settings/school')
    assert d['next_term'] and d['next_term']['begins'] == f"{expected.start_date.day} {expected.start_date.strftime('%B %Y')}"
