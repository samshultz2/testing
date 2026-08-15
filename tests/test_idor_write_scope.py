"""IDOR sweep regression: branch-stamped config/objects reached by a guessed id
on a WRITE endpoint must be branch-scoped. A branch admin manages only their own
branch's WAEC certificate templates, payroll deduction types and CBT attempts;
a central admin manages every branch's. See the guards added in
routes/results/waec_cert.py, routes/hr.py and routes/cbt.py.
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
    client = app.test_client()
    client.post('/login', data={'username': username, 'password': 'Str0ng!Passw0rd1',
                                '_csrf_token': login_token(client)})
    return client


def _central(app):
    client = app.test_client()
    client.post('/login', data={'password': Config.ADMIN_PASSWORD,
                                '_csrf_token': login_token(client)})
    return client


def test_branch_admin_cannot_touch_other_branch_waec_template(app):
    from models import db, WAECCertTemplate, User, Branch
    ids = {}
    with app.app_context():
        a_bid, a_uid = _make_branch_admin(app, 'IDOR-WAEC-A', 'idor_waec_a')
        b_bid, b_uid = _make_branch_admin(app, 'IDOR-WAEC-B', 'idor_waec_b')
        t = WAECCertTemplate(name='B branch cert', base_layout='classic',
                             exam_type='waec', branch_id=b_bid, status='active', version=1)
        db.session.add(t); db.session.commit()
        ids = {'a_uid': a_uid, 'b_uid': b_uid, 'a_bid': a_bid, 'b_bid': b_bid, 't': t.id}
    try:
        c = _login(app, 'idor_waec_a')
        tok = auth_csrf(c)
        base = '/results/waec/certificate/templates'
        # Every mutation on the OTHER branch's template is refused.
        assert c.post(f'{base}/{ids["t"]}/delete', data={'_csrf_token': tok}).status_code == 403
        assert c.post(f'{base}/{ids["t"]}/status', data={'_csrf_token': tok}).status_code == 403
        assert c.post(f'{base}/{ids["t"]}/default', data={'_csrf_token': tok}).status_code == 403
        assert c.post(f'{base}/{ids["t"]}/duplicate', data={'_csrf_token': tok}).status_code == 403
        assert c.post(f'{base}/{ids["t"]}/edit',
                      data={'name': 'hijacked', '_csrf_token': tok}).status_code == 403
        with app.app_context():
            assert db.session.get(WAECCertTemplate, ids['t']).name == 'B branch cert'
        # A central admin still can.
        cen = _central(app)
        ct = auth_csrf(cen)
        assert cen.post(f'{base}/{ids["t"]}/status',
                        data={'_csrf_token': ct}).status_code in (302, 303)
    finally:
        with app.app_context():
            from models import db as _db
            t = _db.session.get(WAECCertTemplate, ids['t'])
            t and _db.session.delete(t)
            for uid in (ids['a_uid'], ids['b_uid']):
                u = _db.session.get(User, uid); u and _db.session.delete(u)
            for bid in (ids['a_bid'], ids['b_bid']):
                b = _db.session.get(Branch, bid); b and _db.session.delete(b)
            _db.session.commit()


def test_branch_admin_cannot_touch_other_branch_deduction_type(app):
    from models import db, PayrollDeductionType, User, Branch
    ids = {}
    with app.app_context():
        a_bid, a_uid = _make_branch_admin(app, 'IDOR-DED-A', 'idor_ded_a')
        b_bid, b_uid = _make_branch_admin(app, 'IDOR-DED-B', 'idor_ded_b')
        d = PayrollDeductionType(name='B Welfare', kind='fixed', value=5000,
                                 is_active=True, branch_id=b_bid)
        db.session.add(d); db.session.commit()
        ids = {'a_uid': a_uid, 'b_uid': b_uid, 'a_bid': a_bid, 'b_bid': b_bid, 'd': d.id}
    try:
        c = _login(app, 'idor_ded_a')
        tok = auth_csrf(c)
        base = '/hr/settings/deductions'
        assert c.post(f'{base}/{ids["d"]}/toggle', data={'_csrf_token': tok}).status_code == 403
        assert c.post(f'{base}/{ids["d"]}/delete', data={'_csrf_token': tok}).status_code == 403
        with app.app_context():
            still = db.session.get(PayrollDeductionType, ids['d'])
            assert still is not None and still.is_active is True   # untouched
    finally:
        with app.app_context():
            from models import db as _db
            d = _db.session.get(PayrollDeductionType, ids['d'])
            d and _db.session.delete(d)
            for uid in (ids['a_uid'], ids['b_uid']):
                u = _db.session.get(User, uid); u and _db.session.delete(u)
            for bid in (ids['a_bid'], ids['b_bid']):
                b = _db.session.get(Branch, bid); b and _db.session.delete(b)
            _db.session.commit()


def test_branch_admin_cannot_force_submit_other_branch_attempt(app):
    from models import db, CBTExam, CBTQuestion, CBTAttempt, Student, User, Branch
    from utils import timeutil
    ids = {}
    with app.app_context():
        a_bid, a_uid = _make_branch_admin(app, 'IDOR-CBT-A', 'idor_cbt_a')
        b_bid, b_uid = _make_branch_admin(app, 'IDOR-CBT-B', 'idor_cbt_b')
        s = Student(student_id='IDORCBT1', first_name='Cee', surname='Bee',
                    gender='Male', is_active=True, branch_id=b_bid)
        db.session.add(s); db.session.flush()
        e = CBTExam(title='B Exam', duration_minutes=30, branch_id=b_bid)
        db.session.add(e); db.session.flush()
        q = CBTQuestion(exam_id=e.id, question_text='q', correct_option='A', marks=1)
        db.session.add(q); db.session.flush()
        att = CBTAttempt(exam_id=e.id, student_id=s.id, status='In progress',
                         started_at=timeutil.now())
        db.session.add(att); db.session.commit()
        ids = {'a_uid': a_uid, 'b_uid': b_uid, 'a_bid': a_bid, 'b_bid': b_bid,
               's': s.id, 'e': e.id, 'q': q.id, 'att': att.id}
    try:
        c = _login(app, 'idor_cbt_a')
        tok = auth_csrf(c)
        r = c.post(f'/cbt/attempts/{ids["att"]}/force-submit',
                   data={'_csrf_token': tok}, headers={'X-Requested-With': 'fetch'})
        assert r.status_code == 403                       # IDOR blocked
        with app.app_context():
            assert db.session.get(CBTAttempt, ids['att']).status == 'In progress'  # untouched
    finally:
        with app.app_context():
            from models import db as _db
            for model, key in ((CBTAttempt, 'att'), (CBTQuestion, 'q'),
                               (CBTExam, 'e'), (Student, 's')):
                o = _db.session.get(model, ids[key]); o and _db.session.delete(o)
            for uid in (ids['a_uid'], ids['b_uid']):
                u = _db.session.get(User, uid); u and _db.session.delete(u)
            for bid in (ids['a_bid'], ids['b_bid']):
                b = _db.session.get(Branch, bid); b and _db.session.delete(b)
            _db.session.commit()
