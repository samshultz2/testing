"""Red-team regression: payroll is per-branch — a branch admin manages only
their own branch's runs/payslips, a central admin manages every branch's, and no
branch admin can read or tamper with another branch's payroll by guessing a
run/slip id. Also covers the assign-class branch guard."""
from config import Config
from tests.conftest import login_token, auth_csrf


def _make_branch_admin(app, branch_name, username):
    """Create a branch (non-default) + a branch-scoped admin in it. Returns
    (branch_id, user_id). Password is 'Str0ng!Passw0rd1'."""
    from models import db, Branch, User
    b = Branch(name=branch_name, is_default=False)
    db.session.add(b)
    db.session.flush()
    u = User(username=username, full_name=f'{username} Admin', role='admin',
             scope='branch', branch_id=b.id, rank=50, manage_scope='branch',
             is_active=True, must_change_password=False)
    u.set_password('Str0ng!Passw0rd1')
    db.session.add(u)
    db.session.commit()
    return b.id, u.id


def _login(app, username, password):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _mk_run(branch_id, year, month, salary):
    """A per-branch payroll run with one payslip for a staff member in that
    branch. Returns (run_id, slip_id, staff_id)."""
    from models import db, StaffMember, PayrollRun, Payslip
    s = StaffMember(staff_id=StaffMember.generate_staff_id(), first_name='Pay',
                    surname='Target', branch_id=branch_id, salary=salary,
                    is_active=True, status='Active')
    db.session.add(s); db.session.flush()
    run = PayrollRun(year=year, month=month, status='Draft', branch_id=branch_id)
    db.session.add(run); db.session.flush()
    ps = Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name,
                 basic=salary, allowances=0, deductions=0)
    db.session.add(ps); db.session.commit()
    return run.id, ps.id, s.id


def test_branch_admin_payroll_is_scoped_to_own_branch(app):
    """A branch admin runs their OWN branch's payroll but cannot read or tamper
    with another branch's; a central admin sees both."""
    from models import db
    c = {}
    with app.app_context():
        a_bid, a_uid = _make_branch_admin(app, 'PR-Branch-A', 'pr_admin_a')
        b_bid, _ = _make_branch_admin(app, 'PR-Branch-B', 'pr_owner_b')
        a_run, a_slip, a_staff = _mk_run(a_bid, 2099, 6, 100000)   # admin A's own
        b_run, b_slip, b_staff = _mk_run(b_bid, 2099, 6, 200000)   # the other branch
        c = {'a_bid': a_bid, 'b_bid': b_bid, 'a_uid': a_uid,
             'owner_b': __import__('models').User.query.filter_by(username='pr_owner_b').first().id,
             'a_run': a_run, 'a_slip': a_slip, 'a_staff': a_staff,
             'b_run': b_run, 'b_slip': b_slip, 'b_staff': b_staff}

    try:
        client = _login(app, 'pr_admin_a', 'Str0ng!Passw0rd1')
        assert client.get('/hr/').status_code == 200          # logged in

        # OWN branch: allowed.
        assert client.get('/hr/payroll').status_code == 200
        assert client.get(f'/hr/payroll/{c["a_run"]}').status_code == 200
        assert client.get(f'/hr/payroll/{c["a_run"]}/payslip/{c["a_slip"]}/print').status_code == 200
        token = auth_csrf(client)
        r = client.post(f'/hr/payroll/{c["a_run"]}/payslip/{c["a_slip"]}/edit',
                        data={'basic': '123456', '_csrf_token': token},
                        headers={'X-Requested-With': 'fetch'})
        assert (r.get_json() or {}).get('ok') is True

        # OTHER branch: denied on every surface.
        assert client.get(f'/hr/payroll/{c["b_run"]}').status_code == 403
        assert client.get(f'/hr/payroll/{c["b_run"]}/payslip/{c["b_slip"]}/print').status_code == 403
        r = client.post(f'/hr/payroll/{c["b_run"]}/payslip/{c["b_slip"]}/edit',
                        data={'basic': '1', '_csrf_token': token},
                        headers={'X-Requested-With': 'fetch'})
        assert r.status_code == 403
        for run_id in (c['b_run'],):
            assert client.post(f'/hr/payroll/{run_id}/mark-paid',
                               data={'_csrf_token': token},
                               headers={'X-Requested-With': 'fetch'}).status_code == 403
        with app.app_context():
            from models import Payslip as PS
            assert (db.session.get(PS, c['a_slip']).basic or 0) == 123456   # own edit stuck
            assert (db.session.get(PS, c['b_slip']).basic or 0) == 200000   # other untouched

        # Central (legacy) admin sees BOTH branches' runs.
        central = app.test_client()
        ct = login_token(central)
        central.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': ct})
        assert central.get(f'/hr/payroll/{c["a_run"]}').status_code == 200
        assert central.get(f'/hr/payroll/{c["b_run"]}').status_code == 200

        # A branch admin creating payroll stamps it with THEIR branch.
        r = client.post('/hr/payroll/create',
                        data={'year': '2098', 'month': '5', '_csrf_token': token},
                        headers={'X-Requested-With': 'fetch'})
        with app.app_context():
            from models import PayrollRun as PR
            made = PR.query.filter_by(year=2098, month=5).first()
            assert made is not None and made.branch_id == c['a_bid']
            c['made_run'] = made.id
    finally:
        with app.app_context():
            from models import (db as _db, Payslip as PS, PayrollRun as PR,
                                StaffMember as SM, User as U, Branch as BR)
            for run_id in (c.get('a_run'), c.get('b_run'), c.get('made_run')):
                r = run_id and _db.session.get(PR, run_id)
                r and _db.session.delete(r)   # cascade deletes payslips
            for sid in (c.get('a_staff'), c.get('b_staff')):
                s = sid and _db.session.get(SM, sid)
                s and _db.session.delete(s)
            for uid in (c.get('a_uid'), c.get('owner_b')):
                u = uid and _db.session.get(U, uid)
                u and _db.session.delete(u)
            for bid in (c.get('a_bid'), c.get('b_bid')):
                b = bid and _db.session.get(BR, bid)
                b and _db.session.delete(b)
            _db.session.commit()


