"""Generator streams are per school level (JSS vs SSS have their own), and the
menu's level switch drives which level's data the pages show."""
import itertools
from config import Config
from models import db, GenStream, Branch
from tests.conftest import login_token, auth_csrf

_SEQ = itertools.count()


def _bid(app):
    with app.app_context():
        return Branch.get_default().id


def test_same_named_stream_allowed_per_level(app):
    bid = _bid(app)
    with app.app_context():
        tag = next(_SEQ)
        nm = f'Science{tag}'
        db.session.add(GenStream(name=nm, school_level='jss', branch_id=bid, is_active=True))
        db.session.add(GenStream(name=nm, school_level='sss', branch_id=bid, is_active=True))
        db.session.commit()                      # unique is (branch, name, level) -> both ok
        assert GenStream.query.filter_by(name=nm, branch_id=bid).count() == 2


def test_streams_list_scoped_to_selected_level(app):
    bid = _bid(app)
    with app.app_context():
        tag = next(_SEQ)
        db.session.add(GenStream(name=f'JOnly{tag}', school_level='jss', branch_id=bid, is_active=True))
        db.session.add(GenStream(name=f'SOnly{tag}', school_level='sss', branch_id=bid, is_active=True))
        db.session.commit()

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})

    # Switch to JSS via the menu switcher (level_dashboard sets the session level).
    c.get('/generator/level/jss')
    body = c.get('/generator/streams').get_data(as_text=True)
    assert f'JOnly{tag}' in body and f'SOnly{tag}' not in body

    # Switch to SSS.
    c.get('/generator/level/sss')
    body = c.get('/generator/streams').get_data(as_text=True)
    assert f'SOnly{tag}' in body and f'JOnly{tag}' not in body


def test_day_clock_helper_defaults_and_custom():
    from utils.generator_times import clock_params, day_end_time
    # Historical defaults when unset.
    assert clock_params({}) == (8, 20, 40, 30)
    assert day_end_time({}, 8, 5) == '14:10'
    # A JSS-style day: 8:00 start, 40-min periods, 30-min break, 9 periods.
    jss = {'day_start': '8:00', 'period_minutes': '40', 'break_minutes': '30'}
    assert day_end_time(jss, 9, 5) == '14:30'
    # Malformed values fall back to defaults (never raise).
    assert clock_params({'day_start': 'nope', 'period_minutes': 'x'}) == (8, 20, 40, 30)
    # No break counted when it would fall outside the day.
    assert day_end_time({'day_start': '8:00', 'period_minutes': '40'}, 5, 6) == '11:20'


def test_day_timing_saved_and_scoped_per_level(app):
    """The School Day Timing form persists per level, and each level keeps its own."""
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})

    tok = auth_csrf(c)   # post-login CSRF token (login rotates it)

    # JSS: starts 08:00.
    c.get('/generator/level/jss')
    c.post('/generator/rules/save', data={
        '_csrf_token': tok, 'periods_per_day': '9', 'break_after_period': '5',
        'day_start': '08:00', 'period_minutes': '40', 'break_minutes': '30', 'max_consecutive': '3',
    })
    jss_body = c.get('/generator/rules').get_data(as_text=True)
    assert 'value="08:00"' in jss_body and 'School Day Timing' in jss_body

    # SSS: starts 08:20 — must not clobber the JSS value.
    c.get('/generator/level/sss')
    c.post('/generator/rules/save', data={
        '_csrf_token': tok, 'periods_per_day': '9', 'break_after_period': '5',
        'day_start': '08:20', 'period_minutes': '35', 'break_minutes': '20', 'max_consecutive': '3',
    })
    sss_body = c.get('/generator/rules').get_data(as_text=True)
    assert 'value="08:20"' in sss_body

    # JSS still reads back its own 08:00.
    c.get('/generator/level/jss')
    assert 'value="08:00"' in c.get('/generator/rules').get_data(as_text=True)


