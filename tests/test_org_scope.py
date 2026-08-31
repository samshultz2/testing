"""Stage 4: section & stream scoping within a branch."""
import re

from models import db, Student, User, SchoolClass, ClassArm, ClassArmAssignment, \
    StudentEnrollment, AcademicSession, Term
from tests.conftest import login_token


def _login(app, username, password='secret123'):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'username': username, 'password': password,
                                '_csrf_token': token})
    return client


def _enrol(student, section_name, branch_id):
    """Enrol a student into a class of the given section for the active term."""
    sess = AcademicSession.query.filter_by(is_active=True).first()
    if not sess:
        sess = AcademicSession(name='S', is_active=True); db.session.add(sess); db.session.flush()
    term = Term.query.filter_by(is_active=True).first()
    if not term:
        term = Term(session_id=sess.id, term_number=1, name='T1', is_active=True)
        db.session.add(term); db.session.flush()
    cls = SchoolClass.query.filter_by(section=section_name).first()
    arm = ClassArm.query.first() or ClassArm(name='A')
    if arm.id is None:
        db.session.add(arm); db.session.flush()
    asg = (ClassArmAssignment.query
           .filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first())
    if not asg:
        asg = ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id,
                                 branch_id=branch_id)
        db.session.add(asg); db.session.flush()
    db.session.add(StudentEnrollment(student_id=student.id,
                                     class_arm_assignment_id=asg.id, is_active=True))


def _setup_sections(app):
    with app.app_context():
        from models import Branch
        bid = Branch.get_default().id
        snr = Student.query.filter_by(student_id='SECSNR').first()
        if not snr:
            snr = Student(student_id='SECSNR', first_name='Sen', surname='Ior',
                          gender='Male', is_active=True, branch_id=bid, stream='Science')
            db.session.add(snr); db.session.flush()
            _enrol(snr, 'senior', bid)
        jnr = Student.query.filter_by(student_id='SECJNR').first()
        if not jnr:
            jnr = Student(student_id='SECJNR', first_name='Jun', surname='Ior',
                          gender='Male', is_active=True, branch_id=bid)
            db.session.add(jnr); db.session.flush()
            _enrol(jnr, 'junior', bid)
        if not User.query.filter_by(username='headmaster1').first():
            u = User(username='headmaster1', role='staff', full_name='HM',
                     scope='branch', branch_id=bid, section='primary')
            u.set_password('secret123'); u.set_modules(['students']); db.session.add(u)
        if not User.query.filter_by(username='hodsci').first():
            u2 = User(username='hodsci', role='staff', full_name='HOD Sci',
                      scope='branch', branch_id=bid, stream='science')
            u2.set_password('secret123'); u2.set_modules(['students']); db.session.add(u2)
        db.session.commit()


def test_section_filter_hides_other_section(app):
    """A 'primary' headmaster sees neither junior nor senior secondary students."""
    _setup_sections(app)
    client = _login(app, 'headmaster1')
    html = client.get('/students').get_data(as_text=True)
    assert 'SECSNR' not in html and 'SECJNR' not in html  # both are secondary


def test_stream_filter_limits_students(app):
    """A science HOD sees only Science-stream students."""
    _setup_sections(app)
    client = _login(app, 'hodsci')
    html = client.get('/students').get_data(as_text=True)
    assert 'SECSNR' in html      # Science stream
    assert 'SECJNR' not in html  # no stream
