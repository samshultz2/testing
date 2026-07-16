"""Staff loans — interest maths, November deadline, guarantor approval gating,
and automatic payroll-deduction repayment."""
from datetime import date

from models import db, StaffMember, StaffLoan, LoanRepayment, PayrollRun
from utils import staff_loans, hr


def _tables(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables
        ensure_tables()


def _staff(name, salary=200000):
    s = StaffMember(first_name=name, surname='Test', is_active=True, status='Active',
                    salary=salary, branch_id=None)
    db.session.add(s); db.session.flush()
    return s


# --- interest maths & deadline ---------------------------------------------
def test_flat_interest_and_months():
    # taken in January -> 11 monthly deductions through November
    assert staff_loans.months_until_november(date(2025, 1, 15)) == 11
    total, monthly = staff_loans.compute(100000, 5, 'flat', 11)
    assert total == 105000.0 and round(monthly, 2) == round(105000 / 11, 2)


def test_reducing_interest_differs_from_flat():
    flat_total, _ = staff_loans.compute(100000, 5, 'flat', 11)
    red_total, _ = staff_loans.compute(100000, 5, 'reducing', 11)
    # reducing balance charges interest only on what's outstanding -> less total
    assert red_total < flat_total and red_total > 100000


def test_loan_taken_after_november_rolls_to_next_year():
    assert staff_loans.months_until_november(date(2025, 12, 1)) == 12   # Dec'25 -> Nov'26
    assert staff_loans.deadline_for(date(2025, 12, 1)).year == 2026


# --- creation, guarantors, activation --------------------------------------
def test_create_requires_three_distinct_guarantors(app):
    _tables(app)
    with app.app_context():
        staff_loans.save_settings(enabled=True, method='flat', rate=5, guarantors_required=3)
        b = _staff('Bola'); g1 = _staff('G1'); g2 = _staff('G2'); db.session.commit()
        loan, err = staff_loans.create_loan(staff_id=b.id, branch_id=None, principal=50000,
                                            guarantor_ids=[g1.id, g2.id, b.id])   # borrower + only 2
        assert loan is None and 'guarantors' in err.lower()


def test_monthly_is_auto_raised_to_clear_by_november(app):
    _tables(app)
    with app.app_context():
        staff_loans.save_settings(enabled=True, method='flat', rate=5, guarantors_required=3)
        b = _staff('Ada'); gs = [_staff(f'G{i}') for i in range(3)]; db.session.commit()
        loan, err = staff_loans.create_loan(
            staff_id=b.id, branch_id=None, principal=110000,
            guarantor_ids=[g.id for g in gs], taken=date(2025, 1, 10), desired_monthly=1000)
        assert err is None
        # 115500 / 11 = 10500 minimum; the tiny 1000 request is raised to it
        assert loan.monthly_amount == 10500.0 and loan.status == 'pending'


def test_loan_activates_only_after_all_guarantors_approve(app):
    _tables(app)
    with app.app_context():
        staff_loans.save_settings(enabled=True, method='flat', rate=5, guarantors_required=3)
        b = _staff('Emeka'); gs = [_staff(f'H{i}') for i in range(3)]; db.session.commit()
        loan, _ = staff_loans.create_loan(staff_id=b.id, branch_id=None, principal=60000,
                                          guarantor_ids=[g.id for g in gs], taken=date(2025, 3, 1))
        staff_loans.act_on_guarantor(loan, gs[0].id, approve=True)
        staff_loans.act_on_guarantor(loan, gs[1].id, approve=True)
        assert loan.status == 'pending'                     # not all approved yet
        staff_loans.act_on_guarantor(loan, gs[2].id, approve=True)
        assert loan.status == 'active'                      # disbursed


def test_a_decline_rejects_the_loan(app):
    _tables(app)
    with app.app_context():
        staff_loans.save_settings(enabled=True, method='flat', rate=5, guarantors_required=3)
        b = _staff('Ken'); gs = [_staff(f'J{i}') for i in range(3)]; db.session.commit()
        loan, _ = staff_loans.create_loan(staff_id=b.id, branch_id=None, principal=60000,
                                          guarantor_ids=[g.id for g in gs])
        staff_loans.act_on_guarantor(loan, gs[0].id, approve=False)
        assert loan.status == 'rejected'


# --- payroll repayment integration -----------------------------------------
def test_payroll_finalize_deducts_and_is_idempotent(app):
    _tables(app)
    with app.app_context():
        staff_loans.save_settings(enabled=True, method='flat', rate=5, guarantors_required=3)
        b = _staff('Ngozi', salary=300000); gs = [_staff(f'K{i}') for i in range(3)]; db.session.commit()
        loan, _ = staff_loans.create_loan(staff_id=b.id, branch_id=None, principal=110000,
                                          guarantor_ids=[g.id for g in gs], taken=date(2025, 1, 10))
        for g in gs:
            staff_loans.act_on_guarantor(loan, g.id, approve=True)
        assert loan.status == 'active'
        monthly = loan.monthly_amount

        run = PayrollRun(year=2025, month=2, status='Draft', branch_id=None)
        db.session.add(run); db.session.commit()
        hr.generate_payslips(run); db.session.commit()
        # the borrower's payslip carries a loan-repayment deduction line
        ps = next(p for p in run.payslips if p.staff_id == b.id)
        assert any('loan' in i.name.lower() and i.amount == monthly for i in ps.items)
        # finalizing books the borrower's repayment (other staff/loans may share
        # the run in the shared test DB, so assert this loan specifically)
        staff_loans.post_run_repayments(run)
        assert loan.amount_repaid == monthly and loan.status == 'active'
        assert LoanRepayment.query.filter_by(loan_id=loan.id).count() == 1
        # re-running the same finalized run must not double-charge this loan
        staff_loans.post_run_repayments(run)
        assert LoanRepayment.query.filter_by(loan_id=loan.id).count() == 1


def test_repayment_caps_at_outstanding_and_marks_paid(app):
    _tables(app)
    with app.app_context():
        staff_loans.save_settings(enabled=True, method='flat', rate=5, guarantors_required=1)
        b = _staff('Sam'); g = _staff('Guar'); db.session.commit()
        loan, _ = staff_loans.create_loan(staff_id=b.id, branch_id=None, principal=10000,
                                          guarantor_ids=[g.id])
        staff_loans.act_on_guarantor(loan, g.id, approve=True)
        applied = staff_loans.record_repayment(loan, 999999, source='manual')  # overpay
        db.session.commit()
        assert applied == loan.total_repayable and loan.outstanding == 0 and loan.status == 'paid'
