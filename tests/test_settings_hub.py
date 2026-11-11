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
        old_end = t.end_date
        t.end_date = date(2098, 7, 20)
        sess = AcademicSession(name='2098/2099 hubtest')
        db.session.add(sess); db.session.flush()
        nxt = Term(name='First Term', term_number=1, session_id=sess.id,
                   start_date=date(2098, 9, 14), end_date=date(2098, 12, 15))
        db.session.add(nxt); db.session.commit()
        ids = (t.id, sess.id, nxt.id)
    try:
        client = _admin(app)
        d = _json(client, '/settings/school')
        assert d['next_term'] and d['next_term']['begins'] == '14 September 2098'
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Term, ids[2]))
            db.session.delete(db.session.get(AcademicSession, ids[1]))
            db.session.get(Term, ids[0]).end_date = old_end
            db.session.commit()

def test_academic_page_has_decision_context(app):
    client = _admin(app)
    d = _json(client, '/settings/academic')
    assert {'branches', 'latest_id', 'arms_in_use', 'slots', 'urls'} <= set(d)
    assert d['urls']['slots']


def test_decimal_totals_between_whole_number_bands_get_the_lower_band(app):
    from types import SimpleNamespace as B
    from models import GradeScale
    from utils.results_analytics_org import _grade_for
    bands = [B(grade='A', min_score=70, max_score=100), B(grade='B', min_score=60, max_score=69),
             B(grade='F', min_score=0, max_score=49)]
    assert GradeScale.band_for(69.5, bands).grade == 'B'
    assert GradeScale.band_for(70, bands).grade == 'A'
    assert GradeScale.band_for(49.9, bands).grade == 'F'
    assert GradeScale.band_for(55, bands) is None          # a real gap stays ungraded
    tup = [(b.grade, b.min_score, b.max_score) for b in bands]
    assert _grade_for(69.5, tup) == 'B' and _grade_for(55, tup) == 'F'


def test_grades_page_has_score_spread(app):
    client = _admin(app)
    d = _json(client, '/settings/grades')
    assert 'spread' in d and 'pass_mark' in d


def test_renaming_an_assessment_keeps_its_row(app):
    from models import db, AssessmentType
    with app.app_context():
        types = AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order).all()
        snap = [(t.id, t.name, t.short_name, t.max_score) for t in types]
    client = _admin(app)
    d = _json(client, '/settings/assessments')
    assert {'marks', 'term_custom', 'subject_overrides'} <= set(d)
    first = snap[0]
    form = {'id[]': [str(x[0]) for x in snap], 'name[]': [first[1] + ' renamed'] + [x[1] for x in snap[1:]],
            'short_name[]': [x[2] or '' for x in snap], 'max_score[]': [str(x[3]) for x in snap],
            '_csrf_token': _ptoken(client)}
    r = client.post('/settings/assessments/save', data=form, headers={'X-Requested-With': 'fetch'})
    assert r.status_code in (200, 302)
    try:
        with app.app_context():
            assert db.session.get(AssessmentType, first[0]).name == first[1] + ' renamed'
            assert db.session.get(AssessmentType, first[0]).is_active
    finally:
        with app.app_context():
            db.session.get(AssessmentType, first[0]).name = first[1]
            db.session.commit()
