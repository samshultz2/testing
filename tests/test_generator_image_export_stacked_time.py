"""The by-day PNG image export cramped each period's clock range onto one
line ("8:00 AM-8:40 AM"), which overlapped the next column's text under 12h
format. Now it's 3 stacked lines (period / start / end)."""
from io import BytesIO

import pytest
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenClassSubjectConfig, GenTimetableRule, GenTimetableResult, SchoolSettings,
)
from tests.conftest import login_token


@pytest.fixture(autouse=True)
def _restore_time_format(app):
    """time_format is a site-wide SchoolSettings row (not branch-scoped), so
    every test here that sets it must put it back for other test files."""
    yield
    with app.app_context():
        SchoolSettings.set('time_format', '24h', 'string', 'test')
        from utils.timeutil import clear_time_format_cache
        clear_time_format_cache()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return c


def _scoped_to_branch(c, branch_id):
    with c.session_transaction() as s:
        s['view_branch_id'] = branch_id
    return c


def _seed(app, tag, periods_per_day=9, break_after=5):
    with app.app_context():
        b = Branch(name=f'ZzImgStackBranch{tag}', code=None)
        db.session.add(b); db.session.flush()
        bid = b.id

        db.session.add_all([
            GenTimetableRule(branch_id=bid, rule_type='periods_per_day', value=str(periods_per_day),
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_after_period', value=str(break_after),
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='day_start', value='8:00',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='period_minutes', value='40',
                             school_level='sss', is_active=True),
            GenTimetableRule(branch_id=bid, rule_type='break_minutes', value='30',
                             school_level='sss', is_active=True),
        ])
        SchoolSettings.set('time_format', '12h', 'string', 'test')
        from utils.timeutil import clear_time_format_cache
        clear_time_format_cache()

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzIS{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}', has_streams=False)
        db.session.add(cc); db.session.flush()

        subj = GenSubject(branch_id=bid, name=f'ZzSubj{tag}', school_level='sss')
        db.session.add(subj); db.session.flush()

        t = GenTeacher(branch_id=bid, name=f'Zz Teacher {tag}', school_level='sss',
                       max_periods_per_day=periods_per_day, max_periods_per_week=periods_per_day * 5)
        db.session.add(t); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzArm{tag}'))
        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=subj.id, is_enabled=True, periods_per_week=5))

        batch_id = f'zzisimg-{tag}'
        for d in range(5):
            db.session.add(GenTimetableResult(
                branch_id=bid, batch_id=batch_id, school_level='sss',
                class_name=f'ZzIS{tag}', arm_name=f'ZzArm{tag}',
                day_of_week=d, period_number=1, subject_id=subj.id, teacher_id=t.id))
        db.session.commit()
        return batch_id, bid


def test_image_export_header_height_reflects_three_stacked_lines(app):
    """Total image height is a direct function of header_height (one term
    per day block) -- pins that constant at 70*scale (3 lines) rather than
    the old 55*scale (2 lines), so a regression back to the cramped 2-line
    format would change this and fail loudly."""
    from PIL import Image
    batch_id, bid = _seed(app, 'HGT', periods_per_day=9, break_after=5)
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_image_hd')
    assert r.status_code == 200
    assert r.mimetype == 'image/png'
    img = Image.open(BytesIO(r.data))

    scale = 4
    cell_height = 35 * scale
    header_height = 70 * scale
    day_header_height = 55 * scale
    margin = 50 * scale
    day_spacing = 25 * scale
    title_height = 120 * scale
    num_class_arms = 1
    num_days = 5

    expected_height = title_height + (num_days * (day_header_height + header_height
                      + (num_class_arms * cell_height) + day_spacing)) + (margin * 2)
    assert img.height == expected_height


def test_image_export_break_column_widened_to_fit_break_time(app):
    """break_col_width went from 35*scale to 48*scale so the stacked break
    start/end time ("11:20 AM" etc.) actually fits instead of being clipped."""
    from PIL import Image
    batch_id, bid = _seed(app, 'WID', periods_per_day=9, break_after=5)
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_image_hd')
    assert r.status_code == 200
    img = Image.open(BytesIO(r.data))

    scale = 4
    cell_width = 85 * scale
    class_col_width = 55 * scale
    break_col_width = 48 * scale
    margin = 50 * scale
    periods_per_day = 9
    table_width = class_col_width + (periods_per_day * cell_width) + break_col_width
    expected_width = table_width + (margin * 2)
    assert img.width == expected_width


def test_image_export_renders_without_error_in_24h_format_too(app):
    """24h format never had the overlap bug (no AM/PM suffix), but the
    3-line layout change must not break it either."""
    from PIL import Image
    batch_id, bid = _seed(app, 'TF24', periods_per_day=9, break_after=5)
    with app.app_context():
        SchoolSettings.set('time_format', '24h', 'string', 'test')
        from utils.timeutil import clear_time_format_cache
        clear_time_format_cache()
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_image_hd')
    assert r.status_code == 200
    img = Image.open(BytesIO(r.data))
    assert img.width > 0 and img.height > 0
