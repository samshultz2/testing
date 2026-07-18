"""Decision-support dashboard blocks — Academic Performance (results module) and
Finance Health (finance module) — are registered, permission-gated, and served
only to users who may see the underlying module."""
from flask import session
from models import db, Branch, User
from tests.conftest import login_token


def test_blocks_registered():
    from routes.main import DASHBOARD_BLOCK_IDS, WIDGET_MODULE, DASHBOARD_WIDGETS
    assert 'academic' in DASHBOARD_BLOCK_IDS
    assert 'finance_health' in DASHBOARD_BLOCK_IDS
    assert WIDGET_MODULE['academic'] == 'results'
    assert WIDGET_MODULE['finance_health'] == 'finance'
    keys = {k for k, *_ in DASHBOARD_WIDGETS}
    assert {'academic', 'finance_health'} <= keys


def _staff_with(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name=username)
            u.set_password('secret123')
            u.set_permissions(perms)
            db.session.add(u); db.session.commit()
        return User.query.filter_by(username=username).first().id


def test_permission_gating(app):
    """Academic needs the results module; Finance Health needs the finance module —
    neither leaks to a user without that module."""
    from routes.main import permitted_widgets
    res_id = _staff_with(app, 'ddb_results', {'results': 'view'})
    fin_id = _staff_with(app, 'ddb_finance', {'finance': 'view'})

    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = res_id; session['role'] = 'staff'
        perm = permitted_widgets()
        assert 'academic' in perm
        assert 'finance_health' not in perm

    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = fin_id; session['role'] = 'staff'
        perm = permitted_widgets()
        assert 'finance_health' in perm
        assert 'academic' not in perm


def test_block_permitted_gate(app):
    """The gate the per-widget endpoint uses (_block_permitted) lets a block
    through only for a user permitted its module."""
    from routes.main import _block_permitted
    res_id = _staff_with(app, 'ddb_results2', {'results': 'view'})
    fin_id = _staff_with(app, 'ddb_finance2', {'finance': 'view'})

    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = res_id; session['role'] = 'staff'
        assert _block_permitted('academic') is True
        assert _block_permitted('finance_health') is False

    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = fin_id; session['role'] = 'staff'
        assert _block_permitted('finance_health') is True
        assert _block_permitted('academic') is False


def test_admin_payload_has_block_keys(app):
    """An admin's full dashboard payload carries both new block keys (data may be
    None until there are scores/fees, but the keys are always present)."""
    from routes.main import dashboard_payload
    from config import Config
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    # hit the JSON endpoint the React app uses
    r = c.get('/api/dashboard/data')
    assert r.status_code == 200
    data = r.get_json()
    assert 'academic' in data
    assert 'finance_health' in data


def test_finance_health_shape(app):
    """Finance Health returns a well-formed dict; collection rate is None when no
    fees are expected yet (never a divide-by-zero). Runs inside a request context
    with branch scope set, exactly as the dashboard calls it."""
    from routes.main import _dash_finance_health
    from models import AcademicSession, Term
    from utils.branch_scope import set_session_scope
    from utils.org_scope import set_session_org
    fin_id = _staff_with(app, 'ddb_fin_shape', {'finance': 'view'})
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='FH 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='FH Term', is_active=True))
        db.session.add(term); db.session.commit()
        term_id = term.id
    with app.test_request_context('/'):
        u = db.session.get(User, fin_id)
        session['logged_in'] = True; session['user_id'] = fin_id; session['role'] = 'staff'
        set_session_scope(u); set_session_org(u)
        term = db.session.get(Term, term_id)
        f = _dash_finance_health(term)
        assert f is not None
        assert set(['expected', 'collected', 'outstanding', 'collection_rate',
                    'defaulter_count', 'net', 'trend']) <= set(f)
        assert isinstance(f['trend'], list)


def test_academic_none_without_scores(app):
    """Academic block is None (hidden) until scores exist, so it never renders an
    empty wall of zeros."""
    from routes.main import _dash_academic
    from models import AcademicSession, Term
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='AC 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='AC Term', is_active=True))
        db.session.add(term); db.session.commit()
        # no StudentScore rows seeded -> no assessed students -> None
        assert _dash_academic(term, None) is None
