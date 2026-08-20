"""The class (form) teacher name on a class-arm assignment can be corrected
after the fact — a misspelling or the wrong teacher — via the edit-teacher route.
"""
from config import Config
from tests.conftest import login_token, auth_csrf


def _assignment(app):
    from models import (db, ClassArmAssignment, SchoolClass, ClassArm, Term,
                        AcademicSession)
    with app.app_context():
        sc = SchoolClass.query.first() or SchoolClass(name='ATE-Cls', level=1)
        db.session.add(sc); db.session.flush()
        # Always use a fresh arm so the (class, arm, term) unique combo can never
        # collide with an assignment another test already inserted.
        arm = ClassArm(name='ATE-Arm-EDIT', is_active=True)
        db.session.add(arm); db.session.flush()
        term = Term.query.first()
        if not term:
            s = AcademicSession(name='2099/2100', is_active=True)
            db.session.add(s); db.session.flush()
            term = Term(session_id=s.id, term_number=1, name='T1', is_active=True)
            db.session.add(term); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id,
                                 form_teacher_name='Msiplet Naem')   # wrong spelling
        db.session.add(caa); db.session.commit()
        return caa.id


def test_edit_class_teacher_name(app):
    from models import db, ClassArmAssignment
    caa_id = _assignment(app)
    try:
        c = app.test_client()
        c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
        r = c.post(f'/academics/assignments/{caa_id}/edit-teacher',
                   data={'form_teacher': 'Correct Name', '_csrf_token': auth_csrf(c)})
        assert r.status_code in (200, 302, 303)
        with app.app_context():
            assert db.session.get(ClassArmAssignment, caa_id).form_teacher_name == 'Correct Name'
    finally:
        with app.app_context():
            o = db.session.get(ClassArmAssignment, caa_id)
            if o:
                db.session.delete(o); db.session.commit()
