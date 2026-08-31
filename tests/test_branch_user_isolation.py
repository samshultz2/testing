"""A branch-scoped user must never manage accounts in another branch — even if
their stored manage_scope is wrongly 'central'."""
from models import db, Branch, User
from tests.conftest import login_token


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _mk(app, username, **kw):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username, **kw)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
            return u.id
        return u.id


def _ids(app):
    with app.app_context():
        b = Branch.query.filter_by(name='IsoB').first()
        if not b:
            b = Branch(name='IsoB', is_active=True)
            db.session.add(b); db.session.commit()
        bid = b.id
        adef = Branch.get_default().id
    # Branch-scoped user but with a WRONG manage_scope='central'.
    rogue = _mk(app, 'iso_rogue', role='admin', scope='branch', branch_id=bid,
                rank=60, manage_scope='central')
    other = _mk(app, 'iso_other', role='teacher', scope='branch', branch_id=adef,
                rank=10, manage_scope='none')
    return dict(rogue=rogue, other=other)


def test_branch_user_with_central_manage_scope_cannot_cross_branch(app):
    ids = _ids(app)
    c = _login(app, 'iso_rogue')
    # may reach the users area (it manages its own branch) ...
    assert c.get('/users/').status_code == 200
    # ... but must NOT view or edit a user in another branch.
    assert c.get(f'/users/{ids["other"]}', follow_redirects=False).status_code in (302, 303)
    assert c.get(f'/users/{ids["other"]}/edit', follow_redirects=False).status_code in (302, 303)
