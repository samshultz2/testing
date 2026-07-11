"""Sales Phase 2 — management analytics: revenue/units/profit, breakdowns, and a
product drill-down showing which classes' students bought a given product."""
from config import Config
from models import (db, Branch, Product, Sale, SaleItem, AcademicSession, Term,
                    SchoolClass, ClassArm, ClassArmAssignment, Student, StudentEnrollment)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app, tag):
    """A product sold to two students in the same class + a walk-in. `tag` keeps
    names unique across tests sharing the session-scoped DB."""
    with app.app_context():
        for t in Term.query.filter_by(is_active=True).all():
            t.is_active = False
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'AN-Session-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'AN-Term-{tag}', is_active=True)
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.order_by(SchoolClass.level).first()
        arm = ClassArm.query.order_by(ClassArm.name).first()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        s1 = Student(student_id=f'AN_S1_{tag}', first_name='One', surname='ZzAn1', gender='Male',
                     is_active=True, branch_id=bid)
        s2 = Student(student_id=f'AN_S2_{tag}', first_name='Two', surname='ZzAn2', gender='Female',
                     is_active=True, branch_id=bid)
        db.session.add_all([s1, s2]); db.session.flush()
        db.session.add_all([
            StudentEnrollment(student_id=s1.id, class_arm_assignment_id=caa.id, is_active=True),
            StudentEnrollment(student_id=s2.id, class_arm_assignment_id=caa.id, is_active=True),
        ])
        prod = Product(branch_id=bid, name=f'ZzAnBook-{tag}', category='Textbooks',
                       unit_price=1000, cost_price=600, stock_qty=100, is_active=True)
        db.session.add(prod); db.session.flush()

        def _sale(student_id, qty, method='Cash'):
            sale = Sale(branch_id=bid, student_id=student_id, payment_method=method,
                        total=1000 * qty, amount_paid=1000 * qty, sold_by='Tester',
                        receipt_no=f'ANx{tag}{student_id or 0}{qty}')
            db.session.add(sale); db.session.flush()
            db.session.add(SaleItem(sale_id=sale.id, product_id=prod.id, description=prod.name,
                                    quantity=qty, unit_price=1000, line_total=1000 * qty))
        _sale(s1.id, 1)
        _sale(s2.id, 2)
        _sale(None, 1)   # walk-in
        db.session.commit()
        return {'product_id': prod.id, 'term_id': term.id, 'class_name': cls.name,
                'product_name': prod.name}


def _teardown(app, ids):
    with app.app_context():
        t = db.session.get(Term, ids['term_id'])
        if t:
            t.is_active = False
            db.session.commit()


def test_analytics_summary_and_breakdowns(app):
    ids = _seed(app, 'summary')
    try:
        c = _admin(app)
        j = c.get('/sales/analytics', headers={'X-Requested-With': 'fetch'}).get_json()
        assert j['page'] == 'analytics'
        s = j['summary']
        # The shared DB may hold other tests' sales, so assert inclusion, and
        # verify this product's own line exactly.
        assert s['revenue'] >= 4000 and s['units'] >= 4 and s['count'] >= 3
        assert 'Textbooks' in {r['label'] for r in j['by_category']}
        assert j['top_products'] and 'revenue' in j['top_products'][0]
        assert any(r['label'] == 'Cash' for r in j['by_method'])
        assert any(r['label'] == 'Tester' for r in j['by_cashier'])
        assert isinstance(j['trend'], list) and j['trend']
    finally:
        _teardown(app, ids)


def test_product_drilldown_by_class(app):
    ids = _seed(app, 'drill')
    try:
        c = _admin(app)
        j = c.get(f'/sales/analytics?product_id={ids["product_id"]}',
                  headers={'X-Requested-With': 'fetch'}).get_json()
        drill = j['drill']
        assert drill is not None
        assert drill['total_students'] == 2       # two distinct student buyers
        assert drill['total_units'] == 4
        assert drill['non_student_units'] == 1     # the walk-in
        # Both students share the same class → one class row with 2 students, 3 units.
        row = next(r for r in drill['rows'] if r['label'].startswith(ids['class_name']))
        assert row['students'] == 2 and row['units'] == 3
    finally:
        _teardown(app, ids)