def test_assign_class_rejects_out_of_branch_class(app):
    """A branch manager must not be able to assign a teacher to a class that
    lives in a branch they don't manage."""
    from models import (db, Branch, User, Teacher, AcademicSession, Term,
                        SchoolClass, ClassArm, ClassArmAssignment)
    ids = {}
    with app.app_context():
        # Manager in branch M; a class that belongs to branch OTHER.
        mgr_bid, mgr_uid = _make_branch_admin(app, 'M-Mgr', 'assign_mgr')
        other = Branch(name='Other-Cls', is_default=False)
        db.session.add(other); db.session.flush()
        # A teacher the manager may manage (same branch, lower rank).
        t_user = User(username='assign_teacher', role='teacher', scope='branch',
                      branch_id=mgr_bid, rank=1, is_active=True, must_change_password=False)
        t_user.set_password('Str0ng!Passw0rd1')
        db.session.add(t_user); db.session.flush()
        teacher = Teacher(user_id=t_user.id, employee_id=Teacher.generate_employee_id(),
                          branch_id=mgr_bid)
        db.session.add(teacher); db.session.flush()
        # A class assignment in the OTHER branch.
        ssn = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='AS-scope', is_active=True)
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(is_active=True).first() or \
            Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True)
        db.session.add(term); db.session.flush()
        # Dedicated class + arm so the (class_id, arm_id, term_id) triple can't
        # collide with a ClassArmAssignment another test already created.
        sc = SchoolClass(name='ScopeCls', level=1)
        db.session.add(sc); db.session.flush()
        arm = ClassArm(name='ScopeArm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id,
                                 branch_id=other.id)
        db.session.add(caa); db.session.commit()
        ids = {'mgr_bid': mgr_bid, 'mgr_uid': mgr_uid, 'other_bid': other.id,
               't_uid': t_user.id, 't_id': teacher.id, 'caa': caa.id,
               'sc': sc.id, 'arm': arm.id}

    try:
        client = _login(app, 'assign_mgr', 'Str0ng!Passw0rd1')
        token = auth_csrf(client)
        r = client.post(f'/users/{ids["t_uid"]}/assign-class',
                        data={'assignment_id': ids['caa'], 'is_form_teacher': 'on',
                              '_csrf_token': token},
                        headers={'X-Requested-With': 'fetch'})
        # JSON error (not a successful assignment).
        body = r.get_json() or {}
        assert body.get('ok') is not True
        assert 'branch' in (body.get('message') or body.get('error') or '').lower()
        with app.app_context():
            from models import TeacherClassAssignment as TCA
            assert TCA.query.filter_by(teacher_id=ids['t_id'],
                                       class_arm_assignment_id=ids['caa']).first() is None
    finally:
        with app.app_context():
            from models import (db as _db, ClassArmAssignment as CAA, Teacher as TE,
                                User as U, Branch as BR, SchoolClass as SC, ClassArm as CA)
            _db.session.get(CAA, ids['caa']) and _db.session.delete(_db.session.get(CAA, ids['caa']))
            _db.session.get(TE, ids['t_id']) and _db.session.delete(_db.session.get(TE, ids['t_id']))
            _db.session.get(SC, ids['sc']) and _db.session.delete(_db.session.get(SC, ids['sc']))
            _db.session.get(CA, ids['arm']) and _db.session.delete(_db.session.get(CA, ids['arm']))
            for uid in (ids['t_uid'], ids['mgr_uid']):
                u = _db.session.get(U, uid)
                u and _db.session.delete(u)
            for bid in (ids['mgr_bid'], ids['other_bid']):
                b = _db.session.get(BR, bid)
                b and _db.session.delete(b)
            _db.session.commit()
