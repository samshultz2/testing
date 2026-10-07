"""Sub-section permissions (e.g. Finance: payments but not expenses)."""
import re
from models import db, User, Expense
from tests.conftest import login_token


def _make(app, username, perms):
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='staff', scope='central', full_name=username)
            u.set_password('secret123'); u.set_permissions(perms)
            db.session.add(u); db.session.commit()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'secret123',
                           '_csrf_token': login_token(c)})
    return c


def _ptoken(c):
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                  c.get('/').get_data(as_text=True))
    return m.group(1) if m else None


def test_granular_finance_access(app):
    _make(app, 'fpart', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'fpart')
    # granted sub-sections reachable
    assert c.get('/finance/payments').status_code == 200          # payments (edit)
    assert c.get('/finance/expenses').status_code == 200          # expenses (view)
    # ungranted sub-section blocked
    assert c.get('/finance/defaulters', follow_redirects=False).status_code in (302, 303)


def test_view_subsection_blocks_write(app):
    _make(app, 'fpart2', {'finance.payments': 'edit', 'finance.expenses': 'view'})
    c = _login(app, 'fpart2')
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add',
           data={'description': 'Tape', 'amount': 300, '_csrf_token': _ptoken(c)},
           follow_redirects=True)
    with app.app_context():
        assert Expense.query.count() == before        # expenses is view-only -> blocked


def test_subsection_level_helper(app):
    from flask import session
    from utils.access_control import subsection_level, module_level
    _make(app, 'fpart3', {'finance.payments': 'edit'})
    with app.app_context():
        uid = User.query.filter_by(username='fpart3').first().id
    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = uid
        session['role'] = 'staff'; session['scope'] = 'central'
        assert subsection_level('finance', 'payments') == 'edit'
        assert subsection_level('finance', 'expenses') is None   # not granted
        assert module_level('finance') == 'edit'                 # module visible


def test_results_subsection_scoping(app):
    # WAEC/JAMB live under the 'external_exams' module (blueprint 'results').
    _make(app, 'rwaec', {'external_exams.waec_view': 'view'})
    c = _login(app, 'rwaec')
    assert c.get('/results/waec').status_code == 200                       # waec_view granted
    assert c.get('/results/jamb', follow_redirects=False).status_code in (302, 303)  # jamb not granted


# --- admissions partition ---------------------------------------------------
def _an_applicant(app, app_no='TSTADM001'):
    from models import Applicant
    with app.app_context():
        a = Applicant.query.filter_by(application_no=app_no).first()
        if not a:
            a = Applicant(application_no=app_no, first_name='Amara', surname='Okoye', gender='Female')
            db.session.add(a); db.session.commit()
        return a.id


