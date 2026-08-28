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
