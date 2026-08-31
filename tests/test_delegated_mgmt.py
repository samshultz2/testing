"""Delegated user management: managers edit lower-ranked users in their branch."""
from config import Config
from models import db, Branch, User
from tests.conftest import login_token


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _mk(app, username, **kw):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, full_name=username, **kw)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
            return u.id
        return User.query.filter_by(username=username).first().id


def _ids(app):
    with app.app_context():
        b = Branch.query.filter_by(name='DelB').first() or Branch(name='DelB', is_active=True)
        if b.id is None:
            db.session.add(b); db.session.commit()
        bid = b.id
        adef = Branch.get_default().id
    princ = _mk(app, 'dm_princ', role='staff', scope='branch', branch_id=bid,
                rank=60, manage_scope='branch')
    princ2 = _mk(app, 'dm_princ2', role='staff', scope='branch', branch_id=bid,
                 rank=60, manage_scope='branch')
    tch = _mk(app, 'dm_tch', role='teacher', scope='branch', branch_id=bid,
              rank=10, manage_scope='none')
    tcha = _mk(app, 'dm_tcha', role='teacher', scope='branch', branch_id=adef,
               rank=10, manage_scope='none')
    return dict(bid=bid, princ=princ, princ2=princ2, tch=tch, tcha=tcha)


def test_non_manager_cannot_open_users(app):
    _ids(app)
    c = _login(app, 'dm_tch')
    r = c.get('/users/', follow_redirects=False)
    assert r.status_code in (302, 303)


def test_principal_manages_lower_rank_same_branch_only(app):
    ids = _ids(app)
    c = _login(app, 'dm_princ')
    assert c.get('/users/').status_code == 200
    # can view a lower-ranked teacher in their branch
    assert c.get(f'/users/{ids["tch"]}').status_code == 200
    # cannot view a teacher in another branch
    assert c.get(f'/users/{ids["tcha"]}', follow_redirects=False).status_code in (302, 303)
    # cannot manage an equal-ranked principal
    assert c.get(f'/users/{ids["princ2"]}', follow_redirects=False).status_code in (302, 303)
    # cannot manage self
    assert c.get(f'/users/{ids["princ"]}', follow_redirects=False).status_code in (302, 303)


def test_principal_user_list_is_filtered(app):
    ids = _ids(app)
    c = _login(app, 'dm_princ')
    html = c.get('/users/').get_data(as_text=True)
    assert 'dm_tch' in html          # manageable
    assert 'dm_tcha' not in html     # other branch
    assert 'dm_princ2' not in html   # equal rank


def test_central_admin_manages_principal(app):
    ids = _ids(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    assert c.get(f'/users/{ids["princ"]}').status_code == 200
