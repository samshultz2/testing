"""Timetable generator: backend PDF/image exports for the single-arm print
view, the teacher-workload report, and the unassigned/empty-slots report —
plus the empty-slot-count accuracy fix in _unassigned_rows() and the bulk
all-teachers PDF / active-batch default on the teacher-timetable page."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenTimetableResult, GenTimetableRule, ActiveTimetableBatch,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _pdf_page_count(data):
    """Count PDF pages without needing pypdf (not installed in this env) —
    every page object in a reportlab-produced file has a `/Type /Page`
    (not `/Pages`) entry, so this is a reliable proxy for page count."""
    import re
    return len(re.findall(rb'/Type\s*/Page(?!s)', data))


def _seed_single_class(app, tag, periods_per_day=8):
    """One class-arm with a teacher-taught subject in period 1 on Monday and
    nothing else — enough to exercise print_single_timetable_pdf and the
    empty-slot counter without pulling in the full solver."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzRepSSS1{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}')
        subj = GenSubject(branch_id=bid, name=f'ZzMaths{tag}', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()

        teacher = GenTeacher(branch_id=bid, name=f'Zz Teacher{tag}', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(teacher); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzArm{tag}'))

        db.session.add(GenTimetableRule(branch_id=bid, rule_type='periods_per_day',
                                        value=str(periods_per_day), school_level='sss', is_active=True))

        batch_id = f'zzbatch-report-{tag}'
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=batch_id, school_level='sss',
            class_name=f'ZzRepSSS1{tag}', arm_name=f'ZzArm{tag}', day_of_week=0,
            period_number=1, subject_id=subj.id, teacher_id=teacher.id))
        db.session.commit()
        return batch_id, teacher.id


def test_print_single_timetable_pdf_is_a4_landscape_one_page(app):
    batch_id, _ = _seed_single_class(app, 'P')
    c = _admin(app)

    r = c.get(f'/generator/results/{batch_id}/print/ZzRepSSS1P/ZzArmP/pdf')
    assert r.status_code == 200
    assert r.mimetype == 'application/pdf'
    assert len(r.data) > 500
    assert _pdf_page_count(r.data) == 1

    # A4 landscape page dimensions (841.89 x 595.27 pt) appear verbatim in
    # the uncompressed PDF's /MediaBox — a cheap way to confirm orientation
    # without a PDF-parsing library.
    assert b'841.8' in r.data and b'595.2' in r.data


def test_print_single_timetable_pdf_teacher_toggle(app):
    batch_id, _ = _seed_single_class(app, 'Q')
    c = _admin(app)

    r_with = c.get(f'/generator/results/{batch_id}/print/ZzRepSSS1Q/ZzArmQ/pdf?teachers=1')
    r_without = c.get(f'/generator/results/{batch_id}/print/ZzRepSSS1Q/ZzArmQ/pdf?teachers=0')
    assert r_with.status_code == 200 and r_without.status_code == 200
    # Including the teacher's name adds text content, so the encoded stream
    # bytes should differ (and typically be larger) between the two.
    assert r_with.data != r_without.data


def test_print_single_timetable_pdf_404_redirects(app):
    c = _admin(app)
    r = c.get('/generator/results/nope/print/NoClass/NoArm/pdf')
    assert r.status_code == 302


def test_teacher_workload_report_image_and_pdf(app):
    batch_id, teacher_id = _seed_single_class(app, 'R')
    c = _admin(app)

    r_page = c.get(f'/generator/reports/teacher-workload/{batch_id}')
    assert r_page.status_code == 200
    body = r_page.get_data(as_text=True)
    assert 'teacher_workload_report_image' in body or 'Image (HD)' in body
    assert 'teacher_workload_report_pdf' in body or 'PDF' in body

    r_img = c.get(f'/generator/reports/teacher-workload/{batch_id}/image')
    assert r_img.status_code == 200
    assert r_img.mimetype == 'image/png'
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(r_img.data))
    assert img.width > 0 and img.height > 0

    r_pdf = c.get(f'/generator/reports/teacher-workload/{batch_id}/pdf')
    assert r_pdf.status_code == 200
    assert r_pdf.mimetype == 'application/pdf'
    assert len(r_pdf.data) > 500


