"""Admin can delete users (hard) and staff (hard when clean, else deactivate)."""
from config import Config
from models import db, User, StaffMember, Branch, Payslip, PayrollRun
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_users_list_exposes_delete(app):
    with app.app_context():
        u = User.query.filter_by(username='del_target').first()
        if not u:
            u = User(username='del_target', full_name='Del Target', role='staff')
            u.set_password('CorrectHorse9'); db.session.add(u); db.session.commit()
    c = _admin(app)
    # The SPA fetches its screen data as JSON (X-Requested-With: fetch).
    data = c.get('/users/', headers={'X-Requested-With': 'fetch'}).get_json()
    row = next(r for r in data['users'] if r['username'] == 'del_target')
    assert row['delete_url'] and row['can_delete'] is True


def test_delete_user_hard_removes(app):
    with app.app_context():
        u = User(username='del_me', full_name='Del Me', role='staff')
        u.set_password('CorrectHorse9'); db.session.add(u); db.session.commit()
        uid = u.id
    c = _admin(app)
    c.post(f'/users/{uid}/delete', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(User, uid) is None


def test_delete_staff_hard_when_clean(app):
    with app.app_context():
        bid = Branch.get_default().id
        s = StaffMember(first_name='Clean', surname='Slate', is_active=True,
                        status='Active', staff_type='Teaching', branch_id=bid)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    c.post(f'/hr/staff/{sid}/delete', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(StaffMember, sid) is None      # genuinely removed


def test_delete_staff_with_history_deactivates(app):
    with app.app_context():
        bid = Branch.get_default().id
        s = StaffMember(first_name='Has', surname='History', is_active=True,
                        status='Active', staff_type='Teaching', branch_id=bid)
        db.session.add(s); db.session.flush()
        run = PayrollRun(year=2025, month=4, branch_id=bid, status='Finalized')
        db.session.add(run); db.session.flush()
        db.session.add(Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name,
                               basic=1000, net=1000))
        db.session.commit()
        sid = s.id
    c = _admin(app)
    c.post(f'/hr/staff/{sid}/delete', data={'_csrf_token': auth_csrf(c)}, follow_redirects=True)
    with app.app_context():
        s2 = db.session.get(StaffMember, sid)
        assert s2 is not None and s2.is_active is False       # kept, deactivated
