"""Dashboard Phase 1 — the Needs-Attention insights panel.

The panel is a cross-module widget: always permitted, its items self-filter by
module permission and are sorted by severity. Signals are best-effort.
"""
from config import Config
from flask import session
from models import db, Branch, Student, User
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD,
                           '_csrf_token': login_token(c)})
    return c


def test_insights_widget_always_permitted(app):
    """Even a students-only staffer may see the panel (its items self-filter)."""
    with app.app_context():
        if not User.query.filter_by(username='ins_staff').first():
            u = User(username='ins_staff', role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name='Ins Staff')
            u.set_password('secret123')
            u.set_permissions({'students': 'edit'})
            db.session.add(u); db.session.commit()
        uid = User.query.filter_by(username='ins_staff').first().id
    from routes.main import permitted_widgets, enabled_widgets
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['user_id'] = uid
        session['role'] = 'staff'
        assert 'insights' in permitted_widgets()
        assert 'insights' in enabled_widgets()   # default-on


def test_payload_exposes_insights_list(app):
    c = _admin(app)
    j = c.get('/api/dashboard/data').get_json()
    assert 'insights' in j and isinstance(j['insights'], list)
    assert any(w['key'] == 'insights' for w in j['widget_catalog'])
    assert 'insights' in j['permitted']


def test_incomplete_profile_surfaces(app):
    """A student with no DOB and no parent contact is flagged as incomplete."""
    c = _admin(app)
    with app.app_context():
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_INS_INC', first_name='No', surname='ZzInsInc',
                    gender='Male', is_active=True, branch_id=bid, date_of_birth=None)
        db.session.add(s); db.session.commit()
    j = c.get('/api/dashboard/data').get_json()
    keys = {it['key'] for it in j['insights']}
    assert 'incomplete' in keys
    inc = next(it for it in j['insights'] if it['key'] == 'incomplete')
    assert inc['severity'] == 'low' and inc['url']


def test_open_intervention_surfaces_high(app):
    c = _admin(app)
    with app.app_context():
        from models.models_attendance_intervention import AttendanceIntervention
        bid = Branch.get_default().id
        s = Student(student_id='ZZ_INS_IV', first_name='Iv', surname='ZzInsIv',
                    gender='Female', is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(AttendanceIntervention(student_id=s.id, reason='Low attendance',
                                              status='Open'))
        db.session.commit()
    j = c.get('/api/dashboard/data').get_json()
    iv = [it for it in j['insights'] if it['key'] == 'interventions']
    assert iv and iv[0]['severity'] == 'high'
    # High-severity items sort ahead of low-severity ones.
    order = [it['severity'] for it in j['insights']]
    assert order == sorted(order, key=lambda s: {'high': 0, 'medium': 1, 'low': 2}[s])


def test_insight_items_carry_action_key(app):
    """Every insight item exposes an `action` field (None unless it has a CTA),
    so the React panel can render the optional button without a key error."""
    c = _admin(app)
    j = c.get('/api/dashboard/data').get_json()
    for it in j['insights']:
        assert 'action' in it


def test_defaulters_summary_edges(app):
    from utils.finance import defaulters_summary
    with app.app_context():
        # No term short-circuits before any scoped query.
        assert defaulters_summary(None) == {'count': 0, 'balance': 0.0}
    # A term with no enrolments has no defaulters (needs a request/session ctx
    # for branch scoping).
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'admin'
        assert defaulters_summary(999999) == {'count': 0, 'balance': 0.0}
