"""Timetable generator: the Teacher Assignment Summary report (a button on
/generator/assignments) — a per-teacher breakdown of what they're assigned
to teach and their weekly period total, plus its HD image and PDF exports."""
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenClassSubjectConfig, GenStream, GenStreamSubject, GenClassArmStream,
    GenClassStreamSubject,
)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def test_summary_all_arms_uniform_periods_and_total(app):
    """A single "all arms" assignment on a 3-arm class, all arms sharing the
    same periods_per_week -> "N periods each" and a correct weekly total."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name='ZzTAS1', school_level='sss',
                            num_arms=3, arm_names='ZzArmA,ZzArmB,ZzArmC')
        subj = GenSubject(branch_id=bid, name='ZzMathsTAS1', school_level='sss')
        teacher = GenTeacher(branch_id=bid, name='Zz Mr Uniform', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([cc, subj, teacher]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=4))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=None))
        db.session.commit()

    c = _admin(app)
    r = c.get('/generator/assignments/report')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Zz Mr Uniform' in body
    assert 'ZzTAS1 - ZzMathsTAS1 all arms 4 periods each' in body
    assert '12 periods/week' in body   # 3 arms * 4 periods


def test_summary_single_named_arm(app):
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name='ZzTAS2', school_level='sss',
                            num_arms=2, arm_names='ZzRoseTAS2,ZzLilyTAS2')
        subj = GenSubject(branch_id=bid, name='ZzGovtTAS2', school_level='sss')
        teacher = GenTeacher(branch_id=bid, name='Zz Miss Single', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([cc, subj, teacher]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=3))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name='ZzRoseTAS2'))
        db.session.commit()

    c = _admin(app)
    r = c.get('/generator/assignments/report')
    body = r.get_data(as_text=True)
    assert 'ZzTAS2 - ZzGovtTAS2 (ZzRoseTAS2) 3 periods' in body
    assert '3 periods/week' in body


def test_summary_two_teachers_multiple_subjects_and_total(app):
    """Mirrors the requested format: one teacher with two subject lines
    across two classes, each "all arms", summing to a correct total."""
    with app.app_context():
        bid = Branch.get_default().id
        cc1 = GenClassConfig(branch_id=bid, class_name='ZzTAS3A', school_level='sss',
                             num_arms=2, arm_names='X,Y')
        cc2 = GenClassConfig(branch_id=bid, class_name='ZzTAS3B', school_level='sss',
                             num_arms=1, arm_names='Z')
        s1 = GenSubject(branch_id=bid, name='ZzMathsTAS3', school_level='sss')
        s2 = GenSubject(branch_id=bid, name='ZzPhonicsTAS3', school_level='sss')
        teacher = GenTeacher(branch_id=bid, name='Zz Mr Multi', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([cc1, cc2, s1, s2, teacher]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc1.id, subject_id=s1.id,
                                             is_enabled=True, is_active=True, periods_per_week=4))
        db.session.add(GenClassSubjectConfig(class_config_id=cc2.id, subject_id=s2.id,
                                             is_enabled=True, is_active=True, periods_per_week=1))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=s1.id,
                                            class_config_id=cc1.id, arm_name=None))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=s2.id,
                                            class_config_id=cc2.id, arm_name=None))
        db.session.commit()

    c = _admin(app)
    r = c.get('/generator/assignments/report')
    body = r.get_data(as_text=True)
    assert 'ZzTAS3A - ZzMathsTAS3 all arms 4 periods each' in body
    assert 'ZzTAS3B - ZzPhonicsTAS3 all arms 1 period each' in body
    # 2 arms * 4 + 1 arm * 1 = 9
    assert '9 periods/week' in body


def test_summary_resolves_stream_specific_periods_per_arm(app):
    """A streamed class where two arms belong to different streams with
    different periods_per_week for the same subject -> the "all arms"
    assignment must report the true total, not assume uniformity."""
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name='ZzTAS4', school_level='sss',
                            num_arms=2, arm_names='ZzSci,ZzArt', has_streams=True)
        subj = GenSubject(branch_id=bid, name='ZzChemTAS4', school_level='sss')
        sci = GenStream(branch_id=bid, name='ZzScienceTAS4', school_level='sss')
        art = GenStream(branch_id=bid, name='ZzArtsTAS4', school_level='sss')
        teacher = GenTeacher(branch_id=bid, name='Zz Mr Stream', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([cc, subj, sci, art, teacher]); db.session.flush()

        db.session.add(GenClassArmStream(class_config_id=cc.id, arm_name='ZzSci', stream_id=sci.id))
        db.session.add(GenClassArmStream(class_config_id=cc.id, arm_name='ZzArt', stream_id=art.id))
        # Chemistry is a Science-stream subject at 5/week...
        db.session.add(GenStreamSubject(stream_id=sci.id, subject_id=subj.id, periods_per_week=5))
        # ...and also offered (nominally) in Arts, but a class-stream override
        # cuts it to 2/week there. A class-stream override only takes effect
        # for subjects that are actually GenStreamSubject members of that
        # stream in the first place — same as generate_with_ortools() itself.
        db.session.add(GenStreamSubject(stream_id=art.id, subject_id=subj.id, periods_per_week=5))
        db.session.add(GenClassStreamSubject(class_config_id=cc.id, stream_id=art.id,
                                             subject_id=subj.id, periods_per_week=2, is_enabled=True))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=None))
        db.session.commit()

    c = _admin(app)
    r = c.get('/generator/assignments/report')
    body = r.get_data(as_text=True)
    # Non-uniform (5 vs 2) -> total shown, not a false "N periods each".
    assert 'ZzTAS4 - ZzChemTAS4 all arms' in body
    assert '7 periods total' in body   # 5 + 2
    assert '7 periods/week' in body
    assert 'each' not in body.split('ZzTAS4 - ZzChemTAS4')[1].split('</li>')[0]


def test_summary_image_and_pdf_export(app):
    with app.app_context():
        bid = Branch.get_default().id
        cc = GenClassConfig(branch_id=bid, class_name='ZzTAS5', school_level='sss',
                            num_arms=1, arm_names='ZzOnlyArm')
        subj = GenSubject(branch_id=bid, name='ZzBioTAS5', school_level='sss')
        teacher = GenTeacher(branch_id=bid, name='Zz Mr Export', school_level='sss',
                             max_periods_per_day=6, max_periods_per_week=30)
        db.session.add_all([cc, subj, teacher]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=2))
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=teacher.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=None))
        db.session.commit()

    c = _admin(app)
    r_page = c.get('/generator/assignments/report')
    body = r_page.get_data(as_text=True)
    assert 'Image (HD)' in body and 'PDF' in body

    r_img = c.get('/generator/assignments/report/image')
    assert r_img.status_code == 200
    assert r_img.mimetype == 'image/png'
    from PIL import Image
    from io import BytesIO
    img = Image.open(BytesIO(r_img.data))
    assert img.width > 0 and img.height > 0

    r_pdf = c.get('/generator/assignments/report/pdf')
    assert r_pdf.status_code == 200
    assert r_pdf.mimetype == 'application/pdf'
    import fitz
    doc = fitz.open(stream=r_pdf.data, filetype='pdf')
    # A big school's worth of assignments can span multiple pages — this
    # report has no batch/date scope to narrow it down by, so search all
    # of them rather than assuming this test's own data lands on page 1.
    text = ''.join(page.get_text() for page in doc)
    doc.close()
    assert 'Zz Mr Export' in text
    assert 'ZzTAS5 - ZzBioTAS5 all arms 2 periods each' in text


def test_summary_button_present_on_assignments_page(app):
    c = _admin(app)
    r = c.get('/generator/assignments')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'teacher_assignment_summary_report' in body or 'Assignment Report' in body


def _seed_n_teachers(app, tag, n):
    """Seeds into a DEDICATED branch, not the shared default one --
    _teacher_assignment_summary() has no per-test scope of its own (it shows
    every teacher/assignment for the current branch), so without this,
    accumulated teachers from every other test in this session-scoped-DB
    suite would land in the same report and break any test that assumes a
    specific pairing/order/count. Returns the new branch's id."""
    with app.app_context():
        b = Branch(name=f'ZzTASBranch{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id
        cc = GenClassConfig(branch_id=bid, class_name=f'ZzTASN{tag}', school_level='sss',
                            num_arms=1, arm_names='ZzOnlyArm')
        subj = GenSubject(branch_id=bid, name=f'ZzSubjTASN{tag}', school_level='sss')
        db.session.add_all([cc, subj]); db.session.flush()
        db.session.add(GenClassSubjectConfig(class_config_id=cc.id, subject_id=subj.id,
                                             is_enabled=True, is_active=True, periods_per_week=2))
        for i in range(n):
            t = GenTeacher(branch_id=bid, name=f'Zz Teacher{tag}{i:02d}', school_level='sss',
                           max_periods_per_day=6, max_periods_per_week=30)
            db.session.add(t); db.session.flush()
            db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                                class_config_id=cc.id, arm_name=None))
        db.session.commit()
        return bid


