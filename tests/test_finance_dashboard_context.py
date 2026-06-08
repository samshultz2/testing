"""Characterization test for the finance dashboard context.

Pins finance dashboard() output against a known, branch-isolated dataset so its
fee/expense blocks can be extracted into helpers without behaviour change.
"""
import datetime as dt
from flask import template_rendered
from models import (db, Branch, User, Student, AcademicSession, Term,
                    SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment)
from models.models_finance import FeePayment, Expense
from tests.conftest import login_token


def _seed(app):
    with app.app_context():
        b = Branch.query.filter_by(name='FDB-Branch').first()
        if b and Term.query.filter_by(name='FDB-Term').first():
            t = Term.query.filter_by(name='FDB-Term').first()
            return b.id, t.id
        if not b:
            b = Branch(name='FDB-Branch', is_active=True); db.session.add(b); db.session.commit()
        bid = b.id
        sess = AcademicSession(name='FDB-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='FDB-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        s = Student(student_id='FDB1', first_name='Fee', surname='Payer', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(s); db.session.flush()
        db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.add(FeePayment(student_id=s.id, term_id=term.id, branch_id=bid,
                                  amount=5000, payment_date=dt.date.today(), method='Cash',
                                  receipt_no='FDB-RCP-1'))
        db.session.add(Expense(term_id=term.id, branch_id=bid, description='Chalk', amount=2000,
                               expense_date=dt.date.today()))
        if not User.query.filter_by(username='fdb_user').first():
            u = User(username='fdb_user', role='staff', scope='branch', branch_id=bid,
                     full_name='FDB User'); u.set_password('secret123')
            u.set_permissions({'finance': 'edit'}); db.session.add(u)
        db.session.commit()
        return bid, term.id


def _capture(app, term_id):
    c = app.test_client()
    c.post('/login', data={'username': 'fdb_user', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    recorded = []
    def record(sender, template, context, **extra):
        recorded.append((template.name, context))
    template_rendered.connect(record, app)
    try:
        assert c.get(f'/finance/?term_id={term_id}').status_code == 200
    finally:
        template_rendered.disconnect(record, app)
    for name, ctx in recorded:
        if name == 'finance/dashboard.html':
            return ctx
    raise AssertionError('finance/dashboard.html not rendered')


def test_finance_dashboard_context(app):
    bid, term_id = _seed(app)
    ctx = _capture(app, term_id)
    assert ctx['collected'] == 5000.0
    assert ctx['expenses'] == 2000.0
    assert ctx['net'] == 3000.0
    assert ctx['discounts'] == 0.0
    assert ctx['expected'] == 0.0
    assert ctx['payable_total'] == 0
    assert ctx['outstanding'] == -5000.0
    assert ctx['rate'] == 0.0
    assert ctx['enrolled'] == 1
    assert ctx['defaulter_count'] == 0
    methods = {m['method']: m['amount'] for m in ctx['method_chart']}
    assert methods.get('Cash') == 5000.0
    for key in ('terms', 'selected_term', 'class_chart', 'recent', 'item_chart',
                'trend_chart', 'expense_chart', 'recent_expenses', 'has_structure'):
        assert key in ctx
