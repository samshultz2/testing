"""Red-team regression: payroll is org-wide (one run carries every branch's
staff), so a branch-scoped admin must not be able to read or tamper with it by
guessing a run/slip id. Also covers the assign-class branch guard."""
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


def test_branch_admin_cannot_touch_other_branch_payroll(app):
    from models import db, Branch, StaffMember, PayrollRun, Payslip, User
    created = {}
    with app.app_context():
        # Staff + payslip living in branch "B-Payroll".
        staff_bid, _ = _make_branch_admin(app, 'B-Payroll', 'payroll_staff_owner')
        s = StaffMember(staff_id=StaffMember.generate_staff_id(), first_name='Pay',
                        surname='Target', branch_id=staff_bid, salary=100000,
                        is_active=True, status='Active')
        db.session.add(s)
        db.session.flush()
        run = PayrollRun(year=2099, month=6, status='Draft')
        db.session.add(run)
        db.session.flush()
        ps = Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name,
                     basic=100000, allowances=0, deductions=0)
        db.session.add(ps)
        db.session.commit()
        # A DIFFERENT branch's admin (non-central).
        adm_bid, adm_uid = _make_branch_admin(app, 'A-Other', 'branch_admin_a')
        created = {'run': run.id, 'slip': ps.id, 'staff': s.id,
                   'branches': [staff_bid, adm_bid], 'user': adm_uid,
                   'owner_user': User.query.filter_by(username='payroll_staff_owner').first().id}

    try:
        client = _login(app, 'branch_admin_a', 'Str0ng!Passw0rd1')
        # Sanity: the branch admin IS logged in (HR dashboard reachable, so a
        # later 403 is the payroll guard — not just an unauthenticated bounce).
        assert client.get('/hr/').status_code == 200

        run_id, slip_id = created['run'], created['slip']
        # Every payroll surface must be denied to a non-central admin.
        assert client.get('/hr/payroll').status_code == 403
        assert client.get(f'/hr/payroll/{run_id}').status_code == 403
        assert client.get(f'/hr/payroll/{run_id}/payslip/{slip_id}/print').status_code == 403
        token = auth_csrf(client)
        r = client.post(f'/hr/payroll/{run_id}/payslip/{slip_id}/edit',
                        data={'basic': '1', '_csrf_token': token},
                        headers={'X-Requested-With': 'fetch'})
        assert r.status_code == 403
        # The tamper must NOT have taken effect.
        with app.app_context():
            from models import Payslip as PS
            assert (db.session.get(PS, slip_id).basic or 0) == 100000

        # Control: the central (legacy) admin CAN view payroll — we didn't break it.
        central = app.test_client()
        ct = login_token(central)
        central.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': ct})
        assert central.get(f'/hr/payroll/{run_id}').status_code == 200
    finally:
        with app.app_context():
            from models import db as _db, Payslip as PS, PayrollRun as PR, StaffMember as SM, User as U, Branch as BR
            _db.session.get(PS, created['slip']) and _db.session.delete(_db.session.get(PS, created['slip']))
            _db.session.get(PR, created['run']) and _db.session.delete(_db.session.get(PR, created['run']))
            _db.session.get(SM, created['staff']) and _db.session.delete(_db.session.get(SM, created['staff']))
            for uid in (created['user'], created['owner_user']):
                u = _db.session.get(U, uid)
                u and _db.session.delete(u)
            for bid in created['branches']:
                b = _db.session.get(BR, bid)
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
