"""Grade-integrity guards on the shared score-write path (persist_scores):
publication lock, edit-permission for existing scores, range rejection, and an
audit trail. These are the anti-grade-tampering controls.
"""
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject,
                    ClassSubject, AssessmentType, StudentScore, User, Teacher)
from models.models.settings import AuditLog
from routes.subjects import persist_scores, results_locked
from tests.conftest import login_token


def _setup(app):
    with app.app_context():
        if Student.query.filter_by(student_id='SI1').first():
            t = Term.query.filter_by(name='SI-Term').first()
            caa = ClassArmAssignment.query.filter_by(term_id=t.id).first()
            cs = ClassSubject.query.filter_by(term_id=t.id).first()
            at = AssessmentType.query.filter_by(name='SI-Exam').first()
            a = Student.query.filter_by(student_id='SI1').first()
            return dict(term=t.id, asg=caa.id, cs=cs.id, sub=cs.subject_id, at=at.id, a=a.id)
        bid = Branch.get_default().id
        sess = AcademicSession(name='SI-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='SI-Term')
        db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject.query.first() or Subject(name='Maths', is_active=True)
        if subj.id is None:
            db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id,
                          term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        at = AssessmentType(name='SI-Exam', short_name='EXAM', max_score=100,
                            order=90, is_active=True)
        db.session.add(at); db.session.flush()
        a = Student(student_id='SI1', first_name='Aa', surname='One', gender='Male',
                    is_active=True, branch_id=bid)
        db.session.add(a); db.session.flush()
        db.session.add(StudentEnrollment(student_id=a.id, class_arm_assignment_id=caa.id,
                                         is_active=True))
        db.session.commit()
        return dict(term=term.id, asg=caa.id, cs=cs.id, sub=subj.id, at=at.id, a=a.id)


def _student(app, ids, sid):
    """A fresh enrolled student (tests share one session-scoped DB, so each test
    uses its own student to stay isolated)."""
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name=sid, surname='X', gender='Male',
                        is_active=True, branch_id=Branch.get_default().id)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=ids['asg'],
                                             is_active=True))
            db.session.commit()
        return s.id


def _mk_teacher(app, username, can_edit):
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, full_name=username, role='teacher',
                     scope='central', manage_scope='none')
            u.set_password('secret123'); db.session.add(u); db.session.flush()
            db.session.add(Teacher(user_id=u.id, employee_id=Teacher.generate_employee_id(),
                                   can_enter_results=True, can_edit_results=can_edit))
            db.session.commit()
        return u.id


def _set_published(app, term_id, val):
    with app.app_context():
        db.session.get(Term, term_id).results_published = val
        db.session.commit()


# --- publication lock -------------------------------------------------------
def test_published_term_blocks_non_admin_score_writes(app):
    ids = _setup(app)
    sid = _student(app, ids, 'SI_lock')
    _set_published(app, ids['term'], True)
    try:
        with app.test_request_context():
            # No session identity => treated as a non-admin.
            assert results_locked(ids['term']) is True
            res = persist_scores(ids['term'], ids['asg'], ids['cs'], ids['sub'],
                                 [(sid, ids['at'], '77', 100)])
            assert res is None                       # write refused
        with app.app_context():
            assert StudentScore.query.filter_by(student_id=sid).first() is None
    finally:
        _set_published(app, ids['term'], False)


def test_admin_can_edit_published_term(app):
    ids = _setup(app)
    sid = _student(app, ids, 'SI_adminpub')
    _set_published(app, ids['term'], True)
    try:
        with app.test_request_context():
            from flask import session
            session['logged_in'] = True; session['role'] = 'admin'
            assert results_locked(ids['term']) is False
            res = persist_scores(ids['term'], ids['asg'], ids['cs'], ids['sub'],
                                 [(sid, ids['at'], '77', 100)])
            assert res is not None and res['saved'] == 1
            db.session.commit()
        with app.app_context():
            assert StudentScore.query.filter_by(student_id=sid).first().score == 77
    finally:
        _set_published(app, ids['term'], False)


# --- range rejection --------------------------------------------------------
def test_out_of_range_scores_rejected(app):
    ids = _setup(app)
    sid = _student(app, ids, 'SI_range')
    with app.test_request_context():
        from flask import session
        session['logged_in'] = True; session['role'] = 'admin'
        res = persist_scores(ids['term'], ids['asg'], ids['cs'], ids['sub'], [
            (sid, ids['at'], '-5', 100),           # negative
            (sid, ids['at'], '150', 100),          # above max
        ])
        assert res['saved'] == 0 and res['rejected'] == 2
        db.session.commit()
    with app.app_context():
        assert StudentScore.query.filter_by(student_id=sid).first() is None


# --- edit-permission on existing scores -------------------------------------
def test_enter_only_teacher_cannot_change_existing_score(app):
    ids = _setup(app)
    sid = _student(app, ids, 'SI_enteronly')
    with app.app_context():                        # seed an existing score
        db.session.add(StudentScore(student_id=sid, class_subject_id=ids['cs'],
                                    assessment_type_id=ids['at'], score=40))
        db.session.commit()
    uid = _mk_teacher(app, 'si_enteronly', can_edit=False)
    with app.test_request_context():
        from flask import session
        session['logged_in'] = True; session['role'] = 'teacher'; session['user_id'] = uid
        res = persist_scores(ids['term'], ids['asg'], ids['cs'], ids['sub'],
                             [(sid, ids['at'], '95', 100)])
        assert res['blocked'] == 1 and res['saved'] == 0
        db.session.commit()
    with app.app_context():
        assert StudentScore.query.filter_by(student_id=sid).first().score == 40  # unchanged


# --- audit trail ------------------------------------------------------------
def test_score_change_is_audited(app):
    ids = _setup(app)
    sid = _student(app, ids, 'SI_audit')
    with app.test_request_context():
        from flask import session
        session['logged_in'] = True; session['role'] = 'admin'
        persist_scores(ids['term'], ids['asg'], ids['cs'], ids['sub'],
                       [(sid, ids['at'], '88', 100)])
        db.session.commit()
    with app.app_context():
        row = (AuditLog.query.filter_by(action='results.score_edit')
               .order_by(AuditLog.id.desc()).first())
        assert row is not None
        assert '→88' in row.detail
