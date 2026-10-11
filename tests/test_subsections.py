"""Sub-section permissions (e.g. Finance: payments but not expenses)."""
import re
from models import (db, User, Expense, FeePayment, FeeDiscount, FeeItem, FeeStructure,
                    AdditionalCharge, Student, Term, AcademicSession, SchoolClass, ClassArm,
                    ClassArmAssignment, StudentEnrollment, Branch,
                    StaffMember, Department, LeaveRecord, PayrollRun, JobVacancy, JobApplication,
                    StaffLoan, StaffAttendance, Subject, ClassSubject,
                    PromotionRule, PromotionRecord)
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
    _make(app, 'fpart', {'finance.payments_view': 'view', 'finance.expenses_view': 'view'})
    c = _login(app, 'fpart')
    # granted sub-sections reachable
    assert c.get('/finance/payments').status_code == 200          # payments_view
    assert c.get('/finance/expenses').status_code == 200          # expenses_view
    # ungranted sub-section blocked
    assert c.get('/finance/defaulters', follow_redirects=False).status_code in (302, 303)


def test_view_subsection_blocks_write(app):
    _make(app, 'fpart2', {'finance.payments_view': 'view', 'finance.expenses_view': 'view'})
    c = _login(app, 'fpart2')
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add',
           data={'description': 'Tape', 'amount': 300, '_csrf_token': _ptoken(c)},
           follow_redirects=True)
    with app.app_context():
        assert Expense.query.count() == before        # 'expenses_create' not granted -> blocked


def test_subsection_level_helper(app):
    from flask import session
    from utils.access_control import subsection_level, module_level
    _make(app, 'fpart3', {'finance.payments_create': 'edit'})
    with app.app_context():
        uid = User.query.filter_by(username='fpart3').first().id
    with app.test_request_context('/'):
        session['logged_in'] = True; session['user_id'] = uid
        session['role'] = 'staff'; session['scope'] = 'central'
        assert subsection_level('finance', 'payments_create') == 'edit'
        assert subsection_level('finance', 'expenses_view') is None   # not granted
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


# --- mock_jamb central question bank partition (Sub-Phase 3) ---------------
def _mj_bank_question(app, subject_id, needs_image=False):
    from models.mock_jamb import MockJAMBQuestion
    with app.app_context():
        q = MockJAMBQuestion(mock_exam_id=None, subject_id=subject_id,
                             question_text='2+2=?', correct_option='A',
                             option_a='4', option_b='5', option_c='6', option_d='7',
                             needs_image=needs_image)
        db.session.add(q); db.session.commit()
        return q.id


