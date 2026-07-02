"""Branch-isolation / access-control regression tests for the DB-access audit.

These lock in the Tier-1 fixes:
- whole-DB backup routes are central-admin only (a branch admin is bounced);
- the JAMB results list is branch-scoped (no cross-branch scores/names);
- the global search omnibox is branch-scoped (staff/applicant/receipt/CBT);
- the class-roster export checks branch access (no cross-branch IDOR).
"""
import pytest

from models import (db, Branch, User, Student, StaffMember, JAMBResult,
                    ClassArmAssignment, SchoolClass, ClassArm, Term, AcademicSession)
from tests.conftest import login_token


# --- helpers ---------------------------------------------------------------

def _branch(app, name):
    with app.app_context():
        b = Branch.query.filter_by(name=name).first()
        if not b:
            b = Branch(name=name, is_active=True)
            db.session.add(b); db.session.commit()
        return b.id


def _branch_admin(app, username, branch_id):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, full_name=username, role='admin',
                     scope='branch', branch_id=branch_id, is_active=True)
            u.set_password('secret123'); db.session.add(u); db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


@pytest.fixture(scope='module')
def two_branches(app):
    """B1 (attacker's branch) and B2 (victim branch) with seeded rows in B2:
    a staff member, a student + JAMB result, and a class-arm assignment."""
    b1 = _branch(app, 'ScopeB1')
    b2 = _branch(app, 'ScopeB2')
    with app.app_context():
        # unique markers so we can assert presence/absence in rendered pages
        if not StaffMember.query.filter_by(staff_id='ZORB-STAFF').first():
            db.session.add(StaffMember(first_name='Zzqxlmn', surname='Zorbstaff',
                                       staff_id='ZORB-STAFF', is_active=True, branch_id=b2))
        stu = Student.query.filter_by(student_id='ZORB-STU').first()
        if not stu:
            stu = Student(student_id='ZORB-STU', first_name='Zzqxlmn', surname='Zorbstu',
                          gender='Male', is_active=True, branch_id=b2)
            db.session.add(stu); db.session.flush()
            db.session.add(JAMBResult(student_id=stu.id, exam_year=2099, total_score=321))
        # a class-arm assignment owned by B2 for the IDOR test
        ssn = AcademicSession.query.first() or AcademicSession(name='SC 25/26', is_active=True)
        db.session.add(ssn); db.session.flush()
        term = Term.query.first() or Term(session_id=ssn.id, term_number=1, name='First Term', is_active=True)
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='SC-CLS').first() or SchoolClass(name='SC-CLS', level=3)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id, branch_id=b2).first()
        if not caa:
            caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=b2)
            db.session.add(caa)
        db.session.commit()
        caa_id = ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id, branch_id=b2).first().id
    return {'b1': b1, 'b2': b2, 'caa_b2': caa_id}


# --- 1. backup routes are central-admin only -------------------------------

def test_backup_routes_reject_branch_admin(app, two_branches):
    ca = _branch_admin(app, 'scope_b1_admin', two_branches['b1'])

    def _bounced(path):
        # central_admin_required sends a logged-in branch admin to the dashboard
        # (not to the backup page, and not to /login — they ARE logged in).
        r = ca.get(path, follow_redirects=False)
        loc = r.headers.get('Location') or ''
        assert r.status_code in (302, 303), (path, r.status_code)
        assert '/settings/backup' not in loc and '/login' not in loc, (path, loc)

    _bounced('/settings/backup')
    _bounced('/settings/backup/file/school_x.db')


def test_backup_page_allows_central_admin(auth_client):
    assert auth_client.get('/settings/backup').status_code == 200


# --- 2. JAMB list is branch-scoped -----------------------------------------

def test_jamb_list_hides_other_branch(app, two_branches):
    ca = _branch_admin(app, 'scope_b1_admin', two_branches['b1'])
    html = ca.get('/results/jamb?year=2099').get_data(as_text=True)
    assert 'Zorbstu' not in html          # B2 student must not leak to a B1 admin


def test_jamb_list_shows_own_branch_to_central(auth_client):
    html = auth_client.get('/results/jamb?year=2099').get_data(as_text=True)
    assert 'Zorbstu' in html              # central admin sees all branches


# --- 3. global search is branch-scoped -------------------------------------

def test_global_search_hides_other_branch_staff(app, two_branches):
    ca = _branch_admin(app, 'scope_b1_admin', two_branches['b1'])
    html = ca.get('/search?q=Zzqxlmn').get_data(as_text=True)
    assert 'Zorbstaff' not in html


def test_global_search_shows_all_to_central(auth_client):
    html = auth_client.get('/search?q=Zzqxlmn').get_data(as_text=True)
    assert 'Zorbstaff' in html


# --- 4. class-export IDOR guard --------------------------------------------

def test_class_export_blocks_cross_branch(app, two_branches):
    ca = _branch_admin(app, 'scope_b1_admin', two_branches['b1'])
    r = ca.get(f"/reports/export/class-students?assignment_id={two_branches['caa_b2']}")
    assert r.status_code == 403


def test_class_export_allows_central(auth_client, two_branches):
    r = auth_client.get(f"/reports/export/class-students?assignment_id={two_branches['caa_b2']}")
    assert r.status_code == 200


# --- Tier 2: input hardening ------------------------------------------------

def test_like_term_escapes_wildcards():
    from utils.search import like_term, escape_like
    assert like_term('50%_x') == r'%50\%\_x%'      # % and _ escaped, wrapped in %…%
    assert escape_like('a\\b') == 'a\\\\b'          # backslash escaped first


def test_formula_guard_neutralises_formula_cells():
    from utils.web_exports import formula_guard as fg
    for bad in ('=cmd()', '+1', '-1', '@SUM(A1)'):
        assert fg(bad).startswith("'")             # rendered as text, not a formula
    assert fg('Bello') == 'Bello'                   # ordinary text untouched
    assert fg(1234) == 1234                         # non-strings pass through


def test_global_search_wildcard_does_not_match_everything(app, two_branches):
    # A '%'-only term must not behave as "match all" for a central admin.
    c = app.test_client()
    from config import Config
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    html = c.get('/search?q=%25%25').get_data(as_text=True)   # q = '%%'
    assert 'Zorbstaff' not in html and 'Zorbstu' not in html


def test_copy_subject_config_rejects_bad_level(auth_client):
    r = auth_client.post('/generator/setup/copy-subjects',
                         data={'source_level': 'SSS%', 'target_level': 'JSS',
                               '_csrf_token': _tok_for(auth_client)},
                         follow_redirects=False)
    # invalid level -> bounced back to config (never runs the LIKE), not a 500
    assert r.status_code in (302, 303)


def _tok_for(c):
    with c.session_transaction() as s:
        return s.get('_csrf_token')
