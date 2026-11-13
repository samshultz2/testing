"""Score entry follows each subject's Midterm / practical setting: Theory is out
of 40 with a mid-term / practical and out of 50 without, and the P/ME column is
not shown (and can't be saved) for a subject without one — whatever stale
override rows say."""
import uuid

from config import Config
from models import (db, Student, Subject, ClassSubject, AssessmentType, AcademicSession, Term,
                    SchoolClass, ClassArm, ClassArmAssignment, StudentEnrollment, StudentScore,
                    SubjectAssessmentOverride)
from tests.conftest import login_token, auth_csrf


def _types():
    def get(short, name, mx, order):
        at = AssessmentType.query.filter_by(short_name=short).first()
        if not at:
            at = AssessmentType(name=name, short_name=short, max_score=mx, order=order, is_active=True)
            db.session.add(at); db.session.flush()
        return at
    return get('MID', 'Midterm', 10, 3), get('EXAM', 'Theory', 40, 6)


def _setup(app):
    from utils.assessments import subject_columns, is_theory, is_midterm
    tag = uuid.uuid4().hex[:5].upper()
    with app.app_context():
        mid, _ = _types()
        sess = AcademicSession(name='PR ' + tag); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First ' + tag); db.session.add(term); db.session.flush()
        cls = SchoolClass(name='PRC' + tag, level=55); db.session.add(cls); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True); db.session.add(arm); db.session.flush()
        asg = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id); db.session.add(asg); db.session.flush()
        st = Student(student_id='PR' + tag, surname='Prac' + tag, first_name='A', gender='Male', is_active=True)
        db.session.add(st); db.session.flush()
        db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=asg.id, is_active=True))
        maths = Subject(name='Maths ' + tag, has_practical=True)
        lit = Subject(name='Lit ' + tag, has_practical=False)
        db.session.add_all([maths, lit]); db.session.flush()
        theory = next(t for t in AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order, AssessmentType.id) if is_theory(t))
        mid = next(t for t in AssessmentType.query.filter_by(is_active=True).order_by(AssessmentType.order, AssessmentType.id) if is_midterm(t))
        # Stale overrides: Maths says Theory 50 (wrong), Lit has none at all.
        db.session.add(SubjectAssessmentOverride(subject_id=maths.id, assessment_type_id=theory.id, max_score=50))
        cs_m = ClassSubject(subject_id=maths.id, class_id=cls.id, term_id=term.id, is_active=True)
        cs_l = ClassSubject(subject_id=lit.id, class_id=cls.id, term_id=term.id, is_active=True)
        db.session.add_all([cs_m, cs_l]); db.session.commit()
        cols_m = {at.id: mx for at, mx in subject_columns(maths, term.id)}
        cols_l = {at.id: mx for at, mx in subject_columns(lit, term.id)}
        return dict(term=term.id, asg=asg.id, st=st.id, cs_m=cs_m.id, cs_l=cs_l.id,
                    theory=theory.id, mid=mid.id, cols_m=cols_m, cols_l=cols_l)


def test_columns_follow_the_practical_setting(app):
    x = _setup(app)
    assert x['cols_m'][x['theory']] == 40 and x['mid'] in x['cols_m']          # 40, P/ME shown
    assert x['cols_l'][x['theory']] == 50 and x['mid'] not in x['cols_l']      # 50, P/ME hidden


def test_entry_pages_enforce_40_50_and_hide_pme(app):
    x = _setup(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    tok = auth_csrf(c)
    base = {'_csrf_token': tok, 'term_id': x['term'], 'assignment_id': x['asg'], 'student_id[]': [x['st']]}

    def save(cs, at, v):
        c.post('/subjects/scores/save', data=dict(base, class_subject_id=cs, assessment_type_id=at, **{'score[]': [v]}))
        with app.app_context():
            s = StudentScore.query.filter_by(student_id=x['st'], class_subject_id=cs, assessment_type_id=at).first()
            return s.score if s else None
    assert save(x['cs_m'], x['theory'], '45') is None        # Maths (practical): over 40 → rejected
    assert save(x['cs_m'], x['theory'], '40') == 40
    assert save(x['cs_l'], x['theory'], '45') == 45          # Lit (no practical): up to 50
    assert save(x['cs_l'], x['mid'], '5') is None            # no P/ME for Lit

    # Whole-class page offers the subject's own columns; one-student entry too.
    q = f"term_id={x['term']}&assignment_id={x['asg']}"
    d = c.get(f"/subjects/scores?{q}&class_subject_id={x['cs_l']}", headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    ats = {a['id']: a['max_score'] for a in d['assessment_types']}
    assert x['mid'] not in ats and ats[x['theory']] == 50
    rows = c.get(f"/subjects/api/student-subject-scores?{q}&class_subject_id={x['cs_m']}&student_id={x['st']}").get_json()['rows']
    got = {r['assessment_type_id']: r['max_score'] for r in rows}
    assert got[x['theory']] == 40 and x['mid'] in got
    rows = c.get(f"/subjects/api/student-subject-scores?{q}&class_subject_id={x['cs_l']}&student_id={x['st']}").get_json()['rows']
    assert x['mid'] not in {r['assessment_type_id'] for r in rows}

    # Bulk grid: each subject carries its own columns.
    d = c.get(f"/subjects/bulk-entry?{q}", headers={'X-Requested-With': 'fetch'}).get_json()
    d = d.get('data', d)
    by = {cs['id']: {col['id']: col['max_score'] for col in cs['cols']} for cs in d['class_subjects']}
    assert by[x['cs_m']][x['theory']] == 40 and x['mid'] in by[x['cs_m']]
    assert by[x['cs_l']][x['theory']] == 50 and x['mid'] not in by[x['cs_l']]