def _scoped_to_branch(c, branch_id):
    """View just this one branch for the rest of this client's session, so
    reports scoped by gen_bid() see only that branch's data."""
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def test_pdf_download_forces_attachment_and_is_never_cached(app):
    """The reported bug: an inline PDF response with no cache headers lets
    Chrome (and especially a Google-Drive-viewer PDF handler) reuse a stale
    previously-viewed copy for the same URL. Must be a forced download
    (attachment, not inline) with headers that stop any cache -- browser or
    intermediate -- from ever serving a stale copy back."""
    bid = _seed_n_teachers(app, 'CACHE', 1)
    c = _scoped_to_branch(_admin(app), bid)
    r = c.get('/generator/assignments/report/pdf')
    assert r.status_code == 200
    assert 'attachment' in r.headers.get('Content-Disposition', '')
    cache_control = r.headers.get('Cache-Control', '')
    assert 'no-store' in cache_control and 'no-cache' in cache_control
    assert r.headers.get('Pragma') == 'no-cache'


def test_image_download_is_never_cached(app):
    bid = _seed_n_teachers(app, 'CACHEIMG', 1)
    c = _scoped_to_branch(_admin(app), bid)
    r = c.get('/generator/assignments/report/image')
    assert r.status_code == 200
    assert 'attachment' in r.headers.get('Content-Disposition', '')
    cache_control = r.headers.get('Cache-Control', '')
    assert 'no-store' in cache_control and 'no-cache' in cache_control


