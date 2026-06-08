"""Branch scoping of parent communication (privacy)."""
from flask import session
from models import db, Branch, Student
from utils import comms


def _two_branch_students(app):
    with app.app_context():
        a = Branch.get_default()
        b = Branch.query.filter_by(name='CommsB').first()
        if not b:
            b = Branch(name='CommsB', is_active=True); db.session.add(b); db.session.flush()
        if not Student.query.filter_by(student_id='CMA1').first():
            db.session.add(Student(student_id='CMA1', first_name='Ca', surname='A',
                                   gender='Male', is_active=True, branch_id=a.id))
        if not Student.query.filter_by(student_id='CMB1').first():
            db.session.add(Student(student_id='CMB1', first_name='Cb', surname='B',
                                   gender='Male', is_active=True, branch_id=b.id))
        db.session.commit()
        return a.id, b.id


def test_branch_user_audience_excludes_other_branches(app):
    a_id, b_id = _two_branch_students(app)
    with app.test_request_context('/'):
        session['scope'] = 'branch'; session['branch_id'] = b_id
        targets = comms.resolve_audience('all', None)
        ids = {t['student'].student_id for t in targets}
        assert 'CMB1' in ids
        assert 'CMA1' not in ids


def test_central_user_audience_includes_all(app):
    a_id, b_id = _two_branch_students(app)
    with app.test_request_context('/'):
        session['role'] = 'admin'   # central
        targets = comms.resolve_audience('all', None)
        ids = {t['student'].student_id for t in targets}
        assert {'CMA1', 'CMB1'} <= ids
