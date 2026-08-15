"""Per-branch timetable generator: each branch keeps its own teachers, classes,
subjects, rules and results. A branch admin sees and edits only their branch's
generator config and can't reach another branch's rows by guessing an id; a
central admin operates on the branch they're currently viewing.
"""
from config import Config
from tests.conftest import login_token, auth_csrf


def _make_branch_admin(app, branch_name, username):
    from models import db, Branch, User
    b = Branch(name=branch_name, is_default=False)
    db.session.add(b); db.session.flush()
    u = User(username=username, full_name=f'{username} Admin', role='admin',
             scope='branch', branch_id=b.id, rank=50, manage_scope='branch',
             is_active=True, must_change_password=False)
    u.set_password('Str0ng!Passw0rd1')
    db.session.add(u); db.session.commit()
    return b.id, u.id


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'Str0ng!Passw0rd1',
                           '_csrf_token': login_token(c)})
    return c


def _add_teacher(client, name):
    return client.post('/generator/teachers/add',
                       data={'name': name, '_csrf_token': auth_csrf(client)},
                       follow_redirects=False)


def test_generator_config_is_branch_scoped(app):
    from models import db, GenTeacher, User, Branch
    ids = {}
    with app.app_context():
        a_bid, a_uid = _make_branch_admin(app, 'GEN-A', 'gen_admin_a')
        b_bid, b_uid = _make_branch_admin(app, 'GEN-B', 'gen_admin_b')
        ids = dict(a_bid=a_bid, b_bid=b_bid, a_uid=a_uid, b_uid=b_uid)
    try:
        ca = _login(app, 'gen_admin_a')
        cb = _login(app, 'gen_admin_b')

        # Branch A adds a teacher; it is stamped with branch A.
        _add_teacher(ca, 'Alpha Teacher')
        with app.app_context():
            ta = GenTeacher.query.filter_by(name='Alpha Teacher').first()
            assert ta is not None and ta.branch_id == ids['a_bid']
            ids['ta'] = ta.id

        # Branch B adds its own teacher, stamped with branch B.
        _add_teacher(cb, 'Bravo Teacher')
        with app.app_context():
            tb = GenTeacher.query.filter_by(name='Bravo Teacher').first()
            assert tb is not None and tb.branch_id == ids['b_bid']

        # A's list shows only A's teacher; B's list only B's.
        a_html = ca.get('/generator/teachers').get_data(as_text=True)
        b_html = cb.get('/generator/teachers').get_data(as_text=True)
        assert 'Alpha Teacher' in a_html and 'Bravo Teacher' not in a_html
        assert 'Bravo Teacher' in b_html and 'Alpha Teacher' not in b_html

        # B cannot open, edit or delete A's teacher by guessing the id.
        assert cb.get(f'/generator/teachers/{ids["ta"]}').status_code == 403
        assert cb.post(f'/generator/teachers/{ids["ta"]}/update',
                       data={'name': 'hijacked', '_csrf_token': auth_csrf(cb)}).status_code == 403
        assert cb.post(f'/generator/teachers/{ids["ta"]}/delete',
                       data={'_csrf_token': auth_csrf(cb)}).status_code == 403
        with app.app_context():
            assert GenTeacher.query.get(ids['ta']).name == 'Alpha Teacher'  # untouched

        # A central admin viewing branch B sees B's teacher, not A's.
        central = app.test_client()
        central.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                     '_csrf_token': login_token(central)})
        central.get(f'/set-view-branch?branch_id={ids["b_bid"]}')  # legacy alias
        central.get(f'/set-branch?branch_id={ids["b_bid"]}')
        c_html = central.get('/generator/teachers').get_data(as_text=True)
        assert 'Bravo Teacher' in c_html and 'Alpha Teacher' not in c_html
    finally:
        with app.app_context():
            from models import db as _db
            for t in GenTeacher.query.filter(GenTeacher.name.in_(
                    ['Alpha Teacher', 'Bravo Teacher'])).all():
                _db.session.delete(t)
            for uid in (ids['a_uid'], ids['b_uid']):
                u = _db.session.get(User, uid); u and _db.session.delete(u)
            for bid in (ids['a_bid'], ids['b_bid']):
                b = _db.session.get(Branch, bid); b and _db.session.delete(b)
            _db.session.commit()


def test_generator_settings_are_per_branch(app):
    """GenSettings.get/set are scoped to the caller's branch, so two branches
    keep independent generator settings (e.g. the printed school name)."""
    from models import db, GenSettings, Branch, User
    ids = {}
    with app.app_context():
        a_bid, a_uid = _make_branch_admin(app, 'GENSET-A', 'genset_a')
        b_bid, b_uid = _make_branch_admin(app, 'GENSET-B', 'genset_b')
        GenSettings.set('school_name', 'Alpha Campus', branch_id=a_bid)
        GenSettings.set('school_name', 'Bravo Campus', branch_id=b_bid)
        assert GenSettings.get('school_name', branch_id=a_bid) == 'Alpha Campus'
        assert GenSettings.get('school_name', branch_id=b_bid) == 'Bravo Campus'
        ids = dict(a_bid=a_bid, b_bid=b_bid, a_uid=a_uid, b_uid=b_uid)
    try:
        pass
    finally:
        with app.app_context():
            from models import db as _db
            for row in GenSettings.query.filter(GenSettings.branch_id.in_(
                    [ids['a_bid'], ids['b_bid']])).all():
                _db.session.delete(row)
            for uid in (ids['a_uid'], ids['b_uid']):
                u = _db.session.get(User, uid); u and _db.session.delete(u)
            for bid in (ids['a_bid'], ids['b_bid']):
                b = _db.session.get(Branch, bid); b and _db.session.delete(b)
            _db.session.commit()