def test_mock_jamb_bank_view_without_edit(app):
    subj_id = _mj_subject(app, 'MJ Bank Subject View')
    _make(app, 'mj_bank_view', {'external_exams.mock_jamb_bank_view': 'view'})
    c = _login(app, 'mj_bank_view')
    assert c.get('/mock-jamb/bank').status_code == 200
    token = _ptoken(c)
    r = c.post('/mock-jamb/bank/question/add',
               data={'subject_id': subj_id, 'question_text': 'Q?', 'correct_option': 'A',
                     'option_a': '1', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''   # blocked -> dashboard


def test_mock_jamb_bank_edit_without_delete(app):
    from models.mock_jamb import MockJAMBQuestion
    subj_id = _mj_subject(app, 'MJ Bank Subject Edit')
    _make(app, 'mj_bank_edit', {'external_exams.mock_jamb_bank_view': 'view',
                               'external_exams.mock_jamb_bank_edit': 'edit'})
    c = _login(app, 'mj_bank_edit')
    token = _ptoken(c)
    r = c.post('/mock-jamb/bank/question/add',
               data={'subject_id': subj_id, 'question_text': 'Added Q?', 'correct_option': 'A',
                     'option_a': '1', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        q = MockJAMBQuestion.query.filter_by(subject_id=subj_id, mock_exam_id=None,
                                             question_text='Added Q?').first()
        assert q is not None
        qid = q.id
    # 'mock_jamb_bank_delete' is a separate slice -> blocked
    r2 = c.post(f'/mock-jamb/bank/question/{qid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid) is not None   # untouched


def test_mock_jamb_bank_delete_slice(app):
    from models.mock_jamb import MockJAMBQuestion
    subj_id = _mj_subject(app, 'MJ Bank Subject Delete')
    qid = _mj_bank_question(app, subj_id)
    _make(app, 'mj_bank_delete', {'external_exams.mock_jamb_bank_view': 'view',
                                 'external_exams.mock_jamb_bank_delete': 'edit'})
    c = _login(app, 'mj_bank_delete')
    token = _ptoken(c)
    # 'mock_jamb_bank_edit' not granted -> blocked
    r = c.post('/mock-jamb/bank/question/add',
               data={'subject_id': subj_id, 'question_text': 'Nope?', 'correct_option': 'A',
                     'option_a': '1', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''
    r2 = c.post(f'/mock-jamb/bank/question/{qid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid) is None   # delete granted -> removed


def test_mock_jamb_bank_syllabus_view_without_edit(app):
    subj_id = _mj_subject(app, 'MJ Bank Syllabus View')
    _make(app, 'mj_syl_view', {'external_exams.mock_jamb_bank_syllabus_view': 'view'})
    c = _login(app, 'mj_syl_view')
    assert c.get('/mock-jamb/bank/syllabus').status_code == 200
    token = _ptoken(c)
    r = c.post('/mock-jamb/bank/syllabus/import',
               data={'subject_id': subj_id, 'format': 'json', 'text': 'not valid',
                     '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''   # blocked -> dashboard


def test_mock_jamb_bank_syllabus_edit_without_delete(app):
    subj_id = _mj_subject(app, 'MJ Bank Syllabus Edit')
    _make(app, 'mj_syl_edit', {'external_exams.mock_jamb_bank_syllabus_view': 'view',
                              'external_exams.mock_jamb_bank_syllabus_edit': 'edit'})
    c = _login(app, 'mj_syl_edit')
    token = _ptoken(c)
    # Granted -> passes the permission gate; a malformed import fails business
    # validation and redirects back to the syllabus page (not the dashboard).
    r = c.post('/mock-jamb/bank/syllabus/import',
               data={'subject_id': subj_id, 'format': 'json', 'text': 'not valid',
                     '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') != ''
    assert '/mock-jamb/bank/syllabus' in r.headers['Location']
    # 'mock_jamb_bank_syllabus_delete' is a separate slice -> blocked
    r2 = c.post('/mock-jamb/bank/syllabus/clear', data={'subject_id': subj_id, '_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert r2.headers['Location'].rstrip('/') == ''


def test_mock_jamb_bank_syllabus_delete_slice(app):
    from models.mock_jamb import MockJAMBSyllabus
    subj_id = _mj_subject(app, 'MJ Bank Syllabus Delete')
    with app.app_context():
        syl = MockJAMBSyllabus(subject_id=subj_id, prefix='MJD')
        db.session.add(syl); db.session.commit()
        syl_id = syl.id
    _make(app, 'mj_syl_delete', {'external_exams.mock_jamb_bank_syllabus_view': 'view',
                                'external_exams.mock_jamb_bank_syllabus_delete': 'edit'})
    c = _login(app, 'mj_syl_delete')
    token = _ptoken(c)
    # 'mock_jamb_bank_syllabus_edit' not granted -> blocked
    r = c.post('/mock-jamb/bank/syllabus/import',
               data={'subject_id': subj_id, 'format': 'json', 'text': 'not valid',
                     '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''
    r2 = c.post('/mock-jamb/bank/syllabus/clear', data={'subject_id': subj_id, '_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBSyllabus, syl_id) is None   # delete granted -> removed


def test_mock_jamb_bank_retag_slice(app):
    subj_id = _mj_subject(app, 'MJ Bank Retag')
    _make(app, 'mj_bank_retag', {'external_exams.mock_jamb_bank_analytics_view': 'view',
                                'external_exams.mock_jamb_bank_retag': 'edit'})
    c = _login(app, 'mj_bank_retag')
    token = _ptoken(c)
    # Granted -> passes the gate and redirects to bank_analytics (not the dashboard).
    r = c.post('/mock-jamb/bank/retag', data={'subject_id': subj_id, '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/mock-jamb/bank/analytics' in r.headers['Location']

    _make(app, 'mj_bank_noretag', {'external_exams.mock_jamb_bank_analytics_view': 'view'})
    c2 = _login(app, 'mj_bank_noretag')
    token2 = _ptoken(c2)
    r2 = c2.post('/mock-jamb/bank/retag', data={'subject_id': subj_id, '_csrf_token': token2},
                 follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert r2.headers['Location'].rstrip('/') == ''   # not granted -> dashboard


def test_mock_jamb_bank_scrape_slice(app):
    _make(app, 'mj_bank_scrape', {'external_exams.mock_jamb_bank_view': 'view',
                                 'external_exams.mock_jamb_bank_scrape': 'edit'})
    c = _login(app, 'mj_bank_scrape')
    token = _ptoken(c)
    # Granted, no subjects selected -> passes the gate, fails business validation (400 JSON).
    r = c.post('/mock-jamb/bank/scrape/start', data={'_csrf_token': token}, follow_redirects=False)
    assert r.status_code == 400

    _make(app, 'mj_bank_noscrape', {'external_exams.mock_jamb_bank_view': 'view'})
    c2 = _login(app, 'mj_bank_noscrape')
    token2 = _ptoken(c2)
    r2 = c2.post('/mock-jamb/bank/scrape/start', data={'_csrf_token': token2}, follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert r2.headers['Location'].rstrip('/') == ''   # not granted -> dashboard


def test_mock_jamb_bank_images_view_without_edit(app):
    subj_id = _mj_subject(app, 'MJ Bank Images View')
    qid = _mj_bank_question(app, subj_id, needs_image=True)
    _make(app, 'mj_img_view', {'external_exams.mock_jamb_bank_images_view': 'view'})
    c = _login(app, 'mj_img_view')
    assert c.get('/mock-jamb/bank/needs-images').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/bank/question/{qid}/set-image',
               data={'dismiss': '1', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''   # blocked -> dashboard
    with app.app_context():
        from models.mock_jamb import MockJAMBQuestion
        assert db.session.get(MockJAMBQuestion, qid).needs_image is True   # untouched


def test_mock_jamb_bank_images_edit_slice(app):
    from models.mock_jamb import MockJAMBQuestion
    subj_id = _mj_subject(app, 'MJ Bank Images Edit')
    qid = _mj_bank_question(app, subj_id, needs_image=True)
    _make(app, 'mj_img_edit', {'external_exams.mock_jamb_bank_images_view': 'view',
                              'external_exams.mock_jamb_bank_images_edit': 'edit'})
    c = _login(app, 'mj_img_edit')
    token = _ptoken(c)
    r = c.post(f'/mock-jamb/bank/question/{qid}/set-image',
               data={'dismiss': '1', '_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid).needs_image is False   # granted -> applied


def test_mock_jamb_bank_analytics_view_slice(app):
    _mj_subject(app, 'MJ Bank Analytics View')
    _make(app, 'mj_bank_an_view', {'external_exams.mock_jamb_bank_analytics_view': 'view'})
    c = _login(app, 'mj_bank_an_view')
    assert c.get('/mock-jamb/bank/analytics').status_code == 200


# --- communication partition ------------------------------------------------
def _cm_announcement(app, title='Test Announcement'):
    from models import Announcement
    with app.app_context():
        a = Announcement(title=title, created_by='tester')
        db.session.add(a); db.session.commit()
        return a.id


def _cm_template(app, name='Fee Reminder'):
    from models import MessageTemplate
    with app.app_context():
        t = MessageTemplate(name=name, body='Dear {parent}, this is a reminder.')
        db.session.add(t); db.session.commit()
        return t.id


def _cm_message(app, title='Test Campaign', status='Scheduled'):
    from models import Message
    with app.app_context():
        m = Message(title=title, body='Hello {parent}', channel='SMS', status=status)
        db.session.add(m); db.session.commit()
        return m.id


def test_announcements_view_without_create(app):
    _cm_announcement(app, 'View-only ann')
    _make(app, 'cm_ann_view', {'communication.announcements_view': 'view'})
    c = _login(app, 'cm_ann_view')
    assert c.get('/communication/announcements').status_code == 200
    token = _ptoken(c)
    r = c.post('/communication/announcements/add', data={'title': 'Nope', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        from models import Announcement
        assert Announcement.query.filter_by(title='Nope').first() is None


def test_announcements_create_without_edit_or_delete(app):
    from models import Announcement
    aid = _cm_announcement(app, 'Create-slice ann')
    _make(app, 'cm_ann_create', {'communication.announcements_create': 'edit'})
    c = _login(app, 'cm_ann_create')
    token = _ptoken(c)
    r = c.post('/communication/announcements/add', data={'title': 'Added', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert Announcement.query.filter_by(title='Added').first() is not None
    # 'announcements_edit'/'announcements_delete' are separate slices -> blocked
    r1b = c.post(f'/communication/announcements/{aid}/edit', data={'title': 'Edited', '_csrf_token': token},
                 follow_redirects=False)
    assert r1b.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Announcement, aid).title != 'Edited'
    r2 = c.post(f'/communication/announcements/{aid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Announcement, aid) is not None


def test_announcements_delete_slice(app):
    from models import Announcement
    aid = _cm_announcement(app, 'Delete-slice ann')
    _make(app, 'cm_ann_delete', {'communication.announcements_delete': 'edit'})
    c = _login(app, 'cm_ann_delete')
    token = _ptoken(c)
    # 'announcements_create' not granted -> blocked
    r = c.post('/communication/announcements/add', data={'title': 'Nope', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert Announcement.query.filter_by(title='Nope').first() is None
    r2 = c.post(f'/communication/announcements/{aid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Announcement, aid) is None   # delete granted -> removed


def test_ack_announcement_always_allowed(app):
    """Regression test for the pre-existing bug: acknowledging an announcement
    must work even for a user with ZERO communication-module access, since
    it's shown on the main dashboard to every logged-in user."""
    aid = _cm_announcement(app, 'Ack-all ann')
    _make(app, 'cm_no_comms_access', {})
    c = _login(app, 'cm_no_comms_access')
    token = _ptoken(c)
    r = c.post(f'/communication/announcements/{aid}/ack', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        from models import AnnouncementAck, User
        uid = User.query.filter_by(username='cm_no_comms_access').first().id
        assert AnnouncementAck.query.filter_by(announcement_id=aid, user_id=uid).first() is not None


def test_templates_create_without_delete(app):
    from models import MessageTemplate
    _make(app, 'cm_tpl_create', {'communication.templates_create': 'edit'})
    c = _login(app, 'cm_tpl_create')
    token = _ptoken(c)
    r = c.post('/communication/templates/add',
               data={'name': 'New Template', 'body': 'Hello {parent}', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        t = MessageTemplate.query.filter_by(name='New Template').first()
        assert t is not None
        tid = t.id
    # 'templates_delete' is a separate slice -> blocked
    r2 = c.post(f'/communication/templates/{tid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MessageTemplate, tid) is not None


def test_templates_delete_slice(app):
    from models import MessageTemplate
    tid = _cm_template(app, 'Delete-slice tpl')
    _make(app, 'cm_tpl_delete', {'communication.templates_delete': 'edit'})
    c = _login(app, 'cm_tpl_delete')
    token = _ptoken(c)
    r2 = c.post(f'/communication/templates/{tid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(MessageTemplate, tid) is None   # delete granted -> removed


def test_messages_create_without_view(app):
    mid = _cm_message(app, 'View-sep campaign')
    _make(app, 'cm_msg_create', {'communication.messages_create': 'edit'})
    c = _login(app, 'cm_msg_create')
    assert c.get('/communication/compose').status_code == 200
    # 'messages_view' is a separate slice -> blocked
    assert c.get('/communication/messages').status_code in (302, 303)
    assert c.get(f'/communication/messages/{mid}').status_code in (302, 303)


def test_messages_edit_without_delete(app):
    from models import Message
    mid = _cm_message(app, 'Edit-slice campaign', status='Scheduled')
    _make(app, 'cm_msg_edit', {'communication.messages_view': 'view',
                               'communication.messages_edit': 'edit'})
    c = _login(app, 'cm_msg_edit')
    assert c.get(f'/communication/messages/{mid}').status_code == 200
    token = _ptoken(c)
    r = c.post(f'/communication/messages/{mid}/cancel-schedule', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Message, mid).status == 'Draft'
    # 'messages_delete' is a separate slice -> blocked
    r2 = c.post(f'/communication/messages/{mid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Message, mid) is not None


def test_messages_delete_slice(app):
    from models import Message
    mid = _cm_message(app, 'Delete-slice campaign')
    _make(app, 'cm_msg_delete', {'communication.messages_view': 'view',
                                 'communication.messages_delete': 'edit'})
    c = _login(app, 'cm_msg_delete')
    token = _ptoken(c)
    # 'messages_edit' not granted -> blocked
    r = c.post(f'/communication/messages/{mid}/cancel-schedule', data={'_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Message, mid).status == 'Scheduled'
    r2 = c.post(f'/communication/messages/{mid}/delete', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    with app.app_context():
        assert db.session.get(Message, mid) is None   # delete granted -> removed


def test_messages_view_without_export(app):
    mid = _cm_message(app, 'Export-sep campaign')
    _make(app, 'cm_msg_view', {'communication.messages_view': 'view'})
    c = _login(app, 'cm_msg_view')
    assert c.get(f'/communication/messages/{mid}').status_code == 200
    # 'messages_export' is a separate slice -> blocked
    assert c.get(f'/communication/messages/{mid}/export').status_code in (302, 303)


def test_reports_view_without_export(app):
    _make(app, 'cm_rep_view', {'communication.reports_view': 'view'})
    c = _login(app, 'cm_rep_view')
    assert c.get('/communication/reports').status_code == 200
    assert c.get('/communication/reports/export').status_code in (302, 303)


def test_inbox_view_without_send(app):
    _make(app, 'cm_inbox_view', {'communication.inbox_view': 'view'})
    c = _login(app, 'cm_inbox_view')
    assert c.get('/communication/inbox').status_code == 200
    token = _ptoken(c)
    r = c.post('/communication/inbox/start', data={'user_ids': '1', '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''   # blocked -> dashboard


def test_inbox_send_slice(app):
    from models import User
    with app.app_context():
        other = User(username='cm_inbox_other', role='staff', scope='central', full_name='Other Staff')
        other.set_password('secret123'); other.set_permissions({})
        db.session.add(other); db.session.commit()
        other_id = other.id
    _make(app, 'cm_inbox_send', {'communication.inbox_view': 'view',
                                 'communication.inbox_send': 'edit'})
    c = _login(app, 'cm_inbox_send')
    token = _ptoken(c)
    r = c.post('/communication/inbox/start', data={'user_ids': str(other_id), '_csrf_token': token},
               follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') != ''
    assert '/communication/inbox/' in r.headers['Location']
    with app.app_context():
        from models import Conversation
        assert Conversation.query.count() >= 1


def test_settings_view_without_edit(app):
    _make(app, 'cm_set_view', {'communication.settings_view': 'view'})
    c = _login(app, 'cm_set_view')
    assert c.get('/communication/settings').status_code == 200
    token = _ptoken(c)
    r = c.post('/communication/settings/save', data={'_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers['Location'].rstrip('/') == ''   # blocked -> dashboard


def test_settings_edit_slice(app):
    _make(app, 'cm_set_edit', {'communication.settings_view': 'view',
                               'communication.settings_edit': 'edit'})
    c = _login(app, 'cm_set_edit')
    token = _ptoken(c)
    r = c.post('/communication/settings/save', data={'_csrf_token': token}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/communication/settings' in r.headers['Location']
    # 'save_automations' stays admin-only even with full settings_edit granted
    r2 = c.post('/communication/settings/automations', data={'_csrf_token': token},
                follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert r2.headers['Location'].rstrip('/') == ''   # still blocked -> dashboard


# ---- Finance (32-key granular split) ---------------------------------------

def _fin_term_student(app, tag, sid, enrol=False):
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name=f'{tag}-Sess').first() or AcademicSession(name=f'{tag}-Sess')
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(name=f'{tag}-Term').first() or Term(session_id=ssn.id, term_number=1, name=f'{tag}-Term')
        db.session.add(term); db.session.flush()
        st = Student.query.filter_by(student_id=sid).first()
        if not st:
            st = Student(student_id=sid, first_name='F', surname='N', gender='Male',
                         is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.flush()
        if enrol:
            cls = SchoolClass.query.filter_by(name=f'{tag}-Class').first() or SchoolClass(name=f'{tag}-Class', level=1)
            db.session.add(cls); db.session.flush()
            arm = ClassArm.query.filter_by(name=f'{tag}-Arm').first() or ClassArm(name=f'{tag}-Arm', is_active=True)
            db.session.add(arm); db.session.flush()
            caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first()
                   or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id))
            db.session.add(caa); db.session.flush()
            if not StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first():
                db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return term.id, st.id


def test_finance_payments_view_without_create(app):
    _make(app, 'finpv', {'finance.payments_view': 'view'})
    c = _login(app, 'finpv')
    assert c.get('/finance/collections').status_code == 200
    assert c.get('/finance/payments').status_code == 200
    r = c.get('/finance/payments/record', follow_redirects=False)
    assert r.status_code in (302, 303)        # payments_create not granted


def test_finance_payments_create_without_edit_or_delete(app):
    term_id, sid = _fin_term_student(app, 'FPC', 'FPC-STU')
    _make(app, 'finpc', {'finance.payments_create': 'edit'})
    c = _login(app, 'finpc')
    tok = _ptoken(c)
    c.post('/finance/payments/record',
           data={'student_id': sid, 'term_id': term_id, 'amount': '1000',
                 'payment_date': '2024-01-10', 'method': 'Cash', '_csrf_token': tok})
    with app.app_context():
        payment = FeePayment.query.filter_by(student_id=sid, term_id=term_id).first()
        assert payment is not None
        pid = payment.id
    # blocked from edit_payment (even the GET form page)
    r = c.get(f'/finance/payments/{pid}/edit', follow_redirects=False)
    assert r.status_code in (302, 303)
    # blocked from delete_payment
    c.post(f'/finance/payments/{pid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(FeePayment, pid) is not None


def test_finance_payments_delete_without_create(app):
    term_id, sid = _fin_term_student(app, 'FPD', 'FPD-STU')
    with app.app_context():
        p = FeePayment(student_id=sid, term_id=term_id, amount=500, method='Cash',
                       receipt_no='FPD-RCP-1', branch_id=Branch.get_default().id)
        db.session.add(p); db.session.commit()
        pid = p.id
    _make(app, 'finpd', {'finance.payments_delete': 'edit'})
    c = _login(app, 'finpd')
    tok = _ptoken(c)
    with app.app_context():
        before = FeePayment.query.filter_by(student_id=sid, term_id=term_id).count()
    c.post('/finance/payments/record',
           data={'student_id': sid, 'term_id': term_id, 'amount': '700',
                 'payment_date': '2024-01-10', 'method': 'Cash', '_csrf_token': tok})
    with app.app_context():
        assert FeePayment.query.filter_by(student_id=sid, term_id=term_id).count() == before
    c.post(f'/finance/payments/{pid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(FeePayment, pid) is None


def test_finance_discounts_create_without_delete(app):
    term_id, sid = _fin_term_student(app, 'FDC', 'FDC-STU')
    _make(app, 'findc', {'finance.discounts_create': 'edit'})
    c = _login(app, 'findc')
    tok = _ptoken(c)
    c.post('/finance/discounts/add',
           data={'student_id': sid, 'term_id': term_id, 'amount': '200',
                 'reason': 'Sibling', '_csrf_token': tok})
    with app.app_context():
        disc = FeeDiscount.query.filter_by(student_id=sid, term_id=term_id).first()
        assert disc is not None
        did = disc.id
    c.post(f'/finance/discounts/{did}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(FeeDiscount, did) is not None   # delete not granted


def test_finance_structure_edit_without_bulk_or_delete(app):
    term_id, sid = _fin_term_student(app, 'FSE', 'FSE-STU', enrol=True)
    with app.app_context():
        caa = StudentEnrollment.query.filter_by(student_id=sid, is_active=True).first().class_arm_assignment
        class_id = caa.class_id
        item = FeeItem.query.filter_by(name='FSE-Tuition').first() or FeeItem(name='FSE-Tuition')
        db.session.add(item); db.session.commit()
        item_id = item.id
    _make(app, 'finse', {'finance.structure_view': 'view', 'finance.structure_edit': 'edit'})
    c = _login(app, 'finse')
    tok = _ptoken(c)
    c.post('/finance/structure/save',
           data={'term_id': term_id, 'class_id': class_id, f'amount_{item_id}': '3000',
                 '_csrf_token': tok})
    with app.app_context():
        row = FeeStructure.query.filter_by(term_id=term_id, class_id=class_id, fee_item_id=item_id).first()
        assert row is not None and row.amount == 3000
    # blocked from copy_structure
    c.post('/finance/structure/copy',
           data={'from_term_id': term_id, 'to_term_id': term_id + 999999, '_csrf_token': tok})
    with app.app_context():
        assert FeeStructure.query.filter_by(term_id=term_id + 999999).count() == 0
    # blocked from clear_structure
    c.post('/finance/structure/clear',
           data={'term_id': term_id, 'class_id': class_id, '_csrf_token': tok})
    with app.app_context():
        assert FeeStructure.query.filter_by(term_id=term_id, class_id=class_id, fee_item_id=item_id).first() is not None


def test_finance_structure_bulk_without_edit(app):
    term_id, sid = _fin_term_student(app, 'FSB', 'FSB-STU', enrol=True)
    with app.app_context():
        caa = StudentEnrollment.query.filter_by(student_id=sid, is_active=True).first().class_arm_assignment
        class_id = caa.class_id
        item = FeeItem.query.filter_by(name='FSB-Tuition').first() or FeeItem(name='FSB-Tuition')
        db.session.add(item); db.session.flush()
        if not FeeStructure.query.filter_by(term_id=term_id, class_id=class_id, fee_item_id=item.id).first():
            db.session.add(FeeStructure(term_id=term_id, class_id=class_id, arm_id=None,
                                        fee_item_id=item.id, amount=4000))
        ssn2 = AcademicSession.query.filter_by(name='FSB-Sess2').first() or AcademicSession(name='FSB-Sess2')
        db.session.add(ssn2); db.session.flush()
        term2 = Term.query.filter_by(name='FSB-Term2').first() or Term(session_id=ssn2.id, term_number=1, name='FSB-Term2')
        db.session.add(term2); db.session.commit()
        to_term_id = term2.id
        item_id = item.id
    _make(app, 'finsb', {'finance.structure_view': 'view', 'finance.structure_bulk': 'edit'})
    c = _login(app, 'finsb')
    tok = _ptoken(c)
    c.post('/finance/structure/copy',
           data={'from_term_id': term_id, 'to_term_id': to_term_id, '_csrf_token': tok})
    with app.app_context():
        assert FeeStructure.query.filter_by(term_id=to_term_id, class_id=class_id, fee_item_id=item_id).first() is not None
    # blocked from save_structure
    c.post('/finance/structure/save',
           data={'term_id': term_id, 'class_id': class_id, f'amount_{item_id}': '9999', '_csrf_token': tok})
    with app.app_context():
        row = FeeStructure.query.filter_by(term_id=term_id, class_id=class_id, fee_item_id=item_id).first()
        assert row.amount == 4000   # unchanged, save_structure not granted


def test_finance_expenses_create_without_delete(app):
    _make(app, 'finec', {'finance.expenses_create': 'edit'})
    c = _login(app, 'finec')
    tok = _ptoken(c)
    with app.app_context():
        before = Expense.query.count()
    c.post('/finance/expenses/add', data={'description': 'FEC Chalk', 'amount': '150', '_csrf_token': tok})
    with app.app_context():
        assert Expense.query.count() == before + 1
        eid = Expense.query.filter_by(description='FEC Chalk').first().id
    c.post(f'/finance/expenses/{eid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Expense, eid) is not None   # delete not granted


def test_finance_defaulters_view_without_notify(app):
    _make(app, 'findv', {'finance.defaulters_view': 'view'})
    c = _login(app, 'findv')
    assert c.get('/finance/defaulters').status_code == 200
    tok = _ptoken(c)
    r = c.post('/finance/installments/notify-overdue', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)        # defaulters_notify not granted


def test_finance_reports_view_without_export(app):
    _make(app, 'finrv', {'finance.reports_view': 'view'})
    c = _login(app, 'finrv')
    assert c.get('/finance/reports').status_code == 200
    r = c.get('/finance/reports/export', follow_redirects=False)
    assert r.status_code in (302, 303)        # reports_export is a separate slice


def test_finance_overview_sync_blocked_even_with_unrelated_edit(app):
    # Regression test for the gap this phase closes: before the 32-key split,
    # module_level('finance') returned 'edit' for ANY edit grant anywhere in
    # Finance, which incorrectly unlocked ledger_sync for a user who only held
    # e.g. defaulters_notify edit. Confirm that's closed, with and without an
    # unrelated edit grant present.
    _make(app, 'finov', {'finance.overview_view': 'view'})
    c = _login(app, 'finov')
    assert c.get('/finance/overview').status_code == 200
    tok = _ptoken(c)
    r = c.post('/finance/ledger/sync', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)

    _make(app, 'finov2', {'finance.overview_view': 'view', 'finance.defaulters_notify': 'edit'})
    c2 = _login(app, 'finov2')
    tok2 = _ptoken(c2)
    r2 = c2.post('/finance/ledger/sync', data={'_csrf_token': tok2}, follow_redirects=False)
    assert r2.status_code in (302, 303)


def test_finance_billing_tools_view_blocked_from_bulk_charge(app):
    # The actual security gap this phase closes: before the split, a user with
    # edit on ANY finance subsection could mass-create charges/penalties via
    # module_level('finance') == 'edit'. Confirm billing_tools_view alone, even
    # alongside an unrelated edit grant, cannot reach bulk_charge/apply_penalties.
    term_id, sid = _fin_term_student(app, 'FBV', 'FBV-STU', enrol=True)
    _make(app, 'finbv', {'finance.billing_tools_view': 'view', 'finance.expenses_create': 'edit'})
    c = _login(app, 'finbv')
    assert c.get(f'/finance/billing-tools?term_id={term_id}').status_code == 200
    tok = _ptoken(c)
    with app.app_context():
        before = AdditionalCharge.query.filter_by(term_id=term_id).count()
    c.post('/finance/billing-tools/bulk-charge',
           data={'term_id': term_id, 'kind': 'charge', 'amount': '500', '_csrf_token': tok})
    c.post('/finance/billing-tools/penalties',
           data={'term_id': term_id, 'ptype': 'fixed', 'value': '500', '_csrf_token': tok})
    with app.app_context():
        assert AdditionalCharge.query.filter_by(term_id=term_id).count() == before


def test_finance_billing_tools_create_without_delete(app):
    term_id, sid = _fin_term_student(app, 'FBC', 'FBC-STU', enrol=True)
    _make(app, 'finbc', {'finance.billing_tools_create': 'edit'})
    c = _login(app, 'finbc')
    tok = _ptoken(c)
    c.post('/finance/billing-tools/bulk-charge',
           data={'term_id': term_id, 'kind': 'charge', 'category': 'Excursion',
                 'amount': '800', '_csrf_token': tok})
    with app.app_context():
        ch = AdditionalCharge.query.filter_by(term_id=term_id, category='Excursion').first()
        assert ch is not None
        cid = ch.id
    c.post(f'/finance/billing-tools/charge/{cid}/remove', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(AdditionalCharge, cid) is not None   # delete not granted


def test_finance_installments_view_without_edit(app):
    term_id, sid = _fin_term_student(app, 'FIV', 'FIV-STU')
    _make(app, 'finiv', {'finance.installments_view': 'view'})
    c = _login(app, 'finiv')
    assert c.get(f'/finance/installments?term_id={term_id}').status_code == 200
    tok = _ptoken(c)
    c.post('/finance/installments/save',
           data={'term_id': term_id, 'label': ['1st'], 'percent': ['50'], 'due': ['2024-01-01'],
                 '_csrf_token': tok})
    with app.app_context():
        from utils.finance_installments import get_plan
        assert get_plan(term_id, None) == []      # installments_edit not granted


def test_finance_installments_edit_without_delete(app):
    term_id, sid = _fin_term_student(app, 'FIE', 'FIE-STU')
    _make(app, 'finie', {'finance.installments_edit': 'edit'})
    c = _login(app, 'finie')
    tok = _ptoken(c)
    c.post('/finance/installments/save',
           data={'term_id': term_id, 'label': ['1st'], 'percent': ['50'], 'due': ['2024-01-01'],
                 '_csrf_token': tok})
    with app.app_context():
        from utils.finance_installments import get_plan
        plan = get_plan(term_id, None)
        assert len(plan) == 1 and plan[0].percent == 50
    c.post('/finance/installments/clear', data={'term_id': term_id, '_csrf_token': tok})
    with app.app_context():
        plan = get_plan(term_id, None)
        assert len(plan) == 1   # installments_delete not granted, still there


# ---- HR (40-key granular split) --------------------------------------------

def _hr_staff(app, tag, **kw):
    with app.app_context():
        s = StaffMember(staff_id=f'HR{tag}', first_name='Hr', surname=f'Zz{tag}',
                        staff_type='Teaching', status='Active', is_active=True,
                        branch_id=Branch.get_default().id, **kw)
        db.session.add(s); db.session.commit()
        return s.id


def test_hr_staff_view_without_create(app):
    _make(app, 'hrsv', {'hr.staff_view': 'view'})
    c = _login(app, 'hrsv')
    assert c.get('/hr/staff').status_code == 200
    r = c.get('/hr/staff/add', follow_redirects=False)
    assert r.status_code in (302, 303)        # staff_create not granted


def test_hr_staff_create_without_edit_or_delete(app):
    _make(app, 'hrsc', {'hr.staff_create': 'edit'})
    c = _login(app, 'hrsc')
    tok = _ptoken(c)
    with app.app_context():
        before = StaffMember.query.count()
    c.post('/hr/staff/add', data={'first_name': 'New', 'surname': 'Hire', 'gender': 'Male',
                                  'staff_type': 'Teaching', '_csrf_token': tok})
    with app.app_context():
        staff = StaffMember.query.filter_by(surname='Hire').first()
        assert staff is not None
        sid = staff.id
        assert StaffMember.query.count() == before + 1
    # blocked from edit_staff (even the GET form page)
    r = c.get(f'/hr/staff/{sid}/edit', follow_redirects=False)
    assert r.status_code in (302, 303)
    # blocked from delete_staff
    c.post(f'/hr/staff/{sid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(StaffMember, sid) is not None


def test_hr_staff_edit_without_lifecycle_even_with_unrelated_edit(app):
    # Regression test for the gap this phase closes: before the 40-key split,
    # module_level('hr') returned 'edit' for ANY edit grant anywhere in HR,
    # which incorrectly unlocked salary adjustment / promote / transfer for a
    # user who only had plain staff_edit. Confirm that's closed, even
    # alongside an unrelated edit grant (leave_approve).
    sid = _hr_staff(app, 'SE1', designation='Teacher', salary=80000)
    _make(app, 'hrse', {'hr.staff_edit': 'edit', 'hr.leave_approve': 'edit'})
    c = _login(app, 'hrse')
    tok = _ptoken(c)
    c.post(f'/hr/staff/{sid}/salary',
           data={'new_salary': '150000', 'effective_date': '2024-01-10', '_csrf_token': tok})
    with app.app_context():
        s = db.session.get(StaffMember, sid)
        assert s.salary == 80000        # staff_lifecycle not granted -> unchanged


def test_hr_staff_lifecycle_without_delete(app):
    sid = _hr_staff(app, 'SL1', designation='Teacher', salary=80000)
    _make(app, 'hrsl', {'hr.staff_lifecycle': 'edit'})
    c = _login(app, 'hrsl')
    tok = _ptoken(c)
    c.post(f'/hr/staff/{sid}/confirm', data={'effective_date': '2024-01-10', '_csrf_token': tok})
    with app.app_context():
        s = db.session.get(StaffMember, sid)
        assert s.confirmation_date is not None
    c.post(f'/hr/staff/{sid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(StaffMember, sid) is not None   # staff_delete not granted


def test_hr_departments_edit_without_delete(app):
    with app.app_context():
        dep = Department(name='HR-Dept-1', is_active=True)
        db.session.add(dep); db.session.commit()
        dep_id = dep.id
    _make(app, 'hrde', {'hr.departments_view': 'view', 'hr.departments_edit': 'edit'})
    c = _login(app, 'hrde')
    tok = _ptoken(c)
    c.post(f'/hr/departments/{dep_id}/edit', data={'name': 'HR-Dept-1-Renamed', '_csrf_token': tok})
    with app.app_context():
        dep = db.session.get(Department, dep_id)
        assert dep.name == 'HR-Dept-1-Renamed'
    c.post(f'/hr/departments/{dep_id}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Department, dep_id) is not None   # departments_delete not granted


def test_hr_leave_create_without_approve(app):
    sid = _hr_staff(app, 'LV1')
    _make(app, 'hrlc', {'hr.leave_create': 'edit'})
    c = _login(app, 'hrlc')
    tok = _ptoken(c)
    c.post('/hr/leave/add', data={'staff_id': sid, 'leave_type': 'Annual',
                                  'start_date': '2024-02-01', 'end_date': '2024-02-03',
                                  '_csrf_token': tok})
    with app.app_context():
        lv = LeaveRecord.query.filter_by(staff_id=sid).first()
        assert lv is not None
        lv_id = lv.id
    c.post(f'/hr/leave/{lv_id}/status', data={'status': 'Approved', '_csrf_token': tok})
    with app.app_context():
        lv = db.session.get(LeaveRecord, lv_id)
        assert lv.status == 'Pending'   # leave_approve not granted


def test_hr_payroll_create_without_finalize(app):
    _make(app, 'hrpc', {'hr.payroll_create': 'edit'})
    c = _login(app, 'hrpc')
    tok = _ptoken(c)
    c.post('/hr/payroll/create', data={'year': '2099', 'month': '5', '_csrf_token': tok})
    with app.app_context():
        run = PayrollRun.query.filter_by(year=2099, month=5).first()
        assert run is not None
        run_id = run.id
    c.post(f'/hr/payroll/{run_id}/finalize', data={'_csrf_token': tok})
    with app.app_context():
        run = db.session.get(PayrollRun, run_id)
        assert run.status == 'Draft'   # payroll_finalize not granted


def test_hr_payroll_edit_blocked_from_finalize_and_delete(app):
    # Regression test, same shape as the staff_edit one above: plain
    # payroll_edit must not imply the higher-trust finalize/delete tiers.
    with app.app_context():
        run = PayrollRun(year=2099, month=6, status='Draft', branch_id=Branch.get_default().id)
        db.session.add(run); db.session.commit()
        run_id = run.id
    _make(app, 'hrpe', {'hr.payroll_edit': 'edit'})
    c = _login(app, 'hrpe')
    tok = _ptoken(c)
    c.post(f'/hr/payroll/{run_id}/finalize', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(PayrollRun, run_id).status == 'Draft'
    c.post(f'/hr/payroll/{run_id}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(PayrollRun, run_id) is not None


def test_hr_attendance_view_without_mark_or_qr(app):
    _make(app, 'hrav', {'hr.attendance_view': 'view'})
    c = _login(app, 'hrav')
    assert c.get('/hr/attendance').status_code == 200
    tok = _ptoken(c)
    r = c.post('/hr/attendance/save', data={'date': '2024-01-10', '_csrf_token': tok},
               follow_redirects=False)
    assert r.status_code in (302, 303)        # attendance_mark not granted
    r2 = c.get('/hr/attendance/qr', follow_redirects=False)
    assert r2.status_code in (302, 303)        # attendance_qr not granted


def test_hr_settings_view_without_edit(app):
    _make(app, 'hrstv', {'hr.settings_view': 'view'})
    c = _login(app, 'hrstv')
    assert c.get('/hr/settings').status_code == 200
    tok = _ptoken(c)
    r = c.post('/hr/settings/save', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)        # settings_edit not granted
    r2 = c.post('/hr/settings/deductions/add',
                data={'name': 'Welfare', 'kind': 'fixed', 'value': '500', '_csrf_token': tok},
                follow_redirects=False)
    assert r2.status_code in (302, 303)        # deduction_types_edit not granted


def test_hr_reports_view_without_export(app):
    _make(app, 'hrrv', {'hr.reports_view': 'view'})
    c = _login(app, 'hrrv')
    assert c.get('/hr/reports').status_code == 200
    r = c.get('/hr/reports/export', follow_redirects=False)
    assert r.status_code in (302, 303)        # reports_export is a separate slice


def test_hr_recruitment_view_blocked_from_hire_even_with_edit(app):
    # The actual security gap this phase closes: before the split, edit on ANY
    # HR subsection could reach hire_applicant (converts a candidate into a real
    # StaffMember) via module_level('hr') == 'edit'. Confirm recruitment_view +
    # recruitment_edit together still don't imply recruitment_hire.
    with app.app_context():
        v = JobVacancy(title='HR Vac 1', status='Open', branch_id=Branch.get_default().id)
        db.session.add(v); db.session.flush()
        a = JobApplication(vacancy_id=v.id, first_name='App', surname='One', status='Shortlisted')
        db.session.add(a); db.session.commit()
        app_id = a.id
    _make(app, 'hrrcv', {'hr.recruitment_view': 'view', 'hr.recruitment_edit': 'edit'})
    c = _login(app, 'hrrcv')
    tok = _ptoken(c)
    c.post(f'/hr/applications/{app_id}/hire', data={'_csrf_token': tok})
    with app.app_context():
        a = db.session.get(JobApplication, app_id)
        assert a.status == 'Shortlisted'   # recruitment_hire not granted
        assert a.hired_staff_id is None


def test_hr_recruitment_create_without_delete(app):
    _make(app, 'hrrcc', {'hr.recruitment_create': 'edit'})
    c = _login(app, 'hrrcc')
    tok = _ptoken(c)
    c.post('/hr/recruitment/add', data={'title': 'HR Vac 2', '_csrf_token': tok})
    with app.app_context():
        v = JobVacancy.query.filter_by(title='HR Vac 2').first()
        assert v is not None
        vac_id = v.id
    c.post(f'/hr/recruitment/{vac_id}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(JobVacancy, vac_id) is not None   # recruitment_delete not granted


def test_hr_loans_view_blocked_from_create_and_manage(app):
    # Regression test confirming the whole Loans feature (previously 100%
    # admin-only and totally unmapped, riding on whole-module access) is
    # properly gated now, not accidentally wide open via whole-module fallback.
    sid = _hr_staff(app, 'LN1')
    with app.app_context():
        loan = StaffLoan(staff_id=sid, branch_id=Branch.get_default().id, principal=10000,
                         total_repayable=10500, monthly_amount=1050, status='active')
        db.session.add(loan); db.session.commit()
        loan_id = loan.id
    _make(app, 'hrlv', {'hr.loans_view': 'view'})
    c = _login(app, 'hrlv')
    assert c.get('/hr/loans').status_code == 200
    tok = _ptoken(c)
    r = c.get('/hr/loans/new', follow_redirects=False)
    assert r.status_code in (302, 303)        # loans_create not granted
    c.post(f'/hr/loans/{loan_id}/repay', data={'amount': '500', '_csrf_token': tok})
    with app.app_context():
        loan = db.session.get(StaffLoan, loan_id)
        assert loan.amount_repaid == 0   # loans_manage not granted


def test_hr_self_service_unaffected_by_module_split(app):
    # The self_* capability keys are orthogonal to the granular module split —
    # confirm a user with ZERO ordinary HR module grants can still clock in via
    # their own linked StaffMember using only the self_attendance capability.
    with app.app_context():
        u = User(username='hrself1', role='staff', scope='branch',
                 branch_id=Branch.get_default().id, full_name='hrself1')
        u.set_password('secret123'); u.set_permissions({'hr.self_attendance': 'edit'})
        db.session.add(u); db.session.flush()
        s = StaffMember(staff_id='HRSELF1', first_name='Self', surname='Service',
                        is_active=True, status='Active', staff_type='Teaching',
                        branch_id=Branch.get_default().id, user_id=u.id)
        db.session.add(s); db.session.commit()
    c = _login(app, 'hrself1')
    with app.app_context():
        from utils import hr
        code = hr.day_code()
    r = c.post('/hr/checkin/self', data={'method': 'qr', 'code': code, '_csrf_token': _ptoken(c)},
               follow_redirects=False)
    assert r.status_code in (200, 302, 303)
    with app.app_context():
        s = StaffMember.query.filter_by(staff_id='HRSELF1').first()
        assert StaffAttendance.query.filter_by(staff_id=s.id).first() is not None
    # still fully blocked from ordinary HR module pages
    assert c.get('/hr/staff', follow_redirects=False).status_code in (302, 303)


def test_hr_device_token_stays_admin_only(app):
    # regenerate_device_token is deliberately left out of the grant system
    # (same precedent as Settings' Users/Branches/Backup) — confirm a non-admin
    # stays blocked even holding full settings_edit + attendance_mark.
    _make(app, 'hrdt', {'hr.settings_view': 'view', 'hr.settings_edit': 'edit',
                        'hr.attendance_view': 'view', 'hr.attendance_mark': 'edit'})
    c = _login(app, 'hrdt')
    tok = _ptoken(c)
    r = c.post('/hr/settings/device-token', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)


# ---- Results/Subjects (15-key granular split + 'cards' capability) --------

def _subj_term_class(app, tag):
    with app.app_context():
        term = Term.query.filter_by(name=f'{tag}-Term').first()
        if not term:
            ssn = AcademicSession(name=f'{tag}-Sess')
            db.session.add(ssn); db.session.flush()
            term = Term(session_id=ssn.id, term_number=1, name=f'{tag}-Term')
            db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name=f'{tag}-Class').first() or SchoolClass(name=f'{tag}-Class', level=1)
        db.session.add(cls); db.session.flush()
        db.session.commit()
        return term.id, cls.id


def _subj_teacher(app, username, perms):
    # scores_entry/scoresheet_scan/etc. have their own business-logic gate
    # (can_enter_results()) independent of the subsection system: a non-admin
    # must have a Teacher profile with can_enter_results=True to even reach
    # the page. Granting the subsection key alone is not enough for these.
    from models import Teacher
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, role='teacher', scope='central', full_name=username)
            u.set_password('secret123'); u.set_permissions(perms)
            db.session.add(u); db.session.flush()
            db.session.add(Teacher(user_id=u.id, can_enter_results=True))
            db.session.commit()


def test_results_subjects_view_without_create(app):
    _make(app, 'rssv', {'results.subjects_view': 'view'})
    c = _login(app, 'rssv')
    assert c.get('/subjects/').status_code == 200
    r = c.get('/subjects/add', follow_redirects=False)
    assert r.status_code in (302, 303)        # subjects_create not granted


def test_results_subjects_create_without_edit_or_delete(app):
    _make(app, 'rssc', {'results.subjects_create': 'edit'})
    c = _login(app, 'rssc')
    tok = _ptoken(c)
    c.post('/subjects/add', data={'name': 'RSSC Subject', '_csrf_token': tok})
    with app.app_context():
        subj = Subject.query.filter_by(name='RSSC Subject').first()
        assert subj is not None
        sid = subj.id
    r = c.get(f'/subjects/{sid}/edit', follow_redirects=False)
    assert r.status_code in (302, 303)
    c.post(f'/subjects/{sid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Subject, sid).is_active is True


def test_results_subjects_edit_without_delete(app):
    term_id, class_id = _subj_term_class(app, 'RSE')
    with app.app_context():
        subj = Subject(name='RSE Subject', is_active=True)
        db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=class_id, term_id=term_id,
                          teacher_name=None, is_active=True)
        db.session.add(cs); db.session.commit()
        cs_id = cs.id
    _make(app, 'rsse', {'results.subjects_edit': 'edit'})
    c = _login(app, 'rsse')
    tok = _ptoken(c)
    c.post(f'/subjects/class-subjects/{cs_id}/edit', data={'teacher_name': 'Mr. RSE', '_csrf_token': tok})
    with app.app_context():
        assert db.session.get(ClassSubject, cs_id).teacher_name == 'Mr. RSE'
    c.post(f'/subjects/class-subjects/{cs_id}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(ClassSubject, cs_id).is_active is True   # subjects_delete not granted


def test_results_subjects_assign_without_edit(app):
    term_id, class_id = _subj_term_class(app, 'RSA')
    with app.app_context():
        subj = Subject.query.filter_by(name='RSA Subject').first() or Subject(name='RSA Subject', is_active=True)
        db.session.add(subj); db.session.commit()
        subj_id = subj.id
    _make(app, 'rsas', {'results.subjects_assign': 'edit'})
    c = _login(app, 'rsas')
    tok = _ptoken(c)
    c.post('/subjects/class-subjects/assign',
           data={'term_id': term_id, 'class_id': class_id, 'subject_ids[]': [str(subj_id)],
                 'teacher_names[]': ['Mrs. RSA'], '_csrf_token': tok})
    with app.app_context():
        cs = ClassSubject.query.filter_by(subject_id=subj_id, class_id=class_id, term_id=term_id).first()
        assert cs is not None
    # blocked from edit_subject (subjects_edit not granted)
    r = c.get(f'/subjects/{subj_id}/edit', follow_redirects=False)
    assert r.status_code in (302, 303)


def test_results_scores_view_without_enter(app):
    _subj_teacher(app, 'rsco_v', {'results.scores_view': 'view'})
    c = _login(app, 'rsco_v')
    assert c.get('/subjects/scores').status_code == 200
    tok = _ptoken(c)
    r = c.post('/subjects/scores/save', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)        # scores_enter not granted


def test_results_scores_enter_blocked_from_bulk_import_even_with_unrelated_edit(app):
    # Regression test for the gap this phase closes: before the split, these 4
    # bulk-import endpoints were unmapped and rode on whole-module edit access,
    # so a user granted edit on an unrelated key alone would've reached them.
    _make(app, 'rsco_e', {'results.scores_enter': 'edit', 'results.subjects_edit': 'edit'})
    c = _login(app, 'rsco_e')
    tok = _ptoken(c)
    r = c.get('/subjects/scores/scan', follow_redirects=False)
    assert r.status_code in (302, 303)        # scores_bulk_import not granted
    r2 = c.post('/subjects/scores/broadsheet-import', data={'_csrf_token': tok}, follow_redirects=False)
    assert r2.status_code in (302, 303)


def test_results_scores_bulk_import_without_enter(app):
    _subj_teacher(app, 'rsco_b', {'results.scores_bulk_import': 'edit'})
    c = _login(app, 'rsco_b')
    assert c.get('/subjects/scores/scan').status_code == 200
    tok = _ptoken(c)
    r = c.post('/subjects/scores/save', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)        # scores_enter not granted


def test_results_broadsheet_view_without_export(app):
    _make(app, 'rsbv', {'results.broadsheet_view': 'view'})
    c = _login(app, 'rsbv')
    assert c.get('/subjects/broadsheet').status_code == 200
    assert c.get('/subjects/broadsheet/explore').status_code == 200   # also closed gap
    r = c.get('/subjects/broadsheet/export', follow_redirects=False)
    assert r.status_code in (302, 303)        # broadsheet_export is a separate slice
    r2 = c.get('/subjects/broadsheet/explore/export', follow_redirects=False)
    assert r2.status_code in (302, 303)


def test_results_reportcard_view_requires_cards_capability_too(app):
    # Regression test proving the dual gate: holding reportcard_view alone
    # (without the central-admin-only 'cards' capability) is still blocked.
    with app.app_context():
        st = Student.query.filter_by(student_id='RSRC-STU').first()
        if not st:
            st = Student(student_id='RSRC-STU', first_name='Rc', surname='Kid',
                        gender='Male', is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.commit()
        sid = st.id
    _make(app, 'rsrc_v', {'results.reportcard_view': 'edit'})
    c = _login(app, 'rsrc_v')
    r = c.get(f'/subjects/report-card/{sid}', follow_redirects=False)
    assert r.status_code in (302, 303)        # 'cards' capability not granted

    _make(app, 'rsrc_v2', {'results.reportcard_view': 'edit', 'results.cards': 'edit'})
    c2 = _login(app, 'rsrc_v2')
    assert c2.get(f'/subjects/report-card/{sid}').status_code == 200
    # still blocked from the batch tier (needs reportcard_batch too)
    r2 = c2.get('/subjects/report-cards/pdf', follow_redirects=False)
    assert r2.status_code in (302, 303)


def test_results_analytics_view_without_export(app):
    _make(app, 'rsav', {'results.analytics_view': 'view'})
    c = _login(app, 'rsav')
    assert c.get('/subjects/analytics').status_code == 200
    r = c.get('/subjects/analytics/report.pdf', follow_redirects=False)
    assert r.status_code in (302, 303)        # analytics_export is a separate slice


def test_results_institution_email_stays_admin_only(app):
    # institution_email / institution_auto_email hard-check is_admin() inline
    # and stay unmapped by design — confirm a non-admin stays blocked even
    # holding full analytics_view + analytics_export.
    _make(app, 'rsie', {'results.analytics_view': 'edit', 'results.analytics_export': 'edit'})
    c = _login(app, 'rsie')
    tok = _ptoken(c)
    r = c.post('/subjects/analytics/institution/email', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)


def test_results_scores_tools_without_enter(app):
    term_id, class_id = _subj_term_class(app, 'RST')
    with app.app_context():
        arm = ClassArm.query.filter_by(name='RST-Arm').first() or ClassArm(name='RST-Arm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=class_id, term_id=term_id, arm_id=arm.id).first()
        if not caa:
            caa = ClassArmAssignment(class_id=class_id, arm_id=arm.id, term_id=term_id,
                                     branch_id=Branch.get_default().id)
            db.session.add(caa); db.session.commit()
        assignment_id = caa.id
    _make(app, 'rstv', {'results.scores_tools': 'edit'})
    c = _login(app, 'rstv')
    tok = _ptoken(c)
    c.post('/subjects/broadsheet/compute',
           data={'term_id': term_id, 'assignment_id': assignment_id, '_csrf_token': tok})
    r = c.post('/subjects/scores/save', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)        # scores_enter not granted


def test_results_workflow_reachable_with_subjects_view_alone(app):
    _make(app, 'rswf', {'results.subjects_view': 'view'})
    c = _login(app, 'rswf')
    assert c.get('/subjects/workflow').status_code == 200


# ---- CBT (20-key granular split; settings/passwords stay admin-only) ------

def _cbt_exam(app, tag, **kw):
    from models import CBTExam
    with app.app_context():
        e = CBTExam.query.filter_by(title=f'{tag}-Exam').first()
        if not e:
            e = CBTExam(title=f'{tag}-Exam', access_password='pw12345',
                        branch_id=Branch.get_default().id, **kw)
            db.session.add(e); db.session.commit()
        return e.id


def test_cbt_exams_view_without_create(app):
    _make(app, 'cbtev', {'cbt.exams_view': 'view'})
    c = _login(app, 'cbtev')
    assert c.get('/cbt/').status_code == 200
    r = c.get('/cbt/exams/add', follow_redirects=False)
    assert r.status_code in (302, 303)        # exams_create not granted


def test_cbt_exams_create_without_edit_or_delete(app):
    _make(app, 'cbtec', {'cbt.exams_create': 'edit'})
    c = _login(app, 'cbtec')
    tok = _ptoken(c)
    c.post('/cbt/exams/add', data={'title': 'CBTEC-Exam', 'access_password': 'secretpw',
                                   '_csrf_token': tok})
    with app.app_context():
        from models import CBTExam
        exam = CBTExam.query.filter_by(title='CBTEC-Exam').first()
        assert exam is not None
        eid = exam.id
    r = c.get(f'/cbt/exams/{eid}/edit', follow_redirects=False)
    assert r.status_code in (302, 303)
    c.post(f'/cbt/exams/{eid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        from models import CBTExam
        assert db.session.get(CBTExam, eid) is not None


def test_cbt_exams_edit_blocked_from_publish_even_with_unrelated_edit(app):
    # Regression test for the gap this phase closes: before the split, the
    # whole 'exams' bucket conflated metadata edit with publish (makes an
    # exam live to the whole student body). Confirm exams_edit alone, even
    # alongside an unrelated edit grant (bank_create), cannot publish.
    eid = _cbt_exam(app, 'CBTPUB')
    _make(app, 'cbtpu', {'cbt.exams_edit': 'edit', 'cbt.bank_create': 'edit'})
    c = _login(app, 'cbtpu')
    tok = _ptoken(c)
    c.post(f'/cbt/exams/{eid}/publish', data={'_csrf_token': tok})
    with app.app_context():
        from models import CBTExam
        assert db.session.get(CBTExam, eid).is_published is False


def test_cbt_exams_questions_edit_without_bulk(app):
    eid = _cbt_exam(app, 'CBTQE')
    _make(app, 'cbtqe', {'cbt.exams_questions_edit': 'edit'})
    c = _login(app, 'cbtqe')
    tok = _ptoken(c)
    with app.app_context():
        from models import CBTQuestion
        before = CBTQuestion.query.filter_by(exam_id=eid).count()
    c.post(f'/cbt/exams/{eid}/questions/add',
           data={'question_text': 'What is 2+2?', 'correct_option': 'A',
                 'option_a': '4', 'option_b': '5', '_csrf_token': tok})
    with app.app_context():
        from models import CBTQuestion
        assert CBTQuestion.query.filter_by(exam_id=eid).count() == before + 1
    r = c.get(f'/cbt/exams/{eid}/import-bank', follow_redirects=False)
    assert r.status_code in (302, 303)        # exams_questions_bulk not granted


def test_cbt_bank_create_without_delete(app):
    _make(app, 'cbtbc', {'cbt.bank_create': 'edit'})
    c = _login(app, 'cbtbc')
    tok = _ptoken(c)
    c.post('/cbt/bank/add', data={'question_text': 'Bank Q1', 'correct_option': 'A',
                                  'option_a': 'x', 'option_b': 'y', '_csrf_token': tok})
    with app.app_context():
        from models import QuestionBank
        q = QuestionBank.query.filter_by(question_text='Bank Q1').first()
        assert q is not None
        qid = q.id
    c.post(f'/cbt/bank/{qid}/delete', data={'_csrf_token': tok})
    with app.app_context():
        from models import QuestionBank
        assert db.session.get(QuestionBank, qid) is not None   # bank_delete not granted


def test_cbt_syllabus_create_without_delete_or_seed(app):
    with app.app_context():
        subj = Subject.query.filter_by(name='CBT-Syl-Subject').first() or Subject(name='CBT-Syl-Subject', is_active=True)
        db.session.add(subj); db.session.commit()
        subj_id = subj.id
    _make(app, 'cbtsc', {'cbt.syllabus_create': 'edit'})
    c = _login(app, 'cbtsc')
    tok = _ptoken(c)
    c.post('/cbt/syllabus/add', data={'subject_id': subj_id, 'title': 'CBT Topic 1', '_csrf_token': tok})
    with app.app_context():
        from models import SyllabusTopic
        topic = SyllabusTopic.query.filter_by(subject_id=subj_id, title='CBT Topic 1').first()
        assert topic is not None
        topic_id = topic.id
    c.post(f'/cbt/syllabus/{topic_id}/delete', data={'_csrf_token': tok})
    with app.app_context():
        from models import SyllabusTopic
        assert db.session.get(SyllabusTopic, topic_id) is not None   # syllabus_delete not granted
    r = c.post('/cbt/syllabus/seed', data={'subject_id': subj_id, '_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)        # syllabus_seed not granted


def test_cbt_monitor_view_blocked_from_force_submit(app):
    # Regression test for the closed gap: force_submit was previously hard
    # admin-only; now it must be blocked by subsection absence for a plain
    # monitor_view holder, not merely by role.
    eid = _cbt_exam(app, 'CBTMON')
    with app.app_context():
        st = Student.query.filter_by(student_id='CBTMON-STU').first()
        if not st:
            st = Student(student_id='CBTMON-STU', first_name='Cbt', surname='Mon',
                        gender='Male', is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.commit()
        from models import CBTAttempt
        att = CBTAttempt(exam_id=eid, student_id=st.id, status='In progress')
        db.session.add(att); db.session.commit()
        att_id = att.id
    _make(app, 'cbtmv', {'cbt.monitor_view': 'view'})
    c = _login(app, 'cbtmv')
    assert c.get(f'/cbt/exams/{eid}/monitor').status_code == 200
    tok = _ptoken(c)
    c.post(f'/cbt/attempts/{att_id}/force-submit', data={'_csrf_token': tok})
    with app.app_context():
        from models import CBTAttempt
        assert db.session.get(CBTAttempt, att_id).status == 'In progress'


def test_cbt_monitor_force_submit_with_view_can_force_submit(app):
    eid = _cbt_exam(app, 'CBTMON2')
    with app.app_context():
        st = Student.query.filter_by(student_id='CBTMON2-STU').first()
        if not st:
            st = Student(student_id='CBTMON2-STU', first_name='Cbt', surname='Mon2',
                        gender='Male', is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.commit()
        from models import CBTAttempt
        att = CBTAttempt(exam_id=eid, student_id=st.id, status='In progress')
        db.session.add(att); db.session.commit()
        att_id = att.id
    _make(app, 'cbtmf', {'cbt.monitor_view': 'view', 'cbt.monitor_force_submit': 'edit'})
    c = _login(app, 'cbtmf')
    tok = _ptoken(c)
    c.post(f'/cbt/attempts/{att_id}/force-submit', data={'_csrf_token': tok})
    with app.app_context():
        from models import CBTAttempt
        assert db.session.get(CBTAttempt, att_id).status == 'Submitted'


def test_cbt_results_view_without_export(app):
    eid = _cbt_exam(app, 'CBTRV')
    _make(app, 'cbtrv', {'cbt.results_view': 'view'})
    c = _login(app, 'cbtrv')
    assert c.get(f'/cbt/exams/{eid}/results').status_code == 200
    r = c.get(f'/cbt/exams/{eid}/results/export', follow_redirects=False)
    assert r.status_code in (302, 303)        # results_export is a separate slice


def test_cbt_settings_and_passwords_stay_admin_only(app):
    # settings / passwords are deliberately left out of the grant system
    # (literal secrets: the supervisor-PIN override and student portal
    # credentials) — confirm a non-admin, non-central-scope user stays
    # blocked even holding full exams_edit + monitor_force_submit.
    # (passwords' own check is `is_central() or is_admin()`, so a
    # central-scoped non-admin would pass — use branch scope to isolate
    # the admin-only behaviour this test is about.)
    with app.app_context():
        u = User.query.filter_by(username='cbtap').first()
        if not u:
            u = User(username='cbtap', role='staff', scope='branch',
                     branch_id=Branch.get_default().id, full_name='cbtap')
            u.set_password('secret123')
            db.session.add(u)
        u.set_permissions({'cbt.exams_edit': 'edit', 'cbt.monitor_force_submit': 'edit'})
        db.session.commit()
    c = _login(app, 'cbtap')
    tok = _ptoken(c)
    r = c.post('/cbt/settings', data={'_csrf_token': tok}, follow_redirects=False)
    assert r.status_code in (302, 303)
    r2 = c.get('/cbt/passwords', follow_redirects=False)
    assert r2.status_code == 403


# ---- Promotion (14-key granular split; set_alumni_password stays admin-only) --

def _promo_classes(app, tag):
    with app.app_context():
        from_cls = (SchoolClass.query.filter_by(name=f'{tag}-From').first()
                    or SchoolClass(name=f'{tag}-From', level=1))
        db.session.add(from_cls); db.session.flush()
        to_cls = (SchoolClass.query.filter_by(name=f'{tag}-To').first()
                  or SchoolClass(name=f'{tag}-To', level=2))
        db.session.add(to_cls); db.session.commit()
        return from_cls.id, to_cls.id


def _promo_enrolled_student(app, tag):
    """A student actively enrolled in ``tag``'s own session/term/class, so
    execute_promotion can find a 'current enrollment' to act on."""
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name=f'{tag}-Sess').first() or AcademicSession(name=f'{tag}-Sess')
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(name=f'{tag}-Term').first() or Term(session_id=ssn.id, term_number=1, name=f'{tag}-Term')
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name=f'{tag}-Class').first() or SchoolClass(name=f'{tag}-Class', level=3)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.filter_by(name=f'{tag}-Arm').first() or ClassArm(name=f'{tag}-Arm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=cls.id, arm_id=arm.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id))
        db.session.add(caa); db.session.flush()
        st = Student.query.filter_by(student_id=f'{tag}-STU').first()
        if not st:
            st = Student(student_id=f'{tag}-STU', first_name='Promo', surname=tag,
                         gender='Male', is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.flush()
        if not StudentEnrollment.query.filter_by(student_id=st.id, class_arm_assignment_id=caa.id).first():
            db.session.add(StudentEnrollment(student_id=st.id, class_arm_assignment_id=caa.id, is_active=True))
        db.session.commit()
        return st.id, ssn.id


def _promo_graduate(app, tag):
    with app.app_context():
        st = Student.query.filter_by(student_id=f'{tag}-GRAD').first()
        if not st:
            st = Student(student_id=f'{tag}-GRAD', first_name='Grad', surname=tag,
                        gender='Female', is_active=True, is_graduated=True,
                        graduate_status='Graduated', branch_id=Branch.get_default().id)
            db.session.add(st); db.session.commit()
        return st.id


def _promo_sss3_teacher(app, tag, perms):
    """A non-admin SSS3 form teacher, so they pass @graduates_access_required
    (admin-or-SSS3-form-teacher) and the subsection grant under test actually
    matters — an admin would bypass the subsection check entirely."""
    from models import Teacher, TeacherClassAssignment
    with app.app_context():
        ssn = AcademicSession.query.filter_by(name=f'{tag}-Sess').first() or AcademicSession(name=f'{tag}-Sess')
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(name=f'{tag}-Term').first() or Term(session_id=ssn.id, term_number=1, name=f'{tag}-Term')
        db.session.add(term); db.session.flush()
        sss3 = SchoolClass.query.filter_by(name='SSS3').first() or SchoolClass(name='SSS3', level=9)
        db.session.add(sss3); db.session.flush()
        arm = ClassArm.query.filter_by(name=f'{tag}-Arm').first() or ClassArm(name=f'{tag}-Arm', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = (ClassArmAssignment.query.filter_by(class_id=sss3.id, arm_id=arm.id, term_id=term.id).first()
               or ClassArmAssignment(class_id=sss3.id, arm_id=arm.id, term_id=term.id, branch_id=Branch.get_default().id))
        db.session.add(caa); db.session.flush()
        username = tag.lower()
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='teacher', scope='central', full_name=username)
            u.set_password('secret123')
            db.session.add(u); db.session.flush()
        teacher = Teacher.query.filter_by(user_id=u.id).first()
        if not teacher:
            teacher = Teacher(user_id=u.id)
            db.session.add(teacher); db.session.flush()
        if not TeacherClassAssignment.query.filter_by(
                teacher_id=teacher.id, class_arm_assignment_id=caa.id).first():
            db.session.add(TeacherClassAssignment(
                teacher_id=teacher.id, class_arm_assignment_id=caa.id,
                is_form_teacher=True, is_active=True))
        u.set_permissions(perms)
        db.session.commit()
        return username


def test_promotion_view_blocked_from_rules_edit(app):
    _make(app, 'pview', {'promotion.promote_view': 'view'})
    c = _login(app, 'pview')
    assert c.get('/promotion/').status_code == 200
    assert c.get('/promotion/history').status_code == 200
    r = c.get('/promotion/rules/add', follow_redirects=False)
    assert r.status_code in (302, 303)        # promote_rules not granted


def test_promotion_rules_create_delete_blocked_from_execute(app):
    from_id, to_id = _promo_classes(app, 'PRUL')
    sid, ssn_id = _promo_enrolled_student(app, 'PRULX')
    _make(app, 'prul', {'promotion.promote_rules': 'edit'})
    c = _login(app, 'prul')
    tok = _ptoken(c)
    c.post('/promotion/rules/add', data={'from_class_id': from_id, 'to_class_id': to_id,
                                         'min_average': '50', 'priority': '0', '_csrf_token': tok})
    with app.app_context():
        rule = PromotionRule.query.filter_by(from_class_id=from_id, to_class_id=to_id).first()
        assert rule is not None and rule.is_active is True
        rule_id = rule.id
    c.post(f'/promotion/rules/{rule_id}/delete', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(PromotionRule, rule_id).is_active is False
    # Regression: before the split, any 'promote' edit grant implied the whole
    # bucket (including running the actual promotion). Confirm rules-only can't.
    with app.app_context():
        before = PromotionRecord.query.count()
    c.post('/promotion/execute', data={
        'from_session_id': ssn_id, 'to_session_id': ssn_id, 'student_id[]': [str(sid)], 'action[]': ['graduated'],
        '_csrf_token': tok,
    })
    with app.app_context():
        assert PromotionRecord.query.count() == before


def test_promotion_execute_can_run_blocked_from_rules_edit(app):
    sid, ssn_id = _promo_enrolled_student(app, 'PEXE')
    from_id, to_id = _promo_classes(app, 'PEXER')
    _make(app, 'pexe', {'promotion.promote_execute': 'edit'})
    c = _login(app, 'pexe')
    tok = _ptoken(c)
    c.post('/promotion/execute', data={
        'from_session_id': ssn_id, 'to_session_id': ssn_id, 'student_id[]': [str(sid)], 'action[]': ['graduated'],
        '_csrf_token': tok,
    })
    with app.app_context():
        record = PromotionRecord.query.filter_by(student_id=sid, from_session_id=ssn_id).first()
        assert record is not None and record.status == 'graduated'
        assert db.session.get(Student, sid).is_graduated is True
    with app.app_context():
        before = PromotionRule.query.count()
    c.post('/promotion/rules/add', data={'from_class_id': from_id, 'to_class_id': to_id,
                                         'min_average': '50', '_csrf_token': tok})
    with app.app_context():
        assert PromotionRule.query.count() == before      # promote_rules not granted


def test_promotion_graduate_status_mark_unmark_blocked_from_execute(app):
    with app.app_context():
        st = Student.query.filter_by(student_id='PGSM-STU').first()
        if not st:
            st = Student(student_id='PGSM-STU', first_name='Mark', surname='Me',
                        gender='Male', is_active=True, branch_id=Branch.get_default().id)
            db.session.add(st); db.session.commit()
        sid = st.id
    _make(app, 'pgsm', {'promotion.promote_graduate_status': 'edit'})
    c = _login(app, 'pgsm')
    tok = _ptoken(c)
    c.post(f'/promotion/graduate/{sid}', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Student, sid).is_graduated is True
    c.post(f'/promotion/ungraduate/{sid}', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Student, sid).is_graduated is False
    exec_sid, ssn_id = _promo_enrolled_student(app, 'PGSMX')
    with app.app_context():
        before = PromotionRecord.query.count()
    c.post('/promotion/execute', data={
        'from_session_id': ssn_id, 'to_session_id': ssn_id, 'student_id[]': [str(exec_sid)], 'action[]': ['graduated'],
        '_csrf_token': tok,
    })
    with app.app_context():
        assert PromotionRecord.query.count() == before    # promote_execute not granted


def test_promotion_change_graduate_status_blocks_deceased_for_non_admin(app):
    # Regression test closing the dormant RESTRICTED_STATUSES gap: before this
    # phase, change_graduate_status was hard admin-only; once it becomes an
    # ordinary grantable action, a non-admin holder must still be unable to
    # set a graduate's status to 'Deceased'.
    sid = _promo_graduate(app, 'PGSD')
    _make(app, 'pgsd', {'promotion.promote_graduate_status': 'edit'})
    c = _login(app, 'pgsd')
    tok = _ptoken(c)
    c.post(f'/promotion/graduates/{sid}/status',
           data={'status': 'Deceased', 'reason': 'test', '_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Student, sid).graduate_status != 'Deceased'
    # a non-restricted status change still works with the same grant
    c.post(f'/promotion/graduates/{sid}/status',
           data={'status': 'Certificate Issued', 'reason': 'test', '_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Student, sid).graduate_status == 'Certificate Issued'


def test_promotion_change_graduate_status_allows_deceased_for_admin(app):
    sid = _promo_graduate(app, 'PGSA')
    with app.app_context():
        u = User.query.filter_by(username='pgsa').first()
        if not u:
            u = User(username='pgsa', role='admin', scope='central', full_name='pgsa')
            u.set_password('secret123')
            db.session.add(u); db.session.commit()
    c = _login(app, 'pgsa')
    tok = _ptoken(c)
    c.post(f'/promotion/graduates/{sid}/status',
           data={'status': 'Deceased', 'reason': 'test', '_csrf_token': tok})
    with app.app_context():
        assert db.session.get(Student, sid).graduate_status == 'Deceased'


def test_promotion_graduates_sss3_view_blocked_from_alumni_edit(app):
    _make(app, 'pgs3', {'promotion.graduates_sss3': 'edit'})
    c = _login(app, 'pgs3')
    assert c.get('/promotion/graduate-sss3/preview').status_code == 200
    sid = _promo_graduate(app, 'PGS3X')
    tok = _ptoken(c)
    c.post(f'/promotion/graduates/{sid}/alumni', data={'occupation': 'Engineer', '_csrf_token': tok})
    with app.app_context():
        from models import AlumniProfile
        prof = AlumniProfile.query.filter_by(student_id=sid).first()
        assert prof is None or prof.occupation != 'Engineer'   # graduates_alumni_edit not granted


def test_promotion_alumni_edit_blocked_from_sss3(app):
    sid = _promo_graduate(app, 'PAED')
    _make(app, 'paed', {'promotion.graduates_alumni_edit': 'edit'})
    c = _login(app, 'paed')
    tok = _ptoken(c)
    c.post(f'/promotion/graduates/{sid}/alumni', data={'occupation': 'Pilot', '_csrf_token': tok})
    with app.app_context():
        from models import AlumniProfile
        prof = AlumniProfile.query.filter_by(student_id=sid).first()
        assert prof is not None and prof.occupation == 'Pilot'
    r = c.get('/promotion/graduate-sss3/preview', follow_redirects=False)
    assert r.status_code in (302, 303)        # graduates_sss3 not granted


def test_promotion_set_alumni_password_stays_admin_only(app):
    # Credential write (alumni portal login) — stays hard admin-only, same
    # treatment as HR's device-token and CBT's settings/passwords, even for a
    # user holding every other promotion key.
    sid = _promo_graduate(app, 'PSAP')
    _make(app, 'psap', {'promotion.promote_view': 'edit', 'promotion.promote_rules': 'edit',
                        'promotion.promote_execute': 'edit', 'promotion.promote_graduate_status': 'edit',
                        'promotion.graduates_sss3': 'edit', 'promotion.graduates_alumni_edit': 'edit',
                        'promotion.documents_generate': 'edit', 'promotion.documents_bulk_generate': 'edit',
                        'promotion.documents_templates': 'edit', 'promotion.documents_requests': 'edit',
                        'promotion.alumni_view': 'edit', 'promotion.alumni_export': 'edit',
                        'promotion.alumni_bulk_email': 'edit'})
    c = _login(app, 'psap')
    tok = _ptoken(c)
    c.post(f'/promotion/graduates/{sid}/portal-password',
           data={'password': 'secretpw1', '_csrf_token': tok})
    with app.app_context():
        st = db.session.get(Student, sid)
        assert not st.check_portal_password('secretpw1')


def test_promotion_documents_generate_blocked_from_bulk(app):
    sid = _promo_graduate(app, 'PDGN')
    _make(app, 'pdgn', {'promotion.documents_generate': 'edit'})
    c = _login(app, 'pdgn')
    r = c.get(f'/promotion/graduates/{sid}/document/statement')
    assert r.status_code == 200
    tok = _ptoken(c)
    c.post(f'/promotion/graduates/{sid}/document/statement/revoke', data={'_csrf_token': tok})
    with app.app_context():
        from models import GraduateDocument
        doc = GraduateDocument.query.filter_by(student_id=sid, doc_type='statement').first()
        assert doc is not None and doc.revoked is True
    r2 = c.get('/promotion/graduates/documents/bulk?doc_type=statement', follow_redirects=False)
    assert r2.status_code in (302, 303)        # documents_bulk_generate not granted


def test_promotion_documents_bulk_generate_blocked_from_single(app):
    _promo_graduate(app, 'PDBG')
    _make(app, 'pdbg', {'promotion.documents_bulk_generate': 'edit'})
    c = _login(app, 'pdbg')
    assert c.get('/promotion/graduates/documents/bulk?doc_type=statement').status_code == 200
    sid2 = _promo_graduate(app, 'PDBG2')
    r = c.get(f'/promotion/graduates/{sid2}/document/statement', follow_redirects=False)
    assert r.status_code in (302, 303)         # documents_generate not granted


def test_promotion_documents_templates_blocked_from_requests(app):
    # doc_templates is additionally gated by @graduates_access_required
    # (admin-or-SSS3-form-teacher); use a non-admin SSS3 form teacher so the
    # documents_templates grant itself is actually what's being tested.
    username = _promo_sss3_teacher(app, 'PDTE', {'promotion.documents_templates': 'edit'})
    c = _login(app, username)
    assert c.get('/promotion/doc-templates').status_code == 200
    tok = _ptoken(c)
    c.post('/promotion/doc-templates/branding', data={'motto': 'Test Motto', '_csrf_token': tok})
    with app.app_context():
        from models import SchoolSettings
        assert SchoolSettings.get('school_motto') == 'Test Motto'
    from models import DocumentRequest
    sid = _promo_graduate(app, 'PDTEX')
    with app.app_context():
        req = DocumentRequest(student_id=sid, doc_type='statement', status='pending')
        db.session.add(req); db.session.commit()
        req_id = req.id
    r = c.get(f'/promotion/alumni/requests/{req_id}/fulfil', follow_redirects=False)
    assert r.status_code in (302, 303)        # documents_requests not granted


def test_promotion_documents_requests_fulfil_decline(app):
    from models import DocumentRequest
    sid = _promo_graduate(app, 'PDRQ')
    with app.app_context():
        req1 = DocumentRequest(student_id=sid, doc_type='statement', status='pending')
        req2 = DocumentRequest(student_id=sid, doc_type='transcript', status='pending')
        db.session.add_all([req1, req2]); db.session.commit()
        req1_id, req2_id = req1.id, req2.id
    _make(app, 'pdrq', {'promotion.documents_requests': 'edit'})
    c = _login(app, 'pdrq')
    assert c.get(f'/promotion/alumni/requests/{req1_id}/fulfil').status_code == 200
    with app.app_context():
        assert db.session.get(DocumentRequest, req1_id).status == 'fulfilled'
    tok = _ptoken(c)
    c.post(f'/promotion/alumni/requests/{req2_id}/decline', data={'_csrf_token': tok})
    with app.app_context():
        assert db.session.get(DocumentRequest, req2_id).status == 'declined'
    # blocked from documents_generate's direct-issue endpoint
    r = c.get(f'/promotion/graduates/{sid}/document/conduct', follow_redirects=False)
    assert r.status_code in (302, 303)


def test_promotion_documents_verifications_view(app):
    # document_verifications is additionally gated by @graduates_access_required.
    username = _promo_sss3_teacher(app, 'PDVE', {'promotion.documents_verifications': 'view'})
    c = _login(app, username)
    assert c.get('/promotion/graduates/documents/verifications').status_code == 200


def test_promotion_alumni_view_blocked_from_export(app):
    # alumni_directory/alumni_analytics are additionally gated by
    # @graduates_access_required; use a non-admin SSS3 form teacher so the
    # alumni_view grant itself is actually what's being tested.
    username = _promo_sss3_teacher(app, 'PAVE', {'promotion.alumni_view': 'view'})
    c = _login(app, username)
    assert c.get('/promotion/alumni').status_code == 200
    assert c.get('/promotion/alumni/analytics').status_code == 200
    r = c.get('/promotion/alumni/export', follow_redirects=False)
    assert r.status_code in (302, 303)        # alumni_export not granted


def test_promotion_alumni_export_blocked_from_bulk_email(app):
    # alumni_export is additionally gated by @graduates_access_required.
    username = _promo_sss3_teacher(app, 'PAEX', {'promotion.alumni_export': 'edit'})
    c = _login(app, username)
    assert c.get('/promotion/alumni/export').status_code == 200
    tok = _ptoken(c)
    r = c.post('/promotion/alumni/bulk-email',
              data={'subject': 'Hi', 'body': 'Hello', '_csrf_token': tok}, follow_redirects=False)
    # Blocked by the subsection gate (-> main dashboard), not by the
    # unrelated "email not configured" business check (-> alumni directory).
    assert r.status_code in (302, 303)
    assert '/promotion/alumni' not in (r.headers.get('Location') or '')


def test_promotion_alumni_bulk_email_reaches_handler_blocked_from_export(app):
    _make(app, 'pabe', {'promotion.alumni_bulk_email': 'edit'})
    c = _login(app, 'pabe')
    tok = _ptoken(c)
    r = c.post('/promotion/alumni/bulk-email',
              data={'subject': 'Hi', 'body': 'Hello', '_csrf_token': tok}, follow_redirects=False)
    # Permission passed through to the view (redirects back to the alumni
    # page, not the dashboard) even though sending itself fails without SMTP.
    assert r.status_code in (302, 303)
    assert '/promotion/alumni' in (r.headers.get('Location') or '')
    r2 = c.get('/promotion/alumni/export', follow_redirects=False)
    assert r2.status_code in (302, 303)        # alumni_export not granted


