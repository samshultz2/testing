"""Phase 2b: every remaining coarse module is now sliced into sub-sections.

Two guarantees are locked in here:

1. Catalog integrity — every endpoint referenced by a sub-section is a REAL
   endpoint in the app's URL map (guards against typos/renames silently
   dropping a route back to whole-module access), and a representative sample
   resolves to the expected (module, sub-section).
2. A couple of live HTTP partition checks — a user granted one slice of a
   module cannot use another slice, and slices layered on top of a stricter
   guard (settings backup = central-admin) stay locked.
"""
import re

from config import Config
from models import db, User
from utils.access_control import (_ENDPOINT_SUBSECTION, subsection_for_endpoint,
                                   MODULE_SUBSECTIONS, CAPABILITY_SUBSECTIONS)
from tests.conftest import login_token


def _make_user(app, username, perms):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='staff', full_name=username.title())
            u.set_password('secret123')
            db.session.add(u)
        u.set_permissions(perms)
        db.session.commit()


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


# --- catalog integrity -----------------------------------------------------
def test_every_mapped_endpoint_is_real(app):
    real = {r.endpoint for r in app.url_map.iter_rules()}
    missing = sorted(k for k in _ENDPOINT_SUBSECTION if k not in real)
    assert missing == [], f'sub-section endpoints not in url_map: {missing}'


def test_representative_resolution():
    cases = {
        'academics.add_session': ('academics', 'structure'),
        'academics.enroll_student': ('academics', 'enrollment'),
        'subjects.save_scores': ('results', 'scores'),
        'subjects.subjects_list': ('results', 'subjects'),
        'subjects.broadsheet': ('results', 'analytics'),
        'cbt.bank': ('cbt', 'bank'),
        'cbt.monitor': ('cbt', 'monitor'),
        'timetable.designer': ('timetable', 'manage'),
        'timetable.my_timetable': ('timetable', 'view'),
        'promotion.graduate_document': ('promotion', 'documents'),
        'library.issue': ('library', 'circulation'),
        'library.add_book': ('library', 'catalogue'),
        'reports.export_students': ('reports', 'exports'),
        'events.add_event': ('events', 'manage'),
        'contributions.add_payment': ('contributions', 'record'),
        'website_admin.media_upload': ('website', 'media'),
        'settings.save_grades': ('settings', 'grading'),
        'settings.backup_page': ('settings', 'backup'),
    }
    for ep, expected in cases.items():
        assert subsection_for_endpoint(ep) == expected, ep


def test_graduate_bypass_endpoints_not_subsectioned():
    # These retain their dedicated graduate-viewer bypass; double-gating would
    # break it, so they must NOT be mapped to a promotion sub-section.
    for ep in ('promotion.graduates_list', 'promotion.graduate_profile',
               'promotion.graduate_compare'):
        assert subsection_for_endpoint(ep) is None, ep


def test_capabilities_are_not_in_reverse_map():
    # results.cards / timetable.generate stay explicit capabilities: no endpoint
    # is ever wired to them (granting one must not unlock via the reverse map).
    mapped = {f'{m}.{s}' for m, s in _ENDPOINT_SUBSECTION.values()}
    for cap in CAPABILITY_SUBSECTIONS:
        assert cap not in mapped, cap
    # every module that declares sub-sections appears in the catalog
    for mod in ('academics', 'results', 'cbt', 'timetable', 'promotion', 'library',
                'reports', 'events', 'contributions', 'website', 'settings'):
        assert mod in MODULE_SUBSECTIONS and MODULE_SUBSECTIONS[mod]


# --- live partition checks -------------------------------------------------
def test_library_catalogue_vs_circulation(app):
    _make_user(app, 'lib_cat', {'library.catalogue': 'edit'})
    _make_user(app, 'lib_circ', {'library.circulation': 'edit'})
    c1 = _login(app, 'lib_cat')
    assert c1.get('/library/books').status_code == 200
    assert c1.get('/library/loans', follow_redirects=False).status_code in (302, 303)
    c2 = _login(app, 'lib_circ')
    assert c2.get('/library/loans').status_code == 200
    assert c2.get('/library/books', follow_redirects=False).status_code in (302, 303)


def test_settings_grading_slice_cannot_reach_backup(app):
    """A delegated settings.grading user edits grades but the backup slice stays
    central-admin only."""
    _make_user(app, 'set_grade', {'settings.grading': 'edit'})
    c = _login(app, 'set_grade')
    assert c.get('/settings/grades').status_code == 200
    assert c.get('/settings/backup', follow_redirects=False).status_code in (302, 303)


def test_whole_module_grant_still_passes_all_slices(app):
    _make_user(app, 'lib_full', {'library': 'edit'})
    c = _login(app, 'lib_full')
    assert c.get('/library/books').status_code == 200
    assert c.get('/library/loans').status_code == 200


def test_admin_unaffected(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    assert client.get('/library/books').status_code == 200
    assert client.get('/library/loans').status_code == 200
    assert client.get('/settings/grades').status_code == 200
