"""Cross-class / cross-arm results explorer (/subjects/broadsheet/explore).

Seeds two class-arms in one term that share a subject, each with a scored
student, then checks the endpoint unifies them keyed by the shared Subject and
groups the scope options / metadata correctly.
"""
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Subject, ClassSubject, AssessmentType,
                    Student, StudentEnrollment, StudentScore)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


_SEQ = [0]


def _seed(app):
    """Two classes, one arm each, both offering one shared subject. One student
    per class with a subject score (A=80, B=40). Uniquely tagged per call so the
    session-scoped test DB doesn't collide between tests."""
    with app.app_context():
        _SEQ[0] += 1
        u = f'EXP{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{u}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name=f'{u}-Term'); db.session.add(term); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        if arm.id is None:
            db.session.add(arm); db.session.flush()
        subj = Subject(name=f'{u}-Maths', short_name='EMAT', is_active=True)
        db.session.add(subj); db.session.flush()
        at = AssessmentType(name=f'{u}-Exam', short_name='EXAM', max_score=100,
                            order=91, is_active=True)
        db.session.add(at); db.session.flush()

        out = {'term': term.id, 'subject': subj.id, 'scopes': [], 'students': {},
               'class_names': []}
        for label, score in ((f'{u}-A', 80), (f'{u}-B', 40)):
            tag = label
            out['class_names'].append(tag)
            cls = SchoolClass(name=tag, level=6, is_active=True); db.session.add(cls); db.session.flush()
            caa = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            cs = ClassSubject(subject_id=subj.id, class_id=cls.id, arm_id=arm.id,
                              term_id=term.id, is_active=True); db.session.add(cs); db.session.flush()
            st = Student(student_id=f'{tag}-1', first_name=tag, surname='S', gender='Male',
                         is_active=True, branch_id=bid); db.session.add(st); db.session.flush()
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
            db.session.add(StudentScore(student_id=st.id, class_subject_id=cs.id,
                                        assessment_type_id=at.id, score=score))
            out['scopes'].append(caa.id)
            out['students'][st.full_name] = score
        db.session.commit()
        return out


def test_explore_unifies_two_classes(app):
    ids = _seed(app)
    c = _admin(app)
    scopes = ','.join(str(s) for s in ids['scopes'])
    j = c.get(f"/subjects/broadsheet/explore?term_id={ids['term']}&scopes={scopes}",
              headers={'Accept': 'application/json'}).get_json()
    assert j['page'] == 'explore'
    # both scopes present in meta
    assert {m['assignment_id'] for m in j['scope_meta']} == set(ids['scopes'])
    # the shared subject appears once in the union
    maths = [s for s in j['subjects_union'] if s['id'] == ids['subject']]
    assert len(maths) == 1
    # both students present, each carrying their Maths total under the shared id
    by_name = {r['student']: r for r in j['rows']}
    assert set(by_name) >= set(ids['students'])
    for name, score in ids['students'].items():
        assert by_name[name]['subjects'][str(ids['subject'])] == score
        assert by_name[name]['average'] == score           # single subject → avg == total


def test_explore_scope_options_grouped_by_class(app):
    ids = _seed(app)
    c = _admin(app)
    j = c.get(f"/subjects/broadsheet/explore?term_id={ids['term']}",
              headers={'Accept': 'application/json'}).get_json()
    names = {o['class_name'] for o in j['scope_options']}
    assert set(ids['class_names']) <= names
    # with no scopes selected there are no rows yet
    assert j['rows'] == []


def test_explore_rejects_inaccessible_scope_for_teacher(app):
    """A scope the user can't access is silently dropped (no rows leak)."""
    ids = _seed(app)
    from models import User, Teacher
    with app.app_context():
        if not User.query.filter_by(username='exp_teacher').first():
            u = User(username='exp_teacher', full_name='Exp Teacher', role='teacher',
                     scope='central', manage_scope='none')
            u.set_password('secret123'); db.session.add(u); db.session.flush()
            db.session.add(Teacher(user_id=u.id, employee_id=Teacher.generate_employee_id(),
                                   can_enter_results=True))
            db.session.commit()
    c = app.test_client()
    c.post('/login', data={'username': 'exp_teacher', 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    scopes = ','.join(str(s) for s in ids['scopes'])
    j = c.get(f"/subjects/broadsheet/explore?term_id={ids['term']}&scopes={scopes}",
              headers={'Accept': 'application/json'}).get_json()
    # teacher isn't assigned these classes → scopes dropped, no student rows
    assert j['rows'] == []
