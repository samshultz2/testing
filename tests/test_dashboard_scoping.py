"""Dashboard reflects only what the user is permitted to see:
- cards are gated by module permission (a user without finance access never
  gets the finance widget/stat);
- a teacher's headline student counts cover only their own classes.
"""
from flask import session
from models import (db, Branch, User, Teacher, Student, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, TeacherClassAssignment,
                    AcademicSession, Term)


def test_widget_gated_by_permission(app):
    """A staff user with only 'students' access doesn't get the finance card."""
    with app.app_context():
        if not User.query.filter_by(username='dsc_staff').first():
            u = User(username='dsc_staff', role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name='Dsc Staff')
            u.set_password('secret123')
            u.set_permissions({'students': 'edit'})
            db.session.add(u); db.session.commit()
        uid = User.query.filter_by(username='dsc_staff').first().id

    from routes.main import enabled_widgets, permitted_widgets
    with app.test_request_context('/'):
        session['logged_in'] = True
        session['user_id'] = uid
        session['role'] = 'staff'
        permitted = permitted_widgets()
        assert 'kpi' in permitted              # has students module
        assert 'finance' not in permitted      # no finance module
        assert 'hr' not in permitted
        assert 'finance' not in enabled_widgets()


def test_teacher_widgets_scoped_to_own_students(app):
    """Birthdays/age/religion/stream/recent-students on a teacher's dashboard
    cover only their own students — not the whole branch (e.g. an SSS2 form
    teacher must not see SSS3 students' birthdays)."""
    from datetime import date
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name='TWS-Session'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='TWS-Term', is_active=True)
        db.session.add(term); db.session.flush()
        classes = SchoolClass.query.order_by(SchoolClass.level).all()
        arm = ClassArm.query.first()
        mine = ClassArmAssignment(class_id=classes[0].id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        other = ClassArmAssignment(class_id=classes[1].id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add_all([mine, other]); db.session.flush()
        today = date.today()
        s_mine = Student(student_id='TWS_M', first_name='Mine', surname='Kid', gender='Male',
                         is_active=True, branch_id=bid, religion='Christianity', stream='Science',
                         date_of_birth=date(2008, today.month, today.day))
        s_other = Student(student_id='TWS_O', first_name='Other', surname='Kid', gender='Female',
                          is_active=True, branch_id=bid, religion='Islam', stream='Arts',
                          date_of_birth=date(2007, today.month, today.day))
        db.session.add_all([s_mine, s_other]); db.session.flush()
        db.session.add_all([
            StudentEnrollment(student_id=s_mine.id, class_arm_assignment_id=mine.id, is_active=True),
            StudentEnrollment(student_id=s_other.id, class_arm_assignment_id=other.id, is_active=True),
        ])
        u = User(username='tws_teacher', role='teacher', scope='branch', branch_id=bid)
        u.set_password('secret123'); db.session.add(u); db.session.flush()
        t = Teacher(user_id=u.id, employee_id='TWS001', branch_id=bid)
        db.session.add(t); db.session.flush()
        db.session.add(TeacherClassAssignment(teacher_id=t.id,
                       class_arm_assignment_id=mine.id, is_form_teacher=True))
        db.session.commit()
        uid = u.id
    try:
        from routes.main import dashboard_payload
        from utils.branch_scope import set_session_scope
        from utils.org_scope import set_session_org
        with app.test_request_context('/'):
            u = db.session.get(User, uid)
            session['logged_in'] = True
            session['user_id'] = uid
            session['role'] = 'teacher'
            set_session_scope(u)
            set_session_org(u)
            p = dashboard_payload()
            assert p['total_students'] == 1
            assert p['religion_stats'] == {'Christianity': 1}      # not Islam (other class)
            assert p['stream_dist'].get('Science') == 1 and 'Arts' not in p['stream_dist']
            bday_names = {b['full_name'] for b in p['birthdays_today']}
            assert bday_names == {'Kid Mine'}                       # only their student, not the other class
            assert all('Other' not in s['full_name'] for s in p['recent_students'])
    finally:
        with app.app_context():
            t = Term.query.filter_by(name='TWS-Term').first()
            if t:
                t.is_active = False
                db.session.commit()


def test_teacher_counts_only_own_class(app):
    """A teacher's total_students counts only students in their classes."""
    with app.app_context():
        bid = Branch.get_default().id
        sess = AcademicSession(name='DSC-Session'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='DSC-Term', is_active=True)
        db.session.add(term); db.session.flush()
        classes = SchoolClass.query.order_by(SchoolClass.level).all()
        arm = ClassArm.query.first()
        mine = ClassArmAssignment(class_id=classes[0].id, arm_id=arm.id,
                                  term_id=term.id, branch_id=bid)
        other = ClassArmAssignment(class_id=classes[1].id, arm_id=arm.id,
                                   term_id=term.id, branch_id=bid)
        db.session.add_all([mine, other]); db.session.flush()
        # one student in my class, two in the other class
        s_mine = Student(student_id='DSC_M', first_name='Mine', surname='Kid',
                         gender='Male', is_active=True, branch_id=bid)
        s_o1 = Student(student_id='DSC_O1', first_name='Oth', surname='One',
                       gender='Female', is_active=True, branch_id=bid)
        s_o2 = Student(student_id='DSC_O2', first_name='Oth', surname='Two',
                       gender='Male', is_active=True, branch_id=bid)
        db.session.add_all([s_mine, s_o1, s_o2]); db.session.flush()
        db.session.add_all([
            StudentEnrollment(student_id=s_mine.id, class_arm_assignment_id=mine.id, is_active=True),
            StudentEnrollment(student_id=s_o1.id, class_arm_assignment_id=other.id, is_active=True),
            StudentEnrollment(student_id=s_o2.id, class_arm_assignment_id=other.id, is_active=True),
        ])
        u = User(username='dsc_teacher', role='teacher', scope='branch', branch_id=bid)
        u.set_password('secret123'); db.session.add(u); db.session.flush()
        t = Teacher(user_id=u.id, employee_id='DSC001', branch_id=bid)
        db.session.add(t); db.session.flush()
        db.session.add(TeacherClassAssignment(teacher_id=t.id,
                       class_arm_assignment_id=mine.id, is_form_teacher=True))
        db.session.commit()
        uid = u.id

    try:
        from routes.main import _teacher_scope, _dash_student_counts, _dash_class_stats
        from utils.branch_scope import set_session_scope
        from utils.org_scope import set_session_org
        with app.test_request_context('/'):
            u = db.session.get(User, uid)
            session['logged_in'] = True
            session['user_id'] = uid
            session['role'] = 'teacher'
            set_session_scope(u)   # sets branch scope like a real login
            set_session_org(u)
            active_term = Term.query.filter_by(name='DSC-Term').first()
            tscope = _teacher_scope()
            counts = _dash_student_counts(tscope)
            assert counts['total_students'] == 1          # only their class's student
            assert counts['male_students'] == 1 and counts['female_students'] == 0
            active_enr, n_classes, class_stats = _dash_class_stats(active_term, tscope)
            assert n_classes == 1                          # only their class shown
            assert active_enr == 1
            assert [cs['total'] for cs in class_stats] == [1]
    finally:
        with app.app_context():
            t = Term.query.filter_by(name='DSC-Term').first()
            if t:
                t.is_active = False
                db.session.commit()


def _staff_with(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name=username)
            u.set_password('secret123')
            u.set_permissions(perms)
            db.session.add(u); db.session.commit()
        return User.query.filter_by(username=username).first().id


def test_quick_actions_are_permission_aware(app):
    """Dashboard quick actions only offer what the role can actually do, so no
    user is shown a shortcut that 403s on click."""
    from routes.main import dashboard_payload
    fin_id = _staff_with(app, 'qa_bursar', {'finance': 'edit'})
    stu_id = _staff_with(app, 'qa_teacher', {'students': 'edit'})

    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = fin_id; session['role'] = 'staff'
        p = dashboard_payload()
        labels = {a['label'] for a in p['quick_actions']}
        assert 'Record Payment' in labels and 'Defaulters' in labels
        assert 'Add Student' not in labels and 'Enter Scores' not in labels
        # finance-only staff land finance-first
        assert p['home_focus'] == 'finance'

    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = stu_id; session['role'] = 'staff'
        p = dashboard_payload()
        labels = {a['label'] for a in p['quick_actions']}
        assert 'Add Student' in labels
        assert 'Record Payment' not in labels
        assert p['home_focus'] is None      # has an academic module → normal dashboard


def test_quick_actions_suppressed_for_view_only(app):
    """A view-only user gets no write shortcuts (e.g. no Add Student)."""
    from routes.main import dashboard_payload
    vid = _staff_with(app, 'qa_viewer', {'students': 'view'})
    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = vid; session['role'] = 'staff'
        labels = {a['label'] for a in dashboard_payload()['quick_actions']}
        assert 'Add Student' not in labels   # view level → no write action
