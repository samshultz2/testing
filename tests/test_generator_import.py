"""The generator can import the school's existing subjects/classes/teachers."""
import re
from config import Config
from models import (db, AcademicSession, Term, SchoolClass, ClassArm, ClassArmAssignment,
                    Subject, ClassSubject, Branch,
                    GenSubject, GenClassConfig, GenTeacher, GenClassSubjectConfig,
                    GenTeacherAssignment)
from tests.conftest import login_token


def _seed(app):
    with app.app_context():
        if ClassSubject.query.filter_by(teacher_name='Mr Bello').first():
            return
        bid = Branch.get_default().id
        sess = AcademicSession.query.filter_by(is_active=True).first() or AcademicSession(name='G', is_active=True)
        if sess.id is None: db.session.add(sess); db.session.flush()
        term = Term.query.filter_by(is_active=True).first() or Term(session_id=sess.id, term_number=1, name='GT', is_active=True)
        if term.id is None: db.session.add(term); db.session.flush()
        # a SENIOR class so it maps to 'sss'
        sc = SchoolClass(name='SSS1-G', level=4, section='senior', is_active=True)
        arm = ClassArm.query.first() or ClassArm(name='Rose', is_active=True)
        if arm.id is None: db.session.add(arm)
        db.session.add(sc); db.session.flush()
        db.session.add(ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid))
        subj = Subject(name='Further Maths G', is_active=True); db.session.add(subj); db.session.flush()
        db.session.add(ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id,
                                    term_id=term.id, is_active=True, teacher_name='Mr Bello'))
        db.session.commit()


def test_import_creates_gen_records(app):
    _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    pt = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                   c.get('/').get_data(as_text=True)).group(1)
    c.post('/generator/import-school-data', data={'_csrf_token': pt}, follow_redirects=True)
    with app.app_context():
        gs = GenSubject.query.filter_by(name='Further Maths G', school_level='sss').first()
        gc = GenClassConfig.query.filter_by(class_name='SSS1-G', school_level='sss').first()
        gt = GenTeacher.query.filter_by(name='Mr Bello', school_level='sss').first()
        assert gs and gc and gt
        assert GenClassSubjectConfig.query.filter_by(class_config_id=gc.id, subject_id=gs.id).first()
        assert GenTeacherAssignment.query.filter_by(teacher_id=gt.id, subject_id=gs.id,
                                                    class_config_id=gc.id).first()


def test_import_is_idempotent(app):
    _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    pt = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                   c.get('/').get_data(as_text=True)).group(1)
    c.post('/generator/import-school-data', data={'_csrf_token': pt}, follow_redirects=True)
    c.post('/generator/import-school-data', data={'_csrf_token': pt}, follow_redirects=True)
    with app.app_context():
        assert GenSubject.query.filter_by(name='Further Maths G', school_level='sss').count() == 1
        gc = GenClassConfig.query.filter_by(class_name='SSS1-G', school_level='sss').first()
        gs = GenSubject.query.filter_by(name='Further Maths G', school_level='sss').first()
        assert GenClassSubjectConfig.query.filter_by(class_config_id=gc.id, subject_id=gs.id).count() == 1


def test_import_then_generate_produces_timetable(app):
    """Guard the engine: import school data, then a generation run schedules slots."""
    import re as _re
    from models import GenClassConfig, GenTimetableResult
    _seed(app)
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    pt = _re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                    c.get('/').get_data(as_text=True)).group(1)
    c.post('/generator/import-school-data', data={'_csrf_token': pt})
    c.get('/generator/level/sss')   # set the working level
    with app.app_context():
        gc = GenClassConfig.query.filter_by(class_name='SSS1-G', school_level='sss').first()
        cid = gc.id
        before = GenTimetableResult.query.count()
    r = c.post('/generator/generate/run',
               data={'_csrf_token': pt, 'class_ids[]': str(cid)}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert GenTimetableResult.query.count() > before    # a timetable was produced