def test_admissions_view_create_but_not_delete_or_convert(app):
    from models import Applicant
    aid = _an_applicant(app, 'TSTADM001')
    _make(app, 'adm_vc', {'admissions.view': 'edit', 'admissions.create': 'edit'})
    c = _login(app, 'adm_vc')
    assert c.get('/admissions/').status_code == 200
    assert c.get('/admissions/applicants').status_code == 200
    assert c.get('/admissions/applicants/add').status_code == 200
    token = _ptoken(c)
    # 'delete' and 'convert' are separate slices -- neither was granted, so
    # both are blocked by the generic subsection gate (redirect -> dashboard,
    # not the applicant-specific error redirect a validation failure would use).
    r = c.post(f'/admissions/applicants/{aid}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers['Location'].rstrip('/') == ''
    r2 = c.post(f'/admissions/applicants/{aid}/convert', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303) and r2.headers['Location'].rstrip('/') == ''
    with app.app_context():
        assert db.session.get(Applicant, aid) is not None   # untouched


def test_admissions_delete_slice_allows_delete_but_not_convert(app):
    from models import Applicant
    aid = _an_applicant(app, 'TSTADM002')
    _make(app, 'adm_del', {'admissions.view': 'edit', 'admissions.delete': 'edit'})
    c = _login(app, 'adm_del')
    token = _ptoken(c)
    r = c.post(f'/admissions/applicants/{aid}/convert', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers['Location'].rstrip('/') == ''
    r2 = c.post(f'/admissions/applicants/{aid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303) and r2.headers['Location'].rstrip('/') != ''
    with app.app_context():
        assert db.session.get(Applicant, aid) is None       # delete went through


def test_admissions_download_slice(app):
    _make(app, 'adm_nodl', {'admissions.view': 'edit'})
    c = _login(app, 'adm_nodl')
    r = c.get('/admissions/applicants/blank-form.pdf', follow_redirects=False)
    assert r.status_code in (302, 303)
    _make(app, 'adm_dl', {'admissions.view': 'edit', 'admissions.download': 'edit'})
    c2 = _login(app, 'adm_dl')
    r2 = c2.get('/admissions/applicants/blank-form.pdf')
    assert r2.status_code == 200


# --- the permission_map override-narrowing bug fix --------------------------
def test_group_override_narrows_whole_module_grant(app):
    """A per-user 'none' override on one sub-key (students.purge) must block
    just that slice even when access otherwise comes from a whole-module
    group grant ('students': 'edit') -- not silently no-op because the group
    grant never literally contains the 'students.purge' key to pop."""
    from models import PermissionGroup
    from utils.access_control import MODULE_SUBSECTIONS
    with app.app_context():
        grp = PermissionGroup(name='StudentsFullTest')
        grp.set_permissions({'students': 'edit'})
        db.session.add(grp); db.session.commit()
        u = User.query.filter_by(username='narrow_whole').first()
        if not u:
            u = User(username='narrow_whole', role='staff', full_name='Narrow Whole')
            u.set_password('secret123')
            db.session.add(u)
        u.permission_group_id = grp.id
        u.set_permissions({'students.purge': 'none'})
        db.session.commit()
        pm = u.permission_map
        assert pm.get('students.purge') is None
        for sub in MODULE_SUBSECTIONS['students']:
            if sub == 'purge':
                continue
            assert pm.get(f'students.{sub}') == 'edit'


def test_group_override_narrowing_blocks_endpoint(app):
    """End-to-end: the same whole-module-grant + one-slice-revoked user is
    actually blocked server-side on the revoked slice, not just in the map."""
    from models import PermissionGroup, Student
    with app.app_context():
        grp = PermissionGroup(name='StudentsFullTest2')
        grp.set_permissions({'students': 'edit'})
        db.session.add(grp); db.session.commit()
        u = User.query.filter_by(username='narrow_whole2').first()
        if not u:
            u = User(username='narrow_whole2', role='staff', full_name='Narrow Whole 2')
            u.set_password('secret123')
            db.session.add(u)
        u.permission_group_id = grp.id
        u.set_permissions({'students.purge': 'none'})
        db.session.commit()
        s = Student.query.filter_by(student_id='TSTNRW01').first()
        if not s:
            s = Student(student_id='TSTNRW01', first_name='Nar', surname='Row',
                        gender='Male', is_active=False)
            db.session.add(s); db.session.commit()
        sid = s.id
    c = _login(app, 'narrow_whole2')
    token = _ptoken(c)
    # the module grant still covers everything else -- e.g. restore
    r = c.post(f'/students/{sid}/restore', data={'_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303, 200)
    with app.app_context():
        Student.query.filter_by(id=sid).update({'is_active': False})
        db.session.commit()
    # but the revoked slice is blocked
    r2 = c.post(f'/students/{sid}/purge', data={'_csrf_token': token}, follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert Student.query.filter_by(id=sid).first() is not None   # not purged


def test_bulk_delete_students_reachable_by_delete_slice(app):
    """bulk_delete_students used to be hard-walled to @admin_required,
    bypassing the granular 'students.delete' grant entirely. It's now
    reachable (and branch/teacher-scoped) like the single delete_student."""
    from models import Student
    with app.app_context():
        s = Student.query.filter_by(student_id='TSTBLK01').first()
        if not s:
            s = Student(student_id='TSTBLK01', first_name='Bulk', surname='One', gender='Male')
            db.session.add(s); db.session.commit()
        sid = s.id
    _make(app, 'bulk_del', {'students.roster': 'edit', 'students.delete': 'edit'})
    c = _login(app, 'bulk_del')
    token = _ptoken(c)
    r = c.post('/students/bulk-delete', data={'student_ids': [str(sid)], '_csrf_token': token})
    assert r.status_code == 200
    assert r.get_json()['deleted'] == 1
    with app.app_context():
        assert Student.query.filter_by(id=sid).first().is_active is False


# --- academics partition (Phase 1 of the module-by-module rollout) ---------
def test_academics_structure_create_without_view_edit_or_delete(app):
    from models import AcademicSession
    _make(app, 'acad_create', {'academics.structure_create': 'edit'})
    c = _login(app, 'acad_create')
    assert c.get('/academics/sessions/add').status_code == 200
    token = _ptoken(c)
    r = c.post('/academics/sessions/add', data={'name': 'ACST-Sess', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='ACST-Sess').first()
        assert sess is not None
        sid = sess.id
    # 'structure_view'/'structure_edit' are separate slices -> blocked
    assert c.get('/academics/classes', follow_redirects=False).status_code in (302, 303)
    assert c.get(f'/academics/sessions/{sid}/edit', follow_redirects=False).status_code in (302, 303)


def test_academics_holidays_create_without_delete(app):
    from models import AcademicSession, Term, Holiday
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='ACHOL-Sess').first()
        if not sess:
            sess = AcademicSession(name='ACHOL-Sess'); db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='ACHOL-Term')
            db.session.add(term); db.session.commit()
        else:
            term = Term.query.filter_by(session_id=sess.id).first()
        term_id = term.id
    _make(app, 'acad_hol', {'academics.holidays_create': 'edit'})
    c = _login(app, 'acad_hol')
    token = _ptoken(c)
    r = c.post(f'/academics/terms/{term_id}/holidays/add',
               data={'date': '2030-01-01', 'reason': 'Test Holiday', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        hol = Holiday.query.filter_by(term_id=term_id, reason='Test Holiday').first()
        assert hol is not None
        hol_id = hol.id
    r2 = c.post(f'/academics/holidays/{hol_id}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Holiday, hol_id) is not None   # delete not granted -> untouched


def test_academics_enrollment_create_without_edit_or_delete(app):
    from models import (Branch, AcademicSession, Term, SchoolClass, ClassArm,
                        ClassArmAssignment, Student, StudentEnrollment)
    with app.app_context():
        sess = AcademicSession.query.filter_by(name='ACENR-Sess').first()
        if not sess:
            bid = Branch.get_default().id
            sess = AcademicSession(name='ACENR-Sess'); db.session.add(sess); db.session.flush()
            term = Term(session_id=sess.id, term_number=1, name='ACENR-Term')
            db.session.add(term); db.session.flush()
            sc = SchoolClass.query.first(); arm = ClassArm.query.first()
            caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
            db.session.add(caa); db.session.flush()
            s = Student(student_id='ACENR1', first_name='Acenr', surname='One',
                        gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.commit()
            caa_id, sid = caa.id, s.id
        else:
            term = Term.query.filter_by(session_id=sess.id).first()
            caa_id = ClassArmAssignment.query.filter_by(term_id=term.id).first().id
            sid = Student.query.filter_by(student_id='ACENR1').first().id
    _make(app, 'acad_enr', {'academics.enrollment_create': 'edit'})
    c = _login(app, 'acad_enr')
    token = _ptoken(c)
    r = c.post(f'/academics/assignments/{caa_id}/enroll',
               data={'student_ids[]': [str(sid)], '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        en = StudentEnrollment.query.filter_by(
            student_id=sid, class_arm_assignment_id=caa_id, is_active=True).first()
        assert en is not None
        en_id = en.id
    # 'enrollment_delete' not granted -> removing the enrolment is blocked
    r2 = c.post(f'/academics/enrollments/{en_id}/remove', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert StudentEnrollment.query.filter_by(id=en_id, is_active=True).first() is not None


# --- events partition -------------------------------------------------------
def test_events_create_without_edit_delete_or_import(app):
    from models import SchoolEvent
    _make(app, 'ev_create', {'events.create': 'edit'})
    c = _login(app, 'ev_create')
    assert c.get('/events/add').status_code == 200
    token = _ptoken(c)
    r = c.post('/events/add', data={'title': 'Test Event', 'start_date': '2030-01-01',
                                     '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        ev = SchoolEvent.query.filter_by(title='Test Event').first()
        assert ev is not None
        ev_id = ev.id
    assert c.get(f'/events/{ev_id}/edit', follow_redirects=False).status_code in (302, 303)
    assert c.get('/events/import', follow_redirects=False).status_code in (302, 303)
    r2 = c.post(f'/events/{ev_id}/delete', data={'_csrf_token': token}, follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(SchoolEvent, ev_id) is not None   # delete not granted -> untouched


# --- external_exams partition (Phase 2: core WAEC/JAMB/Cutoffs/Predictions) -
def _a_waec_result(app, sid='EXWAEC01', year=2024):
    from models import Student, WAECResult
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Ext', surname='Waec', gender='Male')
            db.session.add(s); db.session.flush()
            db.session.add(WAECResult(student_id=s.id, exam_year=year, subject='English', grade='B2'))
            db.session.commit()
        return s.id


def _a_jamb_result(app, sid='EXJAMB01', year=2024):
    from models import Student, JAMBResult
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Ext', surname='Jamb', gender='Male')
            db.session.add(s); db.session.flush()
            db.session.add(JAMBResult(student_id=s.id, exam_year=year, total_score=250))
            db.session.commit()
        return s.id


def test_waec_create_without_edit_or_delete(app):
    from models import WAECResult
    sid = _a_waec_result(app, 'EXWAEC01')
    _make(app, 'waec_create_only', {'external_exams.waec_create': 'edit'})
    c = _login(app, 'waec_create_only')
    assert c.get('/results/waec/add').status_code == 200
    # 'waec_edit'/'waec_delete' are separate slices -> blocked
    assert c.get(f'/results/waec/student/{sid}/edit/2024', follow_redirects=False).status_code in (302, 303)
    token = _ptoken(c)
    r = c.post(f'/results/waec/student/{sid}/delete/2024', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert WAECResult.query.filter_by(student_id=sid, exam_year=2024).first() is not None


def test_waec_edit_without_delete(app):
    from models import WAECResult
    sid = _a_waec_result(app, 'EXWAEC02')
    _make(app, 'waec_edit_only', {'external_exams.waec_view': 'edit', 'external_exams.waec_edit': 'edit'})
    c = _login(app, 'waec_edit_only')
    assert c.get(f'/results/waec/student/{sid}/edit/2024').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/results/waec/student/{sid}/delete/2024', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert WAECResult.query.filter_by(student_id=sid, exam_year=2024).first() is not None   # untouched


def test_jamb_create_without_edit_or_delete(app):
    from models import JAMBResult
    sid = _a_jamb_result(app, 'EXJAMB01')
    _make(app, 'jamb_create_only', {'external_exams.jamb_create': 'edit'})
    c = _login(app, 'jamb_create_only')
    assert c.get('/results/jamb/add').status_code == 200
    assert c.get(f'/results/jamb/student/{sid}/edit/2024', follow_redirects=False).status_code in (302, 303)
    token = _ptoken(c)
    r = c.post(f'/results/jamb/student/{sid}/delete/2024', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert JAMBResult.query.filter_by(student_id=sid, exam_year=2024).first() is not None


def test_cutoffs_write_without_delete(app):
    from models import UniversityCutoff
    _make(app, 'cutoff_write', {'external_exams.cutoffs_view': 'edit',
                                'external_exams.cutoffs_write': 'edit'})
    c = _login(app, 'cutoff_write')
    assert c.get('/results/cutoffs').status_code == 200
    token = _ptoken(c)
    r = c.post('/results/cutoffs/save',
               data={'university_name': 'Test Uni', 'course_name': 'Test Course',
                     'exam_year': '0', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        row = UniversityCutoff.query.filter_by(university_name='Test Uni',
                                               course_name='Test Course').first()
        assert row is not None
        cid = row.id
    r2 = c.post(f'/results/cutoffs/{cid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(UniversityCutoff, cid) is not None   # delete not granted -> untouched


def test_predictions_view_without_config(app):
    _make(app, 'pred_view', {'external_exams.predictions_view': 'edit'})
    c = _login(app, 'pred_view')
    assert c.get('/results/predictions').status_code == 200
    assert c.get('/results/predictions/waec-model', follow_redirects=False).status_code in (302, 303)


# --- external_exams analytics partition (Phase 3) ---------------------------
def test_analytics_view_without_export_or_recompute(app):
    _make(app, 'analytics_view_only', {'external_exams.analytics_view': 'edit'})
    c = _login(app, 'analytics_view_only')
    assert c.get('/results/analytics').status_code == 200
    assert c.get('/results/waec/broadsheet').status_code == 200
    # 'analytics_export'/'analytics_recompute' are separate slices -> blocked
    assert c.get('/results/analytics/export', follow_redirects=False).status_code in (302, 303)
    token = _ptoken(c)
    r = c.post('/results/analytics/recompute', data={'_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_grade_distribution_create_without_delete(app):
    from models import Branch, BranchGradeDistribution
    with app.app_context():
        bid = Branch.get_default().id
        row = BranchGradeDistribution.query.filter_by(
            branch_id=bid, exam='waec', exam_year=2024, subject='English').first()
        if not row:
            row = BranchGradeDistribution(branch_id=bid, exam='waec', exam_year=2024,
                                          subject='English', candidates=10, band_counts='{}')
            db.session.add(row); db.session.commit()
    _make(app, 'gd_create', {'external_exams.grade_distribution_create': 'edit'})
    c = _login(app, 'gd_create')
    assert c.get('/results/subject-branch-breakdown/import?exam=waec').status_code == 200
    token = _ptoken(c)
    r = c.post('/results/subject-branch-breakdown/import/delete',
               data={'exam': 'waec', 'branch_id': str(bid), 'exam_year': '2024',
                     '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        # 'grade_distribution_delete' not granted -> row untouched
        assert BranchGradeDistribution.query.filter_by(
            branch_id=bid, exam='waec', exam_year=2024, subject='English').first() is not None


# --- external_exams certificate generator partition (Phase 4) --------------
def test_cert_generate_without_templates_or_bulk(app):
    _make(app, 'cert_gen_only', {'external_exams.cert_generate': 'edit'})
    c = _login(app, 'cert_gen_only')
    assert c.get('/results/waec/certificate').status_code == 200
    assert c.get('/results/waec/certificate/templates', follow_redirects=False).status_code in (302, 303)
    assert c.get('/results/waec/certificate/bulk', follow_redirects=False).status_code in (302, 303)


def test_cert_templates_without_delete(app):
    from models import WAECCertTemplate
    _make(app, 'cert_tpl_only', {'external_exams.cert_templates': 'edit'})
    c = _login(app, 'cert_tpl_only')
    assert c.get('/results/waec/certificate/templates').status_code == 200
    token = _ptoken(c)
    r = c.post('/results/waec/certificate/templates',
               data={'name': 'Test Template', 'base_layout': 'prestige', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        tpl = WAECCertTemplate.query.filter_by(name='Test Template').first()
        assert tpl is not None
        tpl_id = tpl.id
    # 'cert_templates_delete' is a separate slice -> blocked
    r2 = c.post(f'/results/waec/certificate/templates/{tpl_id}/delete',
                data={'_csrf_token': token}, follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(WAECCertTemplate, tpl_id) is not None   # untouched


def test_cert_presets_separate_from_templates(app):
    from models import WAECCertPreset
    _make(app, 'cert_preset_only', {'external_exams.cert_presets': 'edit'})
    c = _login(app, 'cert_preset_only')
    # presets don't grant access to template management
    assert c.get('/results/waec/certificate/templates', follow_redirects=False).status_code in (302, 303)
    token = _ptoken(c)
    r = c.post('/results/waec/certificate/presets',
               data={'name': 'Test Preset', 'c': 'school_name', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert WAECCertPreset.query.filter_by(name='Test Preset').first() is not None


# --- mock_waec partition (Phase 5) ------------------------------------------
def _mw_session(app):
    from models import AcademicSession
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='MW 25/26', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _mw_exam(app, ssid, n, name=None):
    from datetime import date
    from models.mock_waec import MockWAECExam
    with app.app_context():
        ex = MockWAECExam(name=name or f'MW Exam {n}', exam_number=n, session_id=ssid,
                          exam_date=date(2025, 1, 1))
        db.session.add(ex); db.session.commit()
        return ex.id


def _mw_student(app, sid):
    from models import Student
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Mock', surname='Waec', gender='Female')
            db.session.add(s); db.session.commit()
        return s.id


def _mw_result(app, student_id, exam_id, subject='Mathematics', score=65):
    from models.mock_waec import MockWAECResult, waec_grade_from_score
    with app.app_context():
        r = MockWAECResult(student_id=student_id, mock_exam_id=exam_id,
                           subject=subject, score=score, grade=waec_grade_from_score(score))
        db.session.add(r); db.session.commit()
        return r.id


def test_mock_waec_exam_view_without_create(app):
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 101)
    _make(app, 'mw_exam_view', {'external_exams.mock_waec_exam_view': 'view'})
    c = _login(app, 'mw_exam_view')
    assert c.get('/mock-waec/').status_code == 200
    assert c.get(f'/mock-waec/exam/{exam_id}').status_code == 200
    # 'mock_waec_exam_create' is a separate slice -> blocked
    assert c.get('/mock-waec/exam/create', follow_redirects=False).status_code in (302, 303)


def test_mock_waec_exam_create_without_edit_or_delete(app):
    from models.mock_waec import MockWAECExam
    ssid = _mw_session(app)
    _make(app, 'mw_exam_create', {'external_exams.mock_waec_exam_create': 'edit'})
    c = _login(app, 'mw_exam_create')
    assert c.get('/mock-waec/exam/create').status_code == 200
    token = _ptoken(c)
    r = c.post('/mock-waec/exam/create',
               data={'session_id': ssid, 'exam_number': 202, 'exam_date': '2025-03-01',
                     'name': 'Created Mock', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        exam = MockWAECExam.query.filter_by(session_id=ssid, exam_number=202).first()
        assert exam is not None
        exam_id = exam.id
    # 'mock_waec_exam_edit'/'mock_waec_exam_delete' are separate slices -> blocked
    assert c.get(f'/mock-waec/exam/{exam_id}/edit', follow_redirects=False).status_code in (302, 303)
    r2 = c.post(f'/mock-waec/exam/{exam_id}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockWAECExam, exam_id) is not None   # untouched


def test_mock_waec_exam_edit_without_delete(app):
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 103)
    _make(app, 'mw_exam_edit', {'external_exams.mock_waec_exam_view': 'view',
                                'external_exams.mock_waec_exam_edit': 'edit'})
    c = _login(app, 'mw_exam_edit')
    assert c.get(f'/mock-waec/exam/{exam_id}/edit').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-waec/exam/{exam_id}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        from models.mock_waec import MockWAECExam
        assert db.session.get(MockWAECExam, exam_id) is not None   # untouched


def test_mock_waec_results_create_without_edit_or_delete(app):
    from models.mock_waec import MockWAECResult
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 104)
    sid = _mw_student(app, 'MWC001')
    _make(app, 'mw_res_create', {'external_exams.mock_waec_exam_view': 'view',
                                 'external_exams.mock_waec_results_create': 'edit'})
    c = _login(app, 'mw_res_create')
    assert c.get(f'/mock-waec/exam/{exam_id}/results/add').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-waec/exam/{exam_id}/results/add',
               data={'student_id': sid, 'subject[]': ['Mathematics'], 'score[]': ['70'],
                     'grade[]': [''], '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        row = MockWAECResult.query.filter_by(student_id=sid, mock_exam_id=exam_id).first()
        assert row is not None
        rid = row.id
    # 'mock_waec_results_edit'/'mock_waec_results_delete' are separate slices -> blocked
    assert c.get(f'/mock-waec/exam/{exam_id}/student/{sid}/edit', follow_redirects=False).status_code in (302, 303)
    r2 = c.post(f'/mock-waec/result/{rid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockWAECResult, rid) is not None   # untouched


def test_mock_waec_results_edit_without_delete(app):
    from models.mock_waec import MockWAECResult
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 105)
    sid = _mw_student(app, 'MWC002')
    rid = _mw_result(app, sid, exam_id)
    _make(app, 'mw_res_edit', {'external_exams.mock_waec_exam_view': 'view',
                              'external_exams.mock_waec_results_edit': 'edit'})
    c = _login(app, 'mw_res_edit')
    assert c.get(f'/mock-waec/exam/{exam_id}/student/{sid}/edit').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-waec/result/{rid}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockWAECResult, rid) is not None   # delete not granted -> untouched


def test_mock_waec_results_delete_slice(app):
    from models.mock_waec import MockWAECResult
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 106)
    sid = _mw_student(app, 'MWC003')
    rid = _mw_result(app, sid, exam_id)
    _make(app, 'mw_res_delete', {'external_exams.mock_waec_exam_view': 'view',
                                 'external_exams.mock_waec_results_delete': 'edit'})
    c = _login(app, 'mw_res_delete')
    # 'mock_waec_results_edit' not granted -> blocked
    assert c.get(f'/mock-waec/exam/{exam_id}/student/{sid}/edit', follow_redirects=False).status_code in (302, 303)
    token = _ptoken(c)
    r = c.post(f'/mock-waec/result/{rid}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockWAECResult, rid) is None   # delete granted -> removed


def test_mock_waec_results_view_without_export(app):
    ssid = _mw_session(app)
    exam_id = _mw_exam(app, ssid, 107)
    _make(app, 'mw_res_view', {'external_exams.mock_waec_exam_view': 'view',
                              'external_exams.mock_waec_results_view': 'view'})
    c = _login(app, 'mw_res_view')
    assert c.get(f'/mock-waec/exam/{exam_id}/broadsheet').status_code == 200
    # 'mock_waec_results_export' is a separate slice -> blocked
    assert c.get(f'/mock-waec/exam/{exam_id}/export', follow_redirects=False).status_code in (302, 303)


# --- mock_jamb partition (Sub-Phase 1) --------------------------------------
def _mj_session(app):
    from models import AcademicSession
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='MJ 25/26', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _mj_exam(app, ssid, n):
    from datetime import date
    from models.mock_jamb import MockJAMBExam
    with app.app_context():
        ex = MockJAMBExam(name=f'MJ Exam {n}', exam_number=n, session_id=ssid,
                          exam_date=date(2025, 1, 1))
        db.session.add(ex); db.session.commit()
        return ex.id


def _mj_student(app, sid):
    from models import Student
    with app.app_context():
        s = Student.query.filter_by(student_id=sid).first()
        if not s:
            s = Student(student_id=sid, first_name='Mock', surname='Jamb', gender='Male')
            db.session.add(s); db.session.commit()
        return s.id


def _mj_result(app, student_id, exam_id, score=70):
    from models.mock_jamb import MockJAMBResult
    with app.app_context():
        r = MockJAMBResult(student_id=student_id, mock_exam_id=exam_id, total_score=score,
                           subject1='Mathematics', subject1_score=score)
        db.session.add(r); db.session.commit()
        return r.id


def _mj_subject(app, name):
    from models import Subject
    with app.app_context():
        s = Subject.query.filter_by(name=name).first() or Subject(name=name, is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _mj_passage(app, exam_id, subject_id):
    from models.mock_jamb import MockJAMBPassage
    with app.app_context():
        p = MockJAMBPassage(mock_exam_id=exam_id, subject_id=subject_id, kind='comprehension',
                            body='Read this passage and answer.')
        db.session.add(p); db.session.commit()
        return p.id


def test_mock_jamb_exam_view_without_create(app):
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 201)
    _make(app, 'mj_exam_view', {'external_exams.mock_jamb_exam_view': 'view'})
    c = _login(app, 'mj_exam_view')
    assert c.get('/mock-jamb/').status_code == 200
    assert c.get(f'/mock-jamb/exam/{exam_id}').status_code == 200
    # 'mock_jamb_exam_create' is a separate slice -> blocked
    assert c.get('/mock-jamb/exam/create', follow_redirects=False).status_code in (302, 303)


def test_mock_jamb_exam_create_without_edit_or_delete(app):
    from models.mock_jamb import MockJAMBExam
    ssid = _mj_session(app)
    _make(app, 'mj_exam_create', {'external_exams.mock_jamb_exam_create': 'edit'})
    c = _login(app, 'mj_exam_create')
    assert c.get('/mock-jamb/exam/create').status_code == 200
    token = _ptoken(c)
    r = c.post('/mock-jamb/exam/create',
               data={'session_id': ssid, 'exam_number': 202, 'exam_date': '2025-03-01',
                     'name': 'Created MJ', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        exam = MockJAMBExam.query.filter_by(session_id=ssid, exam_number=202).first()
        assert exam is not None
        exam_id = exam.id
    # 'mock_jamb_exam_edit'/'mock_jamb_exam_delete' are separate slices -> blocked
    assert c.get(f'/mock-jamb/exam/{exam_id}/edit', follow_redirects=False).status_code in (302, 303)
    r2 = c.post(f'/mock-jamb/exam/{exam_id}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBExam, exam_id) is not None   # untouched


def test_mock_jamb_exam_edit_without_delete(app):
    from models.mock_jamb import MockJAMBExam
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 203)
    _make(app, 'mj_exam_edit', {'external_exams.mock_jamb_exam_view': 'view',
                                'external_exams.mock_jamb_exam_edit': 'edit'})
    c = _login(app, 'mj_exam_edit')
    assert c.get(f'/mock-jamb/exam/{exam_id}/edit').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/exam/{exam_id}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBExam, exam_id) is not None   # untouched


def test_mock_jamb_results_create_without_edit_or_delete(app):
    from models.mock_jamb import MockJAMBResult
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 204)
    sid = _mj_student(app, 'MJC001')
    _make(app, 'mj_res_create', {'external_exams.mock_jamb_exam_view': 'view',
                                 'external_exams.mock_jamb_results_create': 'edit'})
    c = _login(app, 'mj_res_create')
    assert c.get(f'/mock-jamb/exam/{exam_id}/results/add').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/exam/{exam_id}/results/add',
               data={'student_id': sid, 'subject1': 'Mathematics', 'subject1_score': '70',
                     '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        row = MockJAMBResult.query.filter_by(student_id=sid, mock_exam_id=exam_id).first()
        assert row is not None
        rid = row.id
    # 'mock_jamb_results_edit'/'mock_jamb_results_delete' are separate slices -> blocked
    assert c.get(f'/mock-jamb/result/{rid}/edit', follow_redirects=False).status_code in (302, 303)
    r2 = c.post(f'/mock-jamb/result/{rid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBResult, rid) is not None   # untouched


def test_mock_jamb_results_edit_without_delete(app):
    from models.mock_jamb import MockJAMBResult
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 205)
    sid = _mj_student(app, 'MJC002')
    rid = _mj_result(app, sid, exam_id)
    _make(app, 'mj_res_edit', {'external_exams.mock_jamb_exam_view': 'view',
                              'external_exams.mock_jamb_results_edit': 'edit'})
    c = _login(app, 'mj_res_edit')
    assert c.get(f'/mock-jamb/result/{rid}/edit').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/result/{rid}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBResult, rid) is not None   # delete not granted -> untouched


def test_mock_jamb_results_delete_slice(app):
    from models.mock_jamb import MockJAMBResult
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 206)
    sid = _mj_student(app, 'MJC003')
    rid = _mj_result(app, sid, exam_id)
    _make(app, 'mj_res_delete', {'external_exams.mock_jamb_exam_view': 'view',
                                 'external_exams.mock_jamb_results_delete': 'edit'})
    c = _login(app, 'mj_res_delete')
    # 'mock_jamb_results_edit' not granted -> blocked
    assert c.get(f'/mock-jamb/result/{rid}/edit', follow_redirects=False).status_code in (302, 303)
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/result/{rid}/delete', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBResult, rid) is None   # delete granted -> removed


def test_mock_jamb_exam_view_without_export(app):
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 207)
    _make(app, 'mj_exam_view_noexp', {'external_exams.mock_jamb_exam_view': 'view'})
    c = _login(app, 'mj_exam_view_noexp')
    assert c.get(f'/mock-jamb/exam/{exam_id}').status_code == 200
    # 'mock_jamb_results_export' is a separate slice -> blocked
    assert c.get(f'/mock-jamb/exam/{exam_id}/export', follow_redirects=False).status_code in (302, 303)


def test_mock_jamb_build_view_without_edit(app):
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 208)
    _make(app, 'mj_build_view', {'external_exams.mock_jamb_build_view': 'view'})
    c = _login(app, 'mj_build_view')
    assert c.get(f'/mock-jamb/exam/{exam_id}/questions').status_code == 200
    token = _ptoken(c)
    subj_id = _mj_subject(app, 'MJ Build Subject A')
    r = c.post(f'/mock-jamb/exam/{exam_id}/passages/add',
               data={'subject_id': subj_id, 'body': 'A passage', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        from models.mock_jamb import MockJAMBPassage
        assert MockJAMBPassage.query.filter_by(mock_exam_id=exam_id).first() is None   # blocked


def test_mock_jamb_build_edit_without_delete(app):
    from models.mock_jamb import MockJAMBPassage
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 209)
    subj_id = _mj_subject(app, 'MJ Build Subject B')
    _make(app, 'mj_build_edit', {'external_exams.mock_jamb_build_view': 'view',
                                 'external_exams.mock_jamb_build_edit': 'edit'})
    c = _login(app, 'mj_build_edit')
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/exam/{exam_id}/passages/add',
               data={'subject_id': subj_id, 'body': 'A passage', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        passage = MockJAMBPassage.query.filter_by(mock_exam_id=exam_id).first()
        assert passage is not None
        pid = passage.id
    # 'mock_jamb_build_delete' is a separate slice -> blocked
    r2 = c.post(f'/mock-jamb/passage/{pid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBPassage, pid) is not None   # untouched


def test_mock_jamb_build_delete_slice(app):
    from models.mock_jamb import MockJAMBPassage
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 210)
    subj_id = _mj_subject(app, 'MJ Build Subject C')
    pid = _mj_passage(app, exam_id, subj_id)
    _make(app, 'mj_build_delete', {'external_exams.mock_jamb_build_view': 'view',
                                   'external_exams.mock_jamb_build_delete': 'edit'})
    c = _login(app, 'mj_build_delete')
    token = _ptoken(c)
    # 'mock_jamb_build_edit' not granted -> blocked
    r = c.post(f'/mock-jamb/exam/{exam_id}/passages/add',
               data={'subject_id': subj_id, 'body': 'Another passage', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert MockJAMBPassage.query.filter_by(mock_exam_id=exam_id, body='Another passage').first() is None
    r2 = c.post(f'/mock-jamb/passage/{pid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBPassage, pid) is None   # delete granted -> removed


def test_mock_jamb_analytics_view_without_export(app):
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 211)
    _make(app, 'mj_an_view', {'external_exams.mock_jamb_analytics_view': 'view'})
    c = _login(app, 'mj_an_view')
    assert c.get('/mock-jamb/analytics').status_code == 200
    assert c.get('/mock-jamb/trends').status_code == 200
    assert c.get('/mock-jamb/validation').status_code == 200
    assert c.get('/mock-jamb/mastery').status_code == 200
    assert c.get(f'/mock-jamb/exam/{exam_id}/deep').status_code == 200
    assert c.get(f'/mock-jamb/exam/{exam_id}/items').status_code == 200
    # 'mock_jamb_analytics_export' is a separate slice -> blocked, redirected to
    # the dashboard (not the in-feature "no data yet" redirect export uses).
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep/export', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''   # redirected to the dashboard


def test_mock_jamb_analytics_export_separate_slice(app):
    ssid = _mj_session(app)
    exam_id = _mj_exam(app, ssid, 212)
    _make(app, 'mj_an_export', {'external_exams.mock_jamb_analytics_view': 'view',
                                'external_exams.mock_jamb_analytics_export': 'edit'})
    c = _login(app, 'mj_an_export')
    # Granted both view + export -> passes the permission gate; the route then
    # redirects to its own "no data yet" page (not the dashboard), proving the
    # gate -- not the business logic -- is what's under test here.
    r = c.get(f'/mock-jamb/exam/{exam_id}/deep/export', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') != ''
    assert f'/mock-jamb/exam/{exam_id}/deep' in r.headers['Location']
