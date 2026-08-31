"""Dashboard Phase 3 — branch performance comparison for central users."""
from flask import session
from models import db, Branch, Student


def _mk_branch(name):
    b = Branch.query.filter_by(name=name).first()
    if not b:
        b = Branch(name=name, is_active=True)
        db.session.add(b); db.session.commit()
    return b.id


def test_branches_widget_central_only(app):
    from routes.main import permitted_widgets
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'   # always central
        assert 'branches' in permitted_widgets()
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'staff'
        session['scope'] = 'branch'
        assert 'branches' not in permitted_widgets()


def test_branch_comparison_none_for_single_branch(app):
    from routes.main import _dash_branch_comparison
    # A branch-scoped (non-central) user never gets the comparison.
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'staff'
        session['scope'] = 'branch'
        assert _dash_branch_comparison(None) is None


def test_branch_comparison_rows_for_central(app):
    from routes.main import _dash_branch_comparison
    with app.app_context():
        b1 = Branch.get_default().id
        b2 = _mk_branch('BC-Second')
        db.session.add_all([
            Student(student_id='ZZ_BC_1', first_name='A', surname='ZzBc1',
                    gender='Male', is_active=True, branch_id=b1),
            Student(student_id='ZZ_BC_2', first_name='B', surname='ZzBc2',
                    gender='Male', is_active=True, branch_id=b2),
            Student(student_id='ZZ_BC_3', first_name='C', surname='ZzBc3',
                    gender='Female', is_active=True, branch_id=b2),
        ])
        db.session.commit()
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['role'] = 'super_admin'
        rows = _dash_branch_comparison(None)
        assert rows is not None and len(rows) >= 2
        by_id = {r['id']: r for r in rows}
        assert by_id[b2]['students'] >= 2
        for r in rows:
            assert {'id', 'name', 'students', 'attendance', 'fees'} <= set(r)
