"""Finance business-logic guards: cross-branch fee-waiver block, payment-edit
audit trail (old->new), and duplicate-payment (reference) idempotency.
"""
from config import Config
from models import (db, Branch, AcademicSession, Term, Student, FeePayment, FeeDiscount)
from models.models.settings import AuditLog
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    import re
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def _term(app):
    with app.app_context():
        t = Term.query.filter_by(name='FL-Term').first()
        if not t:
            s = AcademicSession(name='FL-Sess'); db.session.add(s); db.session.flush()
            t = Term(session_id=s.id, term_number=1, name='FL-Term', is_active=True)
            db.session.add(t); db.session.commit()
        return t.id


def _student(app, sid, branch_id=None):
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name=sid, surname='Y', gender='Male',
                        is_active=True, branch_id=branch_id or Branch.get_default().id)
            db.session.add(s); db.session.commit()
        return s.id


def _other_branch(app):
    with app.app_context():
        b = Branch.query.filter_by(name='FL-OtherBranch').first()
        if not b:
            b = Branch(name='FL-OtherBranch', is_active=True)
            db.session.add(b); db.session.commit()
        return b.id


# --- cross-branch waiver ----------------------------------------------------
def test_branch_admin_cannot_waive_other_branch_fees(app):
    """A branch admin scoped to branch A must not apply a discount to a student
    in branch B (previously add_discount skipped the branch check)."""
    from models import User
    tid = _term(app)
    other = _other_branch(app)
    victim = _student(app, 'FL_victim', branch_id=other)
    with app.app_context():
        home = Branch.get_default().id
        if not User.query.filter_by(username='fl_badmin').first():
            u = User(username='fl_badmin', full_name='BA', role='admin',
                     scope='branch', branch_id=home, rank=50, manage_scope='branch')
            u.set_password('secret123'); db.session.add(u); db.session.commit()

    c = app.test_client()
    c.post('/login', data={'username': 'fl_badmin', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    r = c.post('/finance/discounts/add', data={
        'student_id': victim, 'term_id': tid, 'amount': '50000',
        'reason': 'x', '_csrf_token': _pt(c)})
    assert r.status_code == 403                       # cross-branch write blocked
    with app.app_context():
        assert FeeDiscount.query.filter_by(student_id=victim).first() is None


# --- payment edit audit -----------------------------------------------------
def test_payment_edit_audits_old_and_new_amount(app):
    tid = _term(app)
    sid = _student(app, 'FL_payedit')
    c = _admin(app)
    c.post('/finance/payments/record', data={
        'student_id': sid, 'term_id': tid, 'amount': '50000',
        'method': 'Cash', '_csrf_token': _pt(c)}, follow_redirects=True)
    with app.app_context():
        p = FeePayment.query.filter_by(student_id=sid).order_by(FeePayment.id.desc()).first()
        pid = p.id
    c.post(f'/finance/payments/{pid}/edit', data={
        'amount': '5000', 'method': 'Cash', '_csrf_token': _pt(c)}, follow_redirects=True)
    with app.app_context():
        row = (AuditLog.query.filter_by(action='finance.payment_edit')
               .order_by(AuditLog.id.desc()).first())
        assert row is not None
        assert '50000' in row.detail and '5000' in row.detail and '→' in row.detail


# --- duplicate payment guard ------------------------------------------------
def test_duplicate_reference_payment_is_rejected(app):
    tid = _term(app)
    sid = _student(app, 'FL_dup')
    c = _admin(app)
    data = {'student_id': sid, 'term_id': tid, 'amount': '10000',
            'method': 'Transfer', 'reference': 'TXN-DUP-1'}
    c.post('/finance/payments/record', data={**data, '_csrf_token': _pt(c)},
           follow_redirects=True)
    c.post('/finance/payments/record', data={**data, '_csrf_token': _pt(c)},
           follow_redirects=True)
    with app.app_context():
        n = FeePayment.query.filter_by(student_id=sid, term_id=tid, reference='TXN-DUP-1').count()
        assert n == 1                                 # second submit refused