def test_unassigned_report_counts_every_period_including_pre_break(app):
    """Regression test for the undercounting bug: the old code excluded the
    period right before the break from ever counting as empty. Seed a batch
    where periods_per_day=8, break_after=4, and ONLY period 4 (immediately
    before the break) is empty for Monday — the old code would have reported
    0 empty slots for Monday; the fix must report 1."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name='ZzRepSSS1UnasgS', school_level='sss',
                            num_arms=1, arm_names='ZzArmUnasgS')
        subj = GenSubject(branch_id=bid, name='ZzMathsUnasgS', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()
        db.session.add(GenTimetableRule(branch_id=bid, rule_type='periods_per_day',
                                        value='8', school_level='sss', is_active=True))
        db.session.add(GenTimetableRule(branch_id=bid, rule_type='break_after_period',
                                        value='4', school_level='sss', is_active=True))

        batch_id = 'zzbatch-report-unasg-s'
        # Fill Monday periods 1,2,3 and 5,6,7,8 — only period 4 (pre-break) empty.
        for p in [1, 2, 3, 5, 6, 7, 8]:
            db.session.add(GenTimetableResult(
                branch_id=bid, batch_id=batch_id, school_level='sss',
                class_name='ZzRepSSS1UnasgS', arm_name='ZzArmUnasgS', day_of_week=0,
                period_number=p, subject_id=subj.id))
        db.session.commit()

    c = _admin(app)
    r = c.get(f'/generator/reports/unassigned/{batch_id}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # 1 empty slot on Monday (period 4), plus 8 fully-empty days (Tue-Fri = 4*8=32)
    # -> weekly total for this one class-arm = 1 + 32 = 33.
    assert '33' in body


def test_unassigned_report_table_layout_class_arm_rows_day_columns(app):
    batch_id, _ = _seed_single_class(app, 'T')
    c = _admin(app)
    r = c.get(f'/generator/reports/unassigned/{batch_id}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'ZzRepSSS1T' in body and 'ZzArmT' in body
    assert 'Mon' in body and 'Total' in body


def test_unassigned_report_image_and_pdf(app):
    batch_id, _ = _seed_single_class(app, 'U')
    c = _admin(app)

    r_img = c.get(f'/generator/reports/unassigned/{batch_id}/image')
    assert r_img.status_code == 200
    assert r_img.mimetype == 'image/png'

    r_pdf = c.get(f'/generator/reports/unassigned/{batch_id}/pdf')
    assert r_pdf.status_code == 200
    assert r_pdf.mimetype == 'application/pdf'
    assert len(r_pdf.data) > 500


def _seed_two_teacher_batch(app, tag):
    """Two teachers, each with a few periods on one class-arm — enough to
    exercise the bulk all-teachers PDF's one-page-per-teacher pagination."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzRepSSS1{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}')
        subj1 = GenSubject(branch_id=bid, name=f'ZzMaths{tag}', school_level='sss')
        subj2 = GenSubject(branch_id=bid, name=f'ZzEng{tag}', school_level='sss')
        db.session.add_all([cc, subj1, subj2]); db.session.flush()

        t1 = GenTeacher(branch_id=bid, name=f'Zz Alpha Teacher{tag}', school_level='sss',
                        max_periods_per_day=6, max_periods_per_week=30)
        t2 = GenTeacher(branch_id=bid, name=f'Zz Beta Teacher{tag}', school_level='sss',
                        max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([t1, t2]); db.session.flush()
        db.session.add_all([
            GenTeacherAssignment(branch_id=bid, teacher_id=t1.id, subject_id=subj1.id,
                                 class_config_id=cc.id, arm_name=f'ZzArm{tag}'),
            GenTeacherAssignment(branch_id=bid, teacher_id=t2.id, subject_id=subj2.id,
                                 class_config_id=cc.id, arm_name=f'ZzArm{tag}'),
        ])
        db.session.add(GenTimetableRule(branch_id=bid, rule_type='periods_per_day',
                                        value='8', school_level='sss', is_active=True))

        batch_id = f'zzbatch-allteachers-{tag}'
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=batch_id, school_level='sss',
            class_name=f'ZzRepSSS1{tag}', arm_name=f'ZzArm{tag}', day_of_week=0,
            period_number=1, subject_id=subj1.id, teacher_id=t1.id))
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=batch_id, school_level='sss',
            class_name=f'ZzRepSSS1{tag}', arm_name=f'ZzArm{tag}', day_of_week=0,
            period_number=2, subject_id=subj2.id, teacher_id=t2.id))
        db.session.commit()
        return batch_id, bid


