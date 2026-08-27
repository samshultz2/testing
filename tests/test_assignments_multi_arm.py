"""Setting up a class lets you pick several arms at once — one assignment is
created per selected arm (existing ones skipped)."""
import itertools
from config import Config
from models import db, SchoolClass, ClassArm, Term, AcademicSession, ClassArmAssignment
from tests.conftest import login_token, auth_csrf

_SEQ = itertools.count()


def _seed(app):
    with app.app_context():
        ssn = (AcademicSession.query.filter_by(is_active=True).first()
               or AcademicSession(name='ASG 25/26', is_active=True))
        db.session.add(ssn); db.session.flush()
        term = (Term.query.filter_by(is_active=True).first()
                or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True))
        db.session.add(term); db.session.flush()
        tag = next(_SEQ)
        cls = SchoolClass(name=f'MCLS{tag}', level=1)
        db.session.add(cls); db.session.flush()
        arms = [ClassArm(name=f'M{tag}-{n}', is_active=True) for n in ('Iris', 'Rose', 'Lily')]
        db.session.add_all(arms); db.session.commit()
        return term.id, cls.id, [a.id for a in arms]


def test_add_assignment_creates_one_per_arm(app):
    term_id, class_id, arm_ids = _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.post('/academics/assignments/add', data={
        '_csrf_token': auth_csrf(c), 'term_id': term_id, 'class_id': class_id,
        'arm_ids': [str(a) for a in arm_ids]})
    assert r.status_code in (200, 302)
    with app.app_context():
        n = ClassArmAssignment.query.filter_by(term_id=term_id, class_id=class_id).count()
        assert n == 3                                   # one per selected arm

    # Re-posting the same set adds nothing new (all already exist).
    r = c.post('/academics/assignments/add', data={
        '_csrf_token': auth_csrf(c), 'term_id': term_id, 'class_id': class_id,
        'arm_ids': [str(a) for a in arm_ids]}, follow_redirects=True)
    with app.app_context():
        assert ClassArmAssignment.query.filter_by(term_id=term_id, class_id=class_id).count() == 3
