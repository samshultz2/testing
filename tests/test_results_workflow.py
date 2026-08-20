"""Results workflow: comments grid, bulk score entry (+auto positions), hub page."""
import re
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject, ClassSubject,
                    AssessmentType, StudentScore, TermSummary)
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        if Student.query.filter_by(student_id='WF1').first():
            t = Term.query.filter_by(name='WF-Term').first()
            caa = ClassArmAssignment.query.filter_by(term_id=t.id).first()
            cs = ClassSubject.query.filter_by(term_id=t.id).first()
            at = AssessmentType.query.filter_by(name='WF-Exam').first()
            a = Student.query.filter_by(student_id='WF1').first()
            b = Student.query.filter_by(student_id='WF2').first()
            return dict(term=t.id, asg=caa.id, cs=cs.id, at=at.id, a=a.id, b=b.id)
        bid = Branch.get_default().id
        sess = AcademicSession(name='WF-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='WF-Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject.query.first() or Subject(name='Maths', is_active=True)
        if subj.id is None:
            db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        at = AssessmentType(name='WF-Exam', short_name='EXAM', max_score=100, order=99, is_active=True)
        db.session.add(at); db.session.flush()
        a = Student(student_id='WF1', first_name='Aa', surname='One', gender='Male', is_active=True, branch_id=bid)
        b = Student(student_id='WF2', first_name='Bb', surname='Two', gender='Female', is_active=True, branch_id=bid)
        db.session.add_all([a, b]); db.session.flush()
        for s in (a, b):
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return dict(term=term.id, asg=caa.id, cs=cs.id, at=at.id, a=a.id, b=b.id)


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _pt(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/').get_data(as_text=True)).group(1)


def test_bulk_entry_saves_and_autocomputes(app):
    ids = _setup(app)
    c = _admin(app)
    assert c.get(f'/subjects/bulk-entry?term_id={ids["term"]}&assignment_id={ids["asg"]}').status_code == 200
    c.post('/subjects/bulk-entry', data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], '_csrf_token': _pt(c),
        f's_{ids["a"]}_{ids["cs"]}_{ids["at"]}': '90',
        f's_{ids["b"]}_{ids["cs"]}_{ids["at"]}': '40',
    }, follow_redirects=True)
    with app.app_context():
        assert StudentScore.query.filter_by(student_id=ids['a'], class_subject_id=ids['cs']).first().score == 90
        # positions auto-computed on save
        ta = TermSummary.query.filter_by(student_id=ids['a'], term_id=ids['term']).first()
        tb = TermSummary.query.filter_by(student_id=ids['b'], term_id=ids['term']).first()
        assert ta.position_in_class == 1 and tb.position_in_class == 2


def test_comments_grid_saves(app):
    ids = _setup(app)
    c = _admin(app)
    c.post('/subjects/comments', data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], '_csrf_token': _pt(c),
        f't_{ids["a"]}': 'Hardworking student.', f'p_{ids["a"]}': 'Keep it up.',
    }, follow_redirects=True)
    with app.app_context():
        ts = TermSummary.query.filter_by(student_id=ids['a'], term_id=ids['term']).first()
        assert ts.teacher_comment == 'Hardworking student.'
        assert ts.principal_comment == 'Keep it up.'


def test_workflow_page(app):
    ids = _setup(app)
    c = _admin(app)
    html = c.get(f'/subjects/workflow?term_id={ids["term"]}&assignment_id={ids["asg"]}').get_data(as_text=True)
    # Workflow is now a React shell hydrated with the step checklist payload.
    assert 'subj-app' in html and '"page": "workflow"' in html
    for key in ('scores_entered', 'scores_expected', 'comments', 'behaviour', 'positions'):
        assert f'"{key}"' in html


def test_bulk_entry_rejects_above_max(app):
    ids = _setup(app)
    with app.app_context():
        sc = StudentScore.query.filter_by(student_id=ids['b'], class_subject_id=ids['cs'],
                                          assessment_type_id=ids['at']).first()
        if not sc:
            sc = StudentScore(student_id=ids['b'], class_subject_id=ids['cs'],
                              assessment_type_id=ids['at'], score=50)
            db.session.add(sc)
        else:
            sc.score = 50
        db.session.commit()
    c = _admin(app)
    c.post('/subjects/bulk-entry', data={
        'term_id': ids['term'], 'assignment_id': ids['asg'], '_csrf_token': _pt(c),
        f's_{ids["b"]}_{ids["cs"]}_{ids["at"]}': '150',   # above max 100
    }, follow_redirects=True)
    with app.app_context():
        sc = StudentScore.query.filter_by(student_id=ids['b'], class_subject_id=ids['cs'],
                                          assessment_type_id=ids['at']).first()
        assert sc.score == 50   # over-max value rejected, baseline kept


def test_parent_results_publish_gate(app):
    ids = _setup(app)
    from utils.report_card import compute_term_summaries
    from models import ClassArmAssignment as CAA, Term as T
    with app.app_context():
        s = Student.query.get(ids['a'])
        s.set_portal_password('pw12345')
        class_id = CAA.query.get(ids['asg']).class_id
        T.query.get(ids['term']).results_published = False
        db.session.commit()
        compute_term_summaries(ids['term'], class_id)
    c = app.test_client()
    tok = re.search(r'name="_csrf_token" value="([0-9a-f]+)"',
                    c.get('/parent/login').get_data(as_text=True)).group(1)
    c.post('/parent/login', data={'student_id': 'WF1', 'password': 'pw12345', '_csrf_token': tok})
    hidden = c.get(f'/parent/?term_id={ids["term"]}',
                   headers={'X-Requested-With': 'fetch'}).get_json()
    assert hidden['report'] is None and not hidden['results_ready']   # unpublished -> hidden
    with app.app_context():
        T.query.get(ids['term']).results_published = True
        db.session.commit()
    # Released but not yet unlocked with a scratch card -> still hidden, prompting
    # the parent to unlock (new per-term scratch-card gate).
    gated = c.get(f'/parent/?term_id={ids["term"]}',
                  headers={'X-Requested-With': 'fetch'}).get_json()
    assert gated['report'] is None and not gated['results_ready'] and gated['needs_card']
    # A successful scratch-card check for this student+term unlocks it on the portal.
    with app.app_context():
        from models import ResultCheckLog
        db.session.add(ResultCheckLog(student_id=ids['a'], term_id=ids['term'],
                                      success=True, detail='test unlock'))
        db.session.commit()
    shown = c.get(f'/parent/?term_id={ids["term"]}',
                  headers={'X-Requested-With': 'fetch'}).get_json()
    assert shown['report'] is not None and shown['results_ready']     # unlocked -> visible
