"""The /students class & arm filter works for every role (it was previously
gated to admins only) and narrows by the active term."""
import re
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, User)
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        existing = Term.query.filter_by(name='SF-Term').first()
        if existing:
            existing.is_active = True
            for t in Term.query.filter(Term.is_active == True, Term.id != existing.id).all():
                t.is_active = False
            db.session.commit()
            cas = ClassArmAssignment.query.filter_by(term_id=existing.id).order_by(
                ClassArmAssignment.id).all()
            return dict(class_a=cas[0].class_id, class_b=cas[1].class_id)
        # Make our term the sole active one for deterministic filtering.
        for t in Term.query.filter_by(is_active=True).all():
            t.is_active = False
        bid = Branch.get_default().id
        sess = AcademicSession(name='SF-Session'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='SF-Term', is_active=True)
        db.session.add(term); db.session.flush()
        classes = SchoolClass.query.order_by(SchoolClass.level).all()
        arms = ClassArm.query.order_by(ClassArm.name).all()
        ca_a = ClassArmAssignment(class_id=classes[0].id, arm_id=arms[0].id,
                                  term_id=term.id, branch_id=bid)
        ca_b = ClassArmAssignment(class_id=classes[1].id, arm_id=arms[0].id,
                                  term_id=term.id, branch_id=bid)
        db.session.add_all([ca_a, ca_b]); db.session.flush()
        sa = Student(student_id='SF_A', first_name='Aa', surname='Aa', gender='Male',
                     is_active=True, branch_id=bid)
        sb = Student(student_id='SF_B', first_name='Bb', surname='Bb', gender='Male',
                     is_active=True, branch_id=bid)
        db.session.add_all([sa, sb]); db.session.flush()
        db.session.add_all([
            StudentEnrollment(student_id=sa.id, class_arm_assignment_id=ca_a.id, is_active=True),
            StudentEnrollment(student_id=sb.id, class_arm_assignment_id=ca_b.id, is_active=True),
        ])
        db.session.commit()
        return dict(class_a=classes[0].id, class_b=classes[1].id)


def _teardown(app):
    with app.app_context():
        t = Term.query.filter_by(name='SF-Term').first()
        if t:
            t.is_active = False
            db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_class_filter_narrows_list(app):
    ids = _setup(app)
    try:
        c = _admin(app)
        html = c.get(f'/students?class_id={ids["class_a"]}').get_data(as_text=True)
        assert 'SF_A' in html and 'SF_B' not in html
        html = c.get(f'/students?class_id={ids["class_b"]}').get_data(as_text=True)
        assert 'SF_B' in html and 'SF_A' not in html
    finally:
        _teardown(app)


def test_summary_survives_sorted_query(app):
    """The list payload's side-rail summary (male/female/stream counts) is
    computed off the *sorted* list query. It must strip the ORDER BY before the
    DISTINCT stream count, or Postgres 500s the whole /students page ("ORDER BY
    expressions must appear in select list" for SELECT DISTINCT)."""
    ids = _setup(app)
    try:
        c = _admin(app)
        # A sort param is what triggers the ORDER BY that broke the DISTINCT count.
        r = c.get('/api/students?sort=surname&order=asc')
        assert r.status_code == 200
        summary = r.get_json()['summary']
        assert summary['total'] >= 2
        assert summary['male'] >= 2          # SF_A + SF_B are both Male
        assert 'female' in summary and 'streams' in summary
    finally:
        _teardown(app)


def test_csv_export(app):
    """The rail's Quick export CSV button hits /students/export?format=csv and
    gets a text/csv download (added alongside excel/word/pdf/image)."""
    _setup(app)
    try:
        c = _admin(app)
        import json as _json
        r = c.get('/students/export?format=csv&fields=' + _json.dumps(['student_id', 'surname', 'first_name']))
        assert r.status_code == 200
        assert 'text/csv' in r.headers.get('Content-Type', '')
        body = r.get_data(as_text=True)
        assert 'Student ID' in body and 'Surname' in body   # header row
    finally:
        _teardown(app)


def test_filter_works_for_non_admin(app):
    """A non-admin (staff with students access) can also use the filter."""
    ids = _setup(app)
    try:
        with app.app_context():
            if not User.query.filter_by(username='sf_staff').first():
                u = User(username='sf_staff', role='staff', scope='central',
                         full_name='SF Staff')
                u.set_password('secret123')
                u.set_permissions({'students': 'edit'})
                db.session.add(u); db.session.commit()
        c = app.test_client()
        c.post('/login', data={'username': 'sf_staff', 'password': 'secret123',
                               '_csrf_token': login_token(c)})
        html = c.get(f'/students?class_id={ids["class_a"]}').get_data(as_text=True)
        assert 'SF_A' in html and 'SF_B' not in html
    finally:
        _teardown(app)
