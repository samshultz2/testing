"""Per-staff recurring deduction amounts + contribution tracking.

Welfare (and the like) is one deduction item, but different staff contribute
different amounts. A per-staff assignment overrides the type's default on that
person's payslip, and their running contribution is tracked from finalized pay.
"""
from datetime import date

from config import Config
from models import (db, User, StaffMember, Branch, PayrollRun, Payslip,
                    PayslipDeduction, PayrollDeductionType, StaffDeduction)
from tests.conftest import login_token, auth_csrf
from contextlib import contextmanager


@contextmanager
def _central_ctx(app):
    """A request context scoped as a central super-admin, so branch-scoped
    queries in the helpers see every branch (mirrors how the app calls them)."""
    with app.test_request_context():
        from flask import session
        session['role'] = 'super_admin'
        session['scope'] = 'central'
        yield


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _staff(app, tag, salary=100000):
    with app.app_context():
        bid = Branch.get_default().id
        s = StaffMember(first_name='Ded', surname=tag, is_active=True, status='Active',
                        staff_type='Teaching', branch_id=bid, salary=salary)
        db.session.add(s); db.session.commit()
        return s.id, bid


def _welfare_type(app, name='Welfare', value=2000, branch_id=None):
    with app.app_context():
        t = PayrollDeductionType(name=name, kind='fixed', value=value, is_active=True,
                                 branch_id=branch_id)
        db.session.add(t); db.session.commit()
        return t.id


def test_override_replaces_default_on_payslip(app):
    from utils import hr as hr_utils
    sid, bid = _staff(app, 'Ovr')
    tid = _welfare_type(app, 'Welfare', 2000, branch_id=bid)
    with app.app_context():
        # This staff pays ₦12,000 Welfare, not the ₦2,000 default.
        db.session.add(StaffDeduction(staff_id=sid, deduction_type_id=tid, amount=12000))
        run = PayrollRun(year=2025, month=5, branch_id=bid, status='Draft')
        db.session.add(run); db.session.commit()
        hr_utils.generate_payslips(run)
        db.session.commit()
        ps = Payslip.query.filter_by(run_id=run.id, staff_id=sid).first()
        welfare = [i for i in ps.items if i.name == 'Welfare']
        assert len(welfare) == 1
        assert welfare[0].amount == 12000        # override, not the 2000 default


def test_default_applies_without_override(app):
    from utils import hr as hr_utils
    sid, bid = _staff(app, 'Def')
    _welfare_type(app, 'Union', 1500, branch_id=bid)
    with app.app_context():
        run = PayrollRun(year=2025, month=6, branch_id=bid, status='Draft')
        db.session.add(run); db.session.commit()
        hr_utils.generate_payslips(run)
        db.session.commit()
        ps = Payslip.query.filter_by(run_id=run.id, staff_id=sid).first()
        union = [i for i in ps.items if i.name == 'Union']
        assert len(union) == 1 and union[0].amount == 1500


def test_contributions_only_count_finalized(app):
    from utils import hr as hr_utils
    sid, bid = _staff(app, 'Con')
    with app.app_context():
        # Two payslips with the same Welfare line: one Paid, one Draft.
        paid = PayrollRun(year=2025, month=1, branch_id=bid, status='Paid')
        draft = PayrollRun(year=2025, month=2, branch_id=bid, status='Draft')
        db.session.add_all([paid, draft]); db.session.flush()
        for run in (paid, draft):
            ps = Payslip(run_id=run.id, staff_id=sid, staff_name='x', basic=100000, net=90000)
            db.session.add(ps); db.session.flush()
            db.session.add(PayslipDeduction(payslip_id=ps.id, name='Welfare', amount=5000))
        db.session.commit()
    with _central_ctx(app):
        c = hr_utils.deduction_contributions(sid)
        assert c['Welfare']['total'] == 5000     # only the Paid run counts
        assert c['Welfare']['months'] == 1