def test_pdf_is_landscape_for_more_horizontal_room(app):
    bid = _seed_n_teachers(app, 'LAND', 1)
    c = _scoped_to_branch(_admin(app), bid)
    r = c.get('/generator/assignments/report/pdf')
    import fitz
    doc = fitz.open(stream=r.data, filetype='pdf')
    try:
        page = doc[0]
        assert page.rect.width > page.rect.height, (
            f'expected landscape (wider than tall), got {page.rect.width}x{page.rect.height}')
    finally:
        doc.close()


def test_pdf_lays_out_two_teachers_side_by_side(app):
    """With several teachers, the second one's name should land noticeably to
    the right of the first's (same row, second column) rather than only ever
    stacking straight down the page. Scoped to a dedicated branch: pairing is
    by position in the FULL current-branch roster, so any other test's
    teachers sorting in between would silently break the row assumption."""
    bid = _seed_n_teachers(app, 'COLS', 4)
    c = _scoped_to_branch(_admin(app), bid)
    r = c.get('/generator/assignments/report/pdf')
    import fitz
    doc = fitz.open(stream=r.data, filetype='pdf')
    try:
        full_text = ''
        positions = {}
        for page in doc:
            full_text += page.get_text()
            for name in ('Zz TeacherCOLS00', 'Zz TeacherCOLS01'):
                hits = page.search_for(name)
                if hits:
                    positions[name] = hits[0]
        assert 'Zz TeacherCOLS00' in full_text and 'Zz TeacherCOLS01' in full_text
        assert len(positions) == 2, 'expected to locate both teacher names on the page'
        r0 = positions['Zz TeacherCOLS00']
        r1 = positions['Zz TeacherCOLS01']
        # Same row (close in y), clearly separated in x (second column).
        assert abs(r0.y0 - r1.y0) < 5
        assert r1.x0 - r0.x0 > 50
    finally:
        doc.close()


def test_image_lays_out_teachers_in_two_columns(app):
    """Same isolation concern as the PDF version above -- scoped to a
    dedicated branch so exactly 2 teachers (1 row) are in view."""
    bid = _seed_n_teachers(app, 'IMGCOLS', 2)
    c = _scoped_to_branch(_admin(app), bid)
    r = c.get('/generator/assignments/report/image')
    assert r.status_code == 200
    from PIL import Image as PILImage
    from io import BytesIO
    img = PILImage.open(BytesIO(r.data))
    # 2 teachers should fit in ONE row of the 2-column layout, so the image
    # should be far shorter than the old single-column-per-teacher layout
    # would have produced for the same data (title + 1 row, not title + 2
    # full teacher blocks stacked).
    assert img.height < 700, f'expected a short single-row image, got height {img.height}'