def test_exports_render_with_custom_break_position(app):
    """Excel/PDF/image exports must not index out of range when the break falls
    somewhere other than after period 5 (here: 7 periods/day, break after 3)."""
    from models import GenTimetableResult, GenTimetableRule, GenSubject, Branch
    tag = next(_SEQ)
    batch = f'ttbatch{tag}'
    with app.app_context():
        bid = Branch.get_default().id
        subj = GenSubject(name=f'Maths{tag}', short_name='MTH', school_level='sss',
                          branch_id=bid, is_active=True)
        db.session.add(subj)
        for rt, val in [('periods_per_day', '7'), ('break_after_period', '3'),
                        ('day_start', '8:00'), ('period_minutes', '40'), ('break_minutes', '30')]:
            db.session.add(GenTimetableRule(rule_type=rt, value=val, school_level='sss',
                                            is_active=True, branch_id=bid))
        db.session.flush()
        for d in range(5):
            for p in range(1, 8):
                db.session.add(GenTimetableResult(
                    branch_id=bid, batch_id=batch, school_level='sss',
                    class_name='SSS1', arm_name='A', day_of_week=d, period_number=p,
                    subject_id=subj.id))
        db.session.commit()

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c.get('/generator/level/sss')
    for url in (f'/generator/results/{batch}/export',
                f'/generator/results/{batch}/export_by_day',
                f'/generator/results/{batch}/export_by_day_pdf',
                f'/generator/results/{batch}/export_image'):
        r = c.get(url)
        assert r.status_code == 200, f'{url} -> {r.status_code}'
        assert len(r.get_data()) > 100, f'{url} produced an empty file'


def test_stream_subject_double_count_persists(app):
    """The stream page's 'Doubles/Week' count is saved, not hardcoded to 1."""
    from models import GenSubject, GenStreamSubject
    tag = next(_SEQ)
    with app.app_context():
        bid = Branch.get_default().id
        st = GenStream(name=f'Sci{tag}', school_level='sss', branch_id=bid, is_active=True)
        sub = GenSubject(name=f'Phy{tag}', short_name='PHY', school_level='sss', branch_id=bid, is_active=True)
        db.session.add_all([st, sub])
        db.session.commit()
        sid, subid = st.id, sub.id

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c.get('/generator/level/sss')
    c.post(f'/generator/streams/{sid}/subjects', data={
        '_csrf_token': auth_csrf(c),
        'subject_ids[]': str(subid),
        f'periods_{subid}': '6',
        f'double_{subid}': '1',
        f'double_count_{subid}': '2',
    })
    with app.app_context():
        row = GenStreamSubject.query.filter_by(stream_id=sid, subject_id=subid).first()
        assert row is not None and row.needs_double_period is True
        assert row.double_period_count == 2      # honoured the count, not hardcoded 1


def test_class_stream_double_count_persists_and_clamps(app):
    """Class-stream page saves its own count, clamped so 2×doubles <= periods."""
    from models import (GenSubject, GenClassConfig, GenClassArmStream,
                        GenClassStreamSubject, GenStreamSubject)
    tag = next(_SEQ)
    with app.app_context():
        bid = Branch.get_default().id
        st = GenStream(name=f'Art{tag}', school_level='sss', branch_id=bid, is_active=True)
        sub = GenSubject(name=f'Lit{tag}', short_name='LIT', school_level='sss', branch_id=bid, is_active=True)
        cc = GenClassConfig(class_name=f'SS{tag}', school_level='sss', branch_id=bid,
                            num_arms=1, arm_names='A', has_streams=True, is_active=True)
        db.session.add_all([st, sub, cc])
        db.session.commit()
        db.session.add(GenClassArmStream(class_config_id=cc.id, arm_name='A', stream_id=st.id))
        db.session.add(GenStreamSubject(stream_id=st.id, subject_id=sub.id, is_compulsory=True))
        db.session.commit()
        cid, sid, subid = cc.id, st.id, sub.id

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c.get('/generator/level/sss')
    # Ask for 5 doubles on a 4-period subject -> clamp to 4//2 = 2.
    c.post(f'/generator/classes/{cid}/stream-subjects/save', data={
        '_csrf_token': auth_csrf(c),
        'stream_id': str(sid),
        'subject_ids[]': str(subid),
        f'periods_{subid}': '4',
        f'double_{subid}': '1',
        f'double_count_{subid}': '5',
        f'enabled_{subid}': '1',
    })
    with app.app_context():
        row = GenClassStreamSubject.query.filter_by(
            class_config_id=cid, stream_id=sid, subject_id=subid).first()
        assert row is not None and row.needs_double_period is True
        assert row.double_period_count == 2      # clamped from 5 to periods//2


