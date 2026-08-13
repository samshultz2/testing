"""Staff-change notifications carry detail (whose record, what changed, who did
it), and every module's admin notification auto-carries the acting user via the
central actor stamp."""
from models import db, User, StaffMember
from utils import notify as notify_mod


def _acting_user(username='mrsbello', full_name='Mrs Bello'):
    u = User(username=username, full_name=full_name, role='admin', is_active=True)
    u.set_password('secret123')
    db.session.add(u); db.session.commit()
    return u


def test_staff_update_notification_has_who_what_and_actor(app):
    with app.test_request_context('/'):
        from flask import session
        u = _acting_user()
        session['user_id'] = u.id
        s = StaffMember(staff_id='STF-1', first_name='Musa', surname='Bello',
                        designation='Teacher', status='Active')
        db.session.add(s); db.session.commit()
        n = notify_mod.notify_staff_change(
            'update', staff=s,
            changes='Designation: "Teacher" → "HOD"',
            actor=notify_mod.actor_label(), url='/hr/x')
        assert n is not None
        assert n.title == 'Staff updated'
        assert s.full_name in n.body and '(STF-1)' in n.body
        assert 'Designation: "Teacher" → "HOD"' in n.body
        assert 'by Mrs Bello' in n.body


def test_notify_admins_auto_stamps_actor(app):
    """A plain module notification (no explicit actor) still says who did it."""
    with app.test_request_context('/'):
        from flask import session
        u = _acting_user(username='mradebayo', full_name='Mr Adebayo')
        session['user_id'] = u.id
        n = notify_mod.notify_admins('Fee recorded', body='₦20,000 · School fees')
        assert n is not None
        assert '· by Mr Adebayo' in n.body


def test_actor_stamp_not_doubled(app):
    """A body already carrying an attribution isn't stamped twice."""
    with app.test_request_context('/'):
        from flask import session
        u = _acting_user(username='mrsokafor', full_name='Mrs Okafor')
        session['user_id'] = u.id
        n = notify_mod.notify_admins('X', body='something happened · by Mrs Okafor')
        assert n is not None
        assert n.body.count('· by ') == 1


def test_background_job_notification_has_no_actor(app):
    """No user in context (a scheduled tick) leaves the body unstamped."""
    with app.app_context():
        n = notify_mod.notify_admins('Nightly summary', body='3 books overdue')
        assert n is not None
        assert '· by ' not in n.body