def test_overview_merges_monthly_and_contributed(app):
    from utils import hr as hr_utils
    sid, bid = _staff(app, 'Ovw')
    tid = _welfare_type(app, 'Cooperative', 2000, branch_id=bid)
    with app.app_context():
        db.session.add(StaffDeduction(staff_id=sid, deduction_type_id=tid, amount=10000))
        run = PayrollRun(year=2025, month=3, branch_id=bid, status='Finalized')
        db.session.add(run); db.session.flush()
        ps = Payslip(run_id=run.id, staff_id=sid, staff_name='x', basic=100000, net=90000)
        db.session.add(ps); db.session.flush()
        db.session.add(PayslipDeduction(payslip_id=ps.id, name='Cooperative', amount=10000))
        db.session.commit()
    with _central_ctx(app):
        ov = hr_utils.staff_deduction_overview(sid)
        item = next(i for i in ov['items'] if i['name'] == 'Cooperative')
        assert item['monthly'] == 10000 and item['assigned'] is True
        assert item['contributed'] == 10000
        # This staff only has the one contribution recorded.
        assert ov['total_contributed'] == 10000


def test_admin_set_and_clear_route(app):
    sid, bid = _staff(app, 'Rte')
    tid = _welfare_type(app, 'Welfare', 2000, branch_id=bid)
    client = _admin(app)
    tok = auth_csrf(client)
    # Set
    r = client.post(f'/hr/staff/{sid}/deductions',
                    data={'type_id': tid, 'amount': '7500', '_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'}).get_json()
    assert r['ok']
    with app.app_context():
        sd = StaffDeduction.query.filter_by(staff_id=sid, deduction_type_id=tid).first()
        assert sd and sd.amount == 7500
    # Clear (blank amount)
    r = client.post(f'/hr/staff/{sid}/deductions',
                    data={'type_id': tid, 'amount': '', '_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'}).get_json()
    assert r['ok']
    with app.app_context():
        assert StaffDeduction.query.filter_by(staff_id=sid, deduction_type_id=tid).first() is None


def test_bulk_amounts_screen_sets_and_clears(app):
    """The central 'per-staff amounts' screen upserts many staff at once."""
    s1, bid = _staff(app, 'Bulk1')
    s2, _ = _staff(app, 'Bulk2')
    tid = _welfare_type(app, 'Welfare', 2000, branch_id=bid)
    client = _admin(app)
    tok = auth_csrf(client)
    r = client.post(f'/hr/settings/deductions/{tid}/amounts',
                    data={f'amount_{s1}': '5000', f'amount_{s2}': '15000', '_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'}).get_json()
    assert r['ok']
    with app.app_context():
        amounts = {sd.staff_id: sd.amount for sd in
                   StaffDeduction.query.filter_by(deduction_type_id=tid).all()}
        assert amounts.get(s1) == 5000 and amounts.get(s2) == 15000
    # Blanking s1 clears just that override.
    r = client.post(f'/hr/settings/deductions/{tid}/amounts',
                    data={f'amount_{s1}': '', f'amount_{s2}': '15000', '_csrf_token': tok},
                    headers={'X-Requested-With': 'fetch'}).get_json()
    assert r['ok']
    with app.app_context():
        assert StaffDeduction.query.filter_by(deduction_type_id=tid, staff_id=s1).first() is None
        assert StaffDeduction.query.filter_by(deduction_type_id=tid, staff_id=s2).first() is not None


def test_self_service_exposes_contributions(app):
    from utils import hr as hr_utils
    with app.app_context():
        bid = Branch.get_default().id
        u = User(username='welf_self', full_name='Welf Self', role='staff',
                 scope='branch', branch_id=bid)
        u.set_password('CorrectHorse9'); u.is_active = True
        u.set_permissions({'hr': {'self_deductions': 'view', 'self_payroll': 'view'}})
        db.session.add(u); db.session.flush()
        s = StaffMember(first_name='Welf', surname='Self', is_active=True, status='Active',
                        staff_type='Teaching', branch_id=bid, user_id=u.id, salary=100000)
        db.session.add(s); db.session.flush()
        run = PayrollRun(year=2025, month=4, branch_id=bid, status='Finalized')
        db.session.add(run); db.session.flush()
        ps = Payslip(run_id=run.id, staff_id=s.id, staff_name=s.full_name, basic=100000, net=90000)
        db.session.add(ps); db.session.flush()
        db.session.add(PayslipDeduction(payslip_id=ps.id, name='Welfare', amount=6000))
        db.session.commit()
        uid = u.id
    with _central_ctx(app):
        u = db.session.get(User, uid)
        data = hr_utils.hr_self_service(u)
        assert data['contributions'] is not None
        names = {i['name']: i for i in data['contributions']['items']}
        assert 'Welfare' in names and names['Welfare']['contributed'] == 6000
