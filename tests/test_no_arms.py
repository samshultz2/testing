"""Schools without class arms: a hidden default 'General' arm makes the app work
with bare class names (SSS1, SSS2, …) and no arm pickers."""
from config import Config
from models import (db, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, SchoolSettings)
from tests.conftest import login_token, auth_csrf


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_default_arm_is_omitted_from_display(app):
    with app.app_context():
        arm = ClassArm.default()
        assert arm.is_default is True and arm.name == 'General'
        assert ClassArm.default().id == arm.id            # idempotent

        ss = AcademicSession(name='NA 25/26'); db.session.add(ss); db.session.flush()
        t = Term(session_id=ss.id, term_number=1, name='First Term'); db.session.add(t); db.session.flush()
        sc = SchoolClass(name='SSS1-NA', level=4); db.session.add(sc); db.session.flush()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=t.id)
        db.session.add(caa); db.session.flush()
        assert caa.display_name == 'SSS1-NA'              # arm name omitted
        assert caa.full_display_name.startswith('SSS1-NA - ')

        # A real arm is still shown.
        real = ClassArm(name='Science-NA', is_active=True); db.session.add(real); db.session.flush()
        caa2 = ClassArmAssignment(class_id=sc.id, arm_id=real.id, term_id=t.id)
        db.session.add(caa2); db.session.flush()
        assert caa2.display_name == 'SSS1-NA Science-NA'


def test_add_assignment_without_arm_uses_default(app):
    c = _admin(app)
    with app.app_context():
        ss = AcademicSession(name='AA 25/26'); db.session.add(ss); db.session.flush()
        t = Term(session_id=ss.id, term_number=1, name='First Term'); db.session.add(t); db.session.flush()
        sc = SchoolClass(name='SSS2-AA', level=5); db.session.add(sc); db.session.flush()
        tid, cid = t.id, sc.id
        SchoolSettings.set('uses_class_arms', False, 'bool')      # arm-less school
        db.session.commit()

    # No arm_id in the form -> default arm, clean name.
    r = c.post('/academics/assignments/add', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'term_id': tid, 'class_id': cid})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        caa = ClassArmAssignment.query.filter_by(term_id=tid, class_id=cid).first()
        assert caa is not None and caa.arm.is_default is True
        assert caa.display_name == 'SSS2-AA'


def test_setup_all_classes_and_toggle(app):
    c = _admin(app)
    with app.app_context():
        ss = AcademicSession(name='SU 25/26'); db.session.add(ss); db.session.flush()
        t = Term(session_id=ss.id, term_number=1, name='First Term'); db.session.add(t); db.session.flush()
        for n, lvl in (('SU-A', 1), ('SU-B', 2)):
            db.session.add(SchoolClass(name=n, level=lvl, is_active=True))
        tid = t.id
        db.session.commit()
        n_active = SchoolClass.query.filter_by(is_active=True).count()

    # Turn arms off, then one-click set up every class for the term.
    c.post('/academics/uses-arms', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': auth_csrf(c), 'uses_arms': '0'})
    r = c.post('/academics/assignments/setup-all', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'term_id': tid})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    with app.app_context():
        assert SchoolSettings.get('uses_class_arms', True) is False
        arm = ClassArm.default()
        made = ClassArmAssignment.query.filter_by(term_id=tid, arm_id=arm.id).count()
        assert made == n_active                          # every active class got one
        # Re-running is idempotent (no duplicates).
    r2 = c.post('/academics/assignments/setup-all', headers={'X-Requested-With': 'fetch'},
                data={'_csrf_token': auth_csrf(c), 'term_id': tid})
    with app.app_context():
        arm = ClassArm.default()
        assert ClassArmAssignment.query.filter_by(term_id=tid, arm_id=arm.id).count() == n_active


def test_arms_list_hides_default(app):
    c = _admin(app)
    with app.app_context():
        ClassArm.default(); db.session.commit()
    r = c.get('/academics/arms', headers={'X-Requested-With': 'fetch'})
    names = [a['name'] for a in r.get_json()['arms']]
    assert 'General' not in names


def test_arms_mode_rejects_armless_assignment(app):
    """With arms ON (the default), you cannot create an armless assignment, so the
    default 'General' arm is never created for an arms school."""
    c = _admin(app)
    with app.app_context():
        SchoolSettings.set('uses_class_arms', True, 'bool')
        ss = AcademicSession(name='AM 25/26'); db.session.add(ss); db.session.flush()
        t = Term(session_id=ss.id, term_number=1, name='First Term'); db.session.add(t); db.session.flush()
        sc = SchoolClass(name='SSS3-AM', level=6); db.session.add(sc); db.session.flush()
        tid, cid = t.id, sc.id
        db.session.commit()

    r = c.post('/academics/assignments/add', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'term_id': tid, 'class_id': cid})   # no arm
    assert r.get_json()['ok'] is False                       # rejected — arm required
    # The bulk "set up all" is also gated to arm-less schools only.
    r2 = c.post('/academics/assignments/setup-all', headers={'X-Requested-With': 'fetch'},
                data={'_csrf_token': auth_csrf(c), 'term_id': tid})
    assert r2.get_json()['ok'] is False
    with app.app_context():
        assert ClassArmAssignment.query.filter_by(term_id=tid, class_id=cid).count() == 0


def test_academic_settings_page_toggles_arms(app):
    """The same toggle lives on Settings -> Academic (the discoverable home)."""
    c = _admin(app)
    r = c.post('/settings/academic', headers={'X-Requested-With': 'fetch'},
               data={'_csrf_token': auth_csrf(c), 'uses_class_arms': '0'})
    assert r.get_json()['ok'] is True
    with app.app_context():
        assert SchoolSettings.get('uses_class_arms', True) is False
        assert ClassArm.query.filter_by(is_default=True).first() is not None   # provisioned
    # The Academic settings payload reflects the saved value for the checkbox.
    g = c.get('/settings/academic', headers={'X-Requested-With': 'fetch'}).get_json()
    assert g['settings'].get('uses_class_arms') == 'false'
    c.post('/settings/academic', headers={'X-Requested-With': 'fetch'},
           data={'_csrf_token': auth_csrf(c), 'uses_class_arms': '1'})           # restore
    with app.app_context():
        assert SchoolSettings.get('uses_class_arms', True) is True