def test_double_resolution_priority_order():
    """class-stream > stream > per-class > global, count travels with the winner."""
    from utils.generator_doubles import resolve_double

    class L:
        def __init__(self, nd, dc):
            self.needs_double_period = nd
            self.double_period_count = dc

    css = L(True, 3); ss = L(True, 2); cls = L(True, 4); glob = L(True, 1)
    # Most specific present wins.
    assert resolve_double(css, ss, cls, glob) == (True, 3)
    # class-stream not asking -> stream wins.
    assert resolve_double(L(False, 0), ss, cls, glob) == (True, 2)
    # stream deferring (NULL) -> per-class wins.
    assert resolve_double(None, L(None, None), cls, glob) == (True, 4)
    # only global asks.
    assert resolve_double(None, None, L(False, 0), glob) == (True, 1)
    # nobody asks -> no double.
    assert resolve_double(None, None, None, L(False, 0)) == (False, 0)
    # enabled but blank count defaults to 1.
    assert resolve_double(L(True, 0), None, None, None) == (True, 1)


def test_by_day_pdf_is_one_page_per_day(app):
    """Each weekday must fit on exactly one landscape page, even with many arms."""
    import io
    from pypdf import PdfReader
    from models import GenTimetableResult, GenTimetableRule, GenSubject, Branch
    tag = next(_SEQ)
    batch = f'pdfpage{tag}'
    with app.app_context():
        bid = Branch.get_default().id
        subj = GenSubject(name=f'Bio{tag}', short_name='BIO', school_level='sss',
                          branch_id=bid, is_active=True)
        db.session.add(subj)
        for rt, val in [('periods_per_day', '8'), ('break_after_period', '5')]:
            db.session.add(GenTimetableRule(rule_type=rt, value=val, school_level='sss',
                                            is_active=True, branch_id=bid))
        db.session.flush()
        arms = ([('SSS1', a) for a in 'DILR'] + [('SSS2', a) for a in 'DILR']
                + [('SSS3', a) for a in 'ILR'])            # 11 class-arms
        for cn, arm in arms:
            for d in range(5):
                for p in range(1, 9):
                    db.session.add(GenTimetableResult(
                        branch_id=bid, batch_id=batch, school_level='sss',
                        class_name=cn, arm_name=arm, day_of_week=d, period_number=p,
                        subject_id=subj.id))
        db.session.commit()

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c.get('/generator/level/sss')
    r = c.get(f'/generator/results/{batch}/export_by_day_pdf')
    assert r.status_code == 200
    pages = len(PdfReader(io.BytesIO(r.get_data())).pages)
    assert pages == 5, f'expected 5 pages (one per weekday), got {pages}'


def test_teacher_timetable_image_has_break_and_renders(app):
    """Teacher timetable image renders and includes the break column in its width."""
    import io
    from PIL import Image
    from models import (GenTimetableResult, GenTimetableRule, GenSubject,
                        GenTeacher, Branch)
    tag = next(_SEQ)
    batch = f'ttimg{tag}'
    with app.app_context():
        bid = Branch.get_default().id
        t = GenTeacher(name=f'T{tag}', school_level='sss', branch_id=bid,
                       is_active=True, max_periods_per_day=6)
        subj = GenSubject(name=f'Mth{tag}', short_name='MTH', school_level='sss',
                          branch_id=bid, is_active=True)
        db.session.add_all([t, subj])
        for rt, val in [('periods_per_day', '8'), ('break_after_period', '5')]:
            db.session.add(GenTimetableRule(rule_type=rt, value=val, school_level='sss',
                                            is_active=True, branch_id=bid))
        db.session.flush()
        for d in range(5):
            for p in range(1, 9):
                db.session.add(GenTimetableResult(
                    branch_id=bid, batch_id=batch, school_level='sss',
                    class_name='SSS1', arm_name='D', day_of_week=d, period_number=p,
                    subject_id=subj.id, teacher_id=t.id))
        db.session.commit()
        tid = t.id

    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    c.get('/generator/level/sss')
    r = c.get(f'/generator/results/{batch}/teacher/{tid}/image')
    assert r.status_code == 200
    w = Image.open(io.BytesIO(r.get_data())).size[0]
    # Day col + 8 periods*110 + break(62) + 2*margin(50), all *4 scale.
    assert w == (100 + 8 * 110 + 62 + 2 * 50) * 4     # break column is in the width
