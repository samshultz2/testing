"""Class-arm assignments created without a branch must be auto-assigned to the
default branch, so they show under that branch (and don't vanish on a branch
switch). Regression for arms (SSS1 Iris) missing when a branch is selected."""
from models import db, SchoolClass, ClassArm, ClassArmAssignment, Term, AcademicSession, Branch
from utils.branch_scope import scope_query, SCOPE_KEY, VIEW_KEY
from utils.academics_schema import ensure_class_arm_branch, _healed


def _setup(app):
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='BSN 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True))
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='SSS1').first() or SchoolClass(name='SSS1', level=4)
        db.session.add(cls); db.session.flush()
        iris = ClassArm.query.filter_by(name='Iris').first() or ClassArm(name='Iris', is_active=True)
        db.session.add(iris); db.session.flush()
        bid = Branch.get_default().id
        a = ClassArmAssignment.query.filter_by(
            class_id=cls.id, arm_id=iris.id, term_id=term.id).first()
        if not a:
            a = ClassArmAssignment(class_id=cls.id, arm_id=iris.id, term_id=term.id)
            db.session.add(a)
        a.branch_id = None                       # simulate an unbranched (legacy) arm
        db.session.commit()
        return a.id, term.id, bid


def test_backfill_assigns_unbranched_to_default_branch(app):
    aid, term_id, bid = _setup(app)
    _healed.clear()                              # force the once-per-engine heal to run
    with app.app_context():
        ensure_class_arm_branch()
        a = db.session.get(ClassArmAssignment, aid)
        assert a.branch_id == bid                # NULL -> default branch


def test_backfilled_arm_shows_under_its_branch(app):
    aid, term_id, bid = _setup(app)
    _healed.clear()
    with app.app_context():
        ensure_class_arm_branch()
    with app.test_request_context('/'):
        from flask import session
        session['logged_in'] = True
        session[SCOPE_KEY] = 'central'
        session[VIEW_KEY] = bid                  # narrowed to the default branch
        ids = {a.id for a in scope_query(
            ClassArmAssignment.query.filter_by(term_id=term_id), ClassArmAssignment).all()}
        assert aid in ids
