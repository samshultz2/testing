"""Dashboard personalization — drag-order, favourites and per-widget refresh,
all permission-scoped.
"""
import json
from config import Config
from models import db, User, Branch
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def _students_only(app, username='dp_staff'):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name='DP Staff')
            u.set_password('secret123')
            u.set_permissions({'students': 'edit'})
            db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def test_order_and_favorites_persist(app):
    c = _admin(app); token = _csrf(c)
    r = c.post('/api/dashboard/widgets',
               data=json.dumps({'order': ['people', 'kpi', 'insights'],
                                'favorites': ['kpi']}),
               content_type='application/json',
               headers={'X-Requested-With': 'fetch', 'X-CSRFToken': token})
    assert r.status_code == 200, r.get_data(as_text=True)
    layout = r.get_json()['layout']
    # Requested order comes first; the rest are appended in canonical order.
    assert layout['order'][:3] == ['people', 'kpi', 'insights']
    assert set(layout['order']) == set(layout['blocks'])
    assert layout['favorites'] == ['kpi']
    # And it round-trips on the next dashboard load.
    j = c.get('/api/dashboard/data').get_json()
    assert j['layout']['order'][:3] == ['people', 'kpi', 'insights']
    assert j['layout']['favorites'] == ['kpi']


def test_partial_save_leaves_other_fields(app):
    c = _admin(app); token = _csrf(c)
    hdr = {'X-Requested-With': 'fetch', 'X-CSRFToken': token}
    c.post('/api/dashboard/widgets', data=json.dumps({'favorites': ['insights']}),
           content_type='application/json', headers=hdr)
    # A later order-only save must not wipe the favourites.
    c.post('/api/dashboard/widgets', data=json.dumps({'order': ['insights', 'kpi']}),
           content_type='application/json', headers=hdr)
    j = c.get('/api/dashboard/data').get_json()
    assert j['layout']['favorites'] == ['insights']
    assert j['layout']['order'][0] == 'insights'


def test_unknown_blocks_sanitised(app):
    c = _admin(app); token = _csrf(c)
    r = c.post('/api/dashboard/widgets',
               data=json.dumps({'order': ['kpi', 'bogus', 'people'],
                                'favorites': ['nope']}),
               content_type='application/json',
               headers={'X-Requested-With': 'fetch', 'X-CSRFToken': token})
    layout = r.get_json()['layout']
    assert 'bogus' not in layout['order']
    assert layout['favorites'] == []   # unknown favourite dropped


def test_widget_endpoint_returns_slice(app):
    c = _admin(app)
    j = c.get('/api/dashboard/widget/kpi').get_json()
    assert 'total_students' in j and 'attendance_stats' in j
    j = c.get('/api/dashboard/widget/insights').get_json()
    assert 'insights' in j and isinstance(j['insights'], list)


def test_widget_endpoint_permission_scoped(app):
    c = _students_only(app)
    # A students-only user may refresh a students block…
    assert c.get('/api/dashboard/widget/kpi').status_code == 200
    # …but not a cross-module KPI block (no finance/sales/hr/cbt/library)…
    assert c.get('/api/dashboard/widget/crossmodule').status_code == 403
    # …nor the central-only branch block…
    assert c.get('/api/dashboard/widget/branches').status_code == 403
    # …and an unknown block is a 404.
    assert c.get('/api/dashboard/widget/bogus').status_code == 404


def test_favorite_permission_scoped(app):
    """A user can't favourite a block they may not see — it's filtered on save."""
    c = _students_only(app, username='dp_staff2'); token = _csrf(c)
    r = c.post('/api/dashboard/widgets',
               data=json.dumps({'favorites': ['kpi', 'crossmodule', 'branches']}),
               content_type='application/json',
               headers={'X-Requested-With': 'fetch', 'X-CSRFToken': token})
    fav = r.get_json()['layout']['favorites']
    assert 'kpi' in fav and 'crossmodule' not in fav and 'branches' not in fav


def test_legacy_list_prefs_still_read(app):
    """Rows saved in the old list shape keep working as the enabled set."""
    with app.app_context():
        u = User(username='dp_legacy', role='staff', scope='central', full_name='Legacy')
        u.set_password('secret123')
        u.dashboard_prefs = json.dumps(['kpi', 'finance'])   # legacy bare list
        db.session.add(u); db.session.commit()
        assert u.dashboard_widgets == ['kpi', 'finance']
        assert u.dashboard_order is None and u.dashboard_favorites is None
        # Setting a layout preserves the legacy enabled list.
        u.set_dashboard_layout(order=['kpi'])
        db.session.commit()
        assert u.dashboard_widgets == ['kpi', 'finance']
        assert u.dashboard_order == ['kpi']
