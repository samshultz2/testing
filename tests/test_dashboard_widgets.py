"""Dashboard widget selection persists and renders."""
import re
from models import db, User
from tests.conftest import login_token


def test_customize_saves_user_prefs(app):
    with app.app_context():
        if not User.query.filter_by(username='dashuser').first():
            u = User(username='dashuser', role='staff', scope='central', full_name='Dash')
            u.set_password('secret123'); db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': 'dashuser', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    assert c.get('/').status_code == 200
    assert c.get('/dashboard/customize').status_code == 200
    pt = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                   c.get('/').get_data(as_text=True)).group(1)
    c.post('/dashboard/customize', data={'_csrf_token': pt, 'w_kpi': 'on', 'w_finance': 'on'},
           follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(username='dashuser').first()
        assert u.dashboard_widgets == ['kpi', 'finance']   # registry order
    assert c.get('/').status_code == 200
