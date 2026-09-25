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
