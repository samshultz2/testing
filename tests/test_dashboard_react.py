"""The React dashboard: inline-hydrated shell + /api/dashboard/data payload,
scoped so a user never receives data for a module they can't access."""
import json
from config import Config
from models import db, Branch, User
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def test_dashboard_shell_hydrates_react(app):
    c = _admin(app)
    html = c.get('/').get_data(as_text=True)
    assert 'id="dashboard-app"' in html              # React mount point
    assert 'id="dash-data"' in html                  # inline payload
    assert 'js/react/dashboard-app.js' in html       # bundle


def test_dashboard_api_payload_keys(app):
    c = _admin(app)
    r = c.get('/api/dashboard/data')
    assert r.status_code == 200
    j = r.get_json()
    for k in ('enabled', 'permitted', 'urls', 'total_students', 'attendance_stats',
              'class_stats', 'age_distribution', 'religion_stats', 'stream_dist'):
        assert k in j
    assert isinstance(j['enabled'], list) and isinstance(j['urls'], dict)
    assert 'customize' in j['urls']


def test_dashboard_api_hides_unpermitted_modules(app):
    with app.app_context():
        if not User.query.filter_by(username='dre_staff').first():
            u = User(username='dre_staff', role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name='Dre Staff')
            u.set_password('Secret123')
            u.set_permissions({'students': 'edit'})   # no finance / hr
            db.session.add(u); db.session.commit()
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'username': 'dre_staff', 'password': 'Secret123', '_csrf_token': tok})
    j = c.get('/api/dashboard/data').get_json()
    assert 'finance' not in j['enabled'] and 'finance' not in j['permitted']
    assert j['finance_stat'] is None and j['hr_stat'] is None
    assert 'kpi' in j['permitted']                    # students access retained