def test_print_all_teacher_timetables_pdf_one_page_per_teacher(app):
    batch_id, _ = _seed_two_teacher_batch(app, 'V')
    c = _admin(app)

    r = c.get(f'/generator/teacher-timetable/print-all-pdf?batch_id={batch_id}')
    assert r.status_code == 200
    assert r.mimetype == 'application/pdf'
    assert _pdf_page_count(r.data) == 2


def test_print_all_teacher_timetables_pdf_no_batch_id_falls_back(app):
    """No ?batch_id at all — the route must still resolve a batch the same
    way the teacher-timetable page's own default does (active batch, else
    most recent), not just error out."""
    batch_id, _ = _seed_two_teacher_batch(app, 'W')
    c = _admin(app)

    r = c.get('/generator/teacher-timetable/print-all-pdf')
    assert r.status_code == 200
    assert r.mimetype == 'application/pdf'


def test_teacher_timetable_download_all_link_present(app):
    batch_id, _ = _seed_two_teacher_batch(app, 'X')
    c = _admin(app)

    r = c.get(f'/generator/teacher-timetable?batch_id={batch_id}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'print_all_teacher_timetables_pdf' in body or 'print-all-pdf' in body
    assert 'Download All' in body


def test_teacher_timetable_defaults_to_active_batch_not_just_latest(app):
    """teacher_timetable() must default to the level's active/published
    batch when no ?batch_id is given — not simply the most recently
    generated one, which could be an old draft nobody is using."""
    older_batch, bid = _seed_two_teacher_batch(app, 'Y1')

    with app.app_context():
        cc = GenClassConfig(branch_id=bid, class_name='ZzRepSSS1Y2', school_level='sss',
                            num_arms=1, arm_names='ZzArmY2')
        subj = GenSubject(branch_id=bid, name='ZzMathsY2', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()
        t = GenTeacher(branch_id=bid, name='Zz Newer Teacher', school_level='sss',
                       max_periods_per_day=6, max_periods_per_week=30)
        db.session.add(t); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name='ZzArmY2'))
        newer_batch = 'zzbatch-allteachers-Y2-newer'
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=newer_batch, school_level='sss',
            class_name='ZzRepSSS1Y2', arm_name='ZzArmY2', day_of_week=0,
            period_number=1, subject_id=subj.id, teacher_id=t.id))
        db.session.commit()

        # The OLDER batch is the one marked "in use" — the newer one is just
        # a draft that happens to have a later generated_at. The test client
        # logs in as a central admin with no branch picked, so viewing_branch_id()
        # is None — the same scope results_list()'s active-batch lookup uses.
        ActiveTimetableBatch.set_active(None, 'sss', older_batch)
        db.session.commit()

    c = _admin(app)
    r = c.get('/generator/teacher-timetable')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f'value="{older_batch}"' in body and 'selected' in body
    # Confirm the *older* batch's option, specifically within the Batch
    # <select>, is the one marked selected (the page has other <select>s
    # too, e.g. the Teacher picker, whose own "selected" option must not
    # be mistaken for this one).
    import re
    select_m = re.search(r'<select name="batch_id"[^>]*>(.*?)</select>', body, re.DOTALL)
    assert select_m, 'batch_id <select> not found on the page'
    m = re.search(r'<option value="([^"]+)"[^>]*selected', select_m.group(1))
    assert m and m.group(1) == older_batch
