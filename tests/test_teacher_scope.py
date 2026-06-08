"""Teacher scoping: attendance/parent-comms limited to the form class."""
from flask import session
from models import (db, Branch, User, Teacher, Student, Subject, SchoolClass,
                    ClassArm, ClassArmAssignment, StudentEnrollment,
                    TeacherClassAssignment, TeacherSubjectAssignment,
                    AcademicSession, Term)


def _setup(app):
    with app.app_context():
        existing = User.query.filter_by(username='ts_teacher').first()
        if existing:
            t = existing.teacher_profile
            form = list(t.form_class_ids)[0]
            subj = t.subject_assignments.first().class_arm_assignment_id
            st = Student.query.filter_by(student_id='TSF1').first()
            return dict(uid=existing.id, bid=existing.branch_id,
                        form=form, subj=subj, student=st.id)
        bid = Branch.get_default().id
        sess = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='TS', is_active=True)
        if sess.id is None:
            db.session.add(sess); db.session.flush()
        term = Term.query.filter_by(is_active=True).first() or \
            Term(session_id=sess.id, term_number=1, name='T1', is_active=True)
        if term.id is None:
            db.session.add(term); db.session.flush()
        classes = SchoolClass.query.order_by(SchoolClass.level).all()
        arm = ClassArm.query.first()
        # form class + a different subject-only class
        form_asg = ClassArmAssignment(class_id=classes[0].id, arm_id=arm.id,
                                      term_id=term.id, branch_id=bid)
        subj_asg = ClassArmAssignment(class_id=classes[1].id, arm_id=arm.id,
                                      term_id=term.id, branch_id=bid)
        db.session.add_all([form_asg, subj_asg]); db.session.flush()
        # a student in the form class
        st = Student(student_id='TSF1', first_name='Form', surname='Kid',
                     gender='Male', is_active=True, branch_id=bid)
        db.session.add(st); db.session.flush()
        db.session.add(StudentEnrollment(student_id=st.id,
                                         class_arm_assignment_id=form_asg.id, is_active=True))
        # the teacher
        u = User(username='ts_teacher', role='teacher', scope='branch', branch_id=bid)
        u.set_password('secret123'); db.session.add(u); db.session.flush()
        t = Teacher(user_id=u.id, employee_id='TS001', branch_id=bid,
                    can_mark_attendance=True)
        db.session.add(t); db.session.flush()
        subj = Subject.query.first() or Subject(name='Maths', is_active=True)
        if subj.id is None:
            db.session.add(subj); db.session.flush()
        db.session.add(TeacherClassAssignment(teacher_id=t.id,
                       class_arm_assignment_id=form_asg.id, is_form_teacher=True))
        db.session.add(TeacherSubjectAssignment(teacher_id=t.id,
                       class_arm_assignment_id=subj_asg.id, subject_id=subj.id))
        db.session.commit()
        return dict(uid=u.id, bid=bid, form=form_asg.id, subj=subj_asg.id, student=st.id)


def _as_teacher(app, ids):
    """Push a request context with the teacher 'logged in'."""
    ctx = app.test_request_context('/')
    ctx.push()
    session['logged_in'] = True
    session['user_id'] = ids['uid']
    session['role'] = 'teacher'
    session['scope'] = 'branch'
    session['branch_id'] = ids['bid']
    return ctx


def test_attendance_only_for_form_class(app):
    ids = _setup(app)
    from utils.access_control import can_mark_attendance
    ctx = _as_teacher(app, ids)
    try:
        assert can_mark_attendance(ids['form']) is True       # form class
        assert can_mark_attendance(ids['subj']) is False      # subject-only class
    finally:
        ctx.pop()


def test_results_still_allowed_for_subject_class(app):
    ids = _setup(app)
    from utils.access_control import can_enter_results
    with app.app_context():
        u = User.query.get(ids['uid'])
        u.teacher_profile.can_enter_results = True
        db.session.commit()
    ctx = _as_teacher(app, ids)
    try:
        # results entry is allowed in the subject class (subject-scoped elsewhere)
        assert can_enter_results(ids['subj']) is True
    finally:
        ctx.pop()


def test_form_student_ids(app):
    ids = _setup(app)
    from utils.access_control import teacher_form_student_ids
    ctx = _as_teacher(app, ids)
    try:
        assert teacher_form_student_ids() == {ids['student']}
    finally:
        ctx.pop()
