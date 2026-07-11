"""Sales Phase 1 — fast buyer selection: the sale form no longer ships every
student; the buyer is found by class (+ optional arm) via an on-demand search."""
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _setup(app, tag):
    """A sole active term with one class+arm and two enrolled students. `tag`
    keeps names unique across tests sharing the session-scoped DB."""
    with app.app_context():
        for t in Term.query.filter_by(is_active=True).all():
            t.is_active = False
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'BP-Session-{tag}'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'BP-Term-{tag}', is_active=True)
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.order_by(SchoolClass.level).first()
        arm = ClassArm.query.order_by(ClassArm.name).first()
        caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        sid_a, sid_b = f'BP_ADA_{tag}', f'BP_BOLA_{tag}'
        a = Student(student_id=sid_a, first_name='Ada', surname='ZzBpAda',
                    gender='Female', is_active=True, branch_id=bid)
        b = Student(student_id=sid_b, first_name='Bola', surname='ZzBpBola',
                    gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        db.session.add_all([
            StudentEnrollment(student_id=a.id, class_arm_assignment_id=caa.id, is_active=True),
            StudentEnrollment(student_id=b.id, class_arm_assignment_id=caa.id, is_active=True),
        ])
        db.session.commit()
        return {'class_id': cls.id, 'arm_id': arm.id, 'term_id': term.id,
                'sid_a': sid_a, 'sid_b': sid_b}


def _teardown(app, ids):
    with app.app_context():
        t = db.session.get(Term, ids['term_id'])
        if t:
            t.is_active = False
            db.session.commit()


def test_new_sale_payload_uses_search_not_full_list(app):
    ids = _setup(app, 'payload')
    try:
        c = _admin(app)
        html = c.get('/sales/new').get_data(as_text=True)
        assert 'student_search_url' in html
        assert '"classes"' in html
        # The old behaviour embedded every student under a "students" key.
        assert '"students":' not in html
    finally:
        _teardown(app, ids)


def test_api_students_filters_by_class_and_query(app):
    ids = _setup(app, 'filter')
    try:
        c = _admin(app)
        # No class → nothing.
        assert c.get('/sales/api/students').get_json()['students'] == []
        # Class → both enrolled students.
        rows = c.get(f'/sales/api/students?class_id={ids["class_id"]}').get_json()['students']
        got = {r['student_id'] for r in rows}
        assert {ids['sid_a'], ids['sid_b']} <= got
        # Search narrows within the class.
        rows = c.get(f'/sales/api/students?class_id={ids["class_id"]}&q=Ada').get_json()['students']
        got = {r['student_id'] for r in rows}
        assert ids['sid_a'] in got and ids['sid_b'] not in got
        # Arm filter composes.
        rows = c.get(f'/sales/api/students?class_id={ids["class_id"]}&arm_id={ids["arm_id"]}').get_json()['students']
        assert len(rows) >= 2
    finally:
        _teardown(app, ids)


def test_sale_with_student_still_records(app):
    """Recording a sale to a chosen student is unchanged."""
    ids = _setup(app, 'record')
    try:
        c = _admin(app)
        with app.app_context():
            bid = Branch.get_default().id
            from models import Product
            p = Product(branch_id=bid, name='ZzBpBook', category='Textbooks',
                        unit_price=500, stock_qty=10, is_active=True)
            db.session.add(p); db.session.commit()
            pid = p.id
            sid = Student.query.filter_by(student_id=ids['sid_a']).first().id
        with c.session_transaction() as s:
            s['_csrf_token'] = 'a' * 64
        r = c.post('/sales/new', headers={'X-Requested-With': 'fetch'},
                   data={'product_id': pid, 'quantity': 2, 'payment_method': 'Cash',
                         'student_id': sid, '_csrf_token': 'a' * 64})
        assert r.status_code == 200 and r.get_json()['ok'], r.get_data(as_text=True)
        with app.app_context():
            from models import Sale
            sale = Sale.query.filter_by(student_id=sid).order_by(Sale.id.desc()).first()
            assert sale is not None and sale.total == 1000
    finally:
        _teardown(app, ids)
