"""The separate ReportLab-based "by day" PDF export (export_results_by_day_pdf)
had the same repeated-period-header-row bug as the XLSX export covered in
test_generator_a3_packed_header.py: every day in a packed A3 page (e.g. both
Monday and Tuesday stacked on one page) rendered its own full
"Class | P1...P9 | BREAK | ..." row, even though the second day's periods are
identical to the first's. Now only the first day in each page-group shows it.
"""
from io import BytesIO

import fitz  # PyMuPDF
import pytest
from config import Config
from models import (
    db, Branch, GenSubject, GenTeacher, GenTeacherAssignment, GenClassConfig,
    GenClassSubjectConfig, GenTimetableRule, GenTimetableResult, SchoolSettings,
)
from tests.conftest import login_token


@pytest.fixture(autouse=True)
def _restore_time_format(app):
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
        b = Branch(name=f'ZzA3PdfHdrBranch{tag}', code=None)
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

        cc = GenClassConfig(branch_id=bid, class_name=f'ZzA3P{tag}', school_level='sss',
                            num_arms=1, arm_names=f'ZzArm{tag}', has_streams=False)
        db.session.add(cc); db.session.flush()

        subj = GenSubject(branch_id=bid, name=f'ZzSubjP{tag}', short_name=None, school_level='sss')
        db.session.add(subj); db.session.flush()

        t = GenTeacher(branch_id=bid, name=f'Zz Teacher P{tag}', school_level='sss',
                       max_periods_per_day=periods_per_day, max_periods_per_week=periods_per_day * 5)
        db.session.add(t); db.session.flush()
        db.session.add(GenTeacherAssignment(branch_id=bid, teacher_id=t.id, subject_id=subj.id,
                                            class_config_id=cc.id, arm_name=f'ZzArm{tag}'))
        db.session.add(GenClassSubjectConfig(
            class_config_id=cc.id, subject_id=subj.id, is_enabled=True, periods_per_week=5))

        batch_id = f'zza3pdfh-{tag}'
        for d in range(5):
            db.session.add(GenTimetableResult(
                branch_id=bid, batch_id=batch_id, school_level='sss',
                class_name=f'ZzA3P{tag}', arm_name=f'ZzArm{tag}',
                day_of_week=d, period_number=1, subject_id=subj.id, teacher_id=t.id))
        db.session.commit()
        return batch_id, bid


def _pages_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    return [page.get_text() for page in doc]


def test_packed_pdf_second_day_on_page_has_no_repeated_header(app):
    batch_id, bid = _seed(app, 'PK', periods_per_day=9, break_after=5)
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=packed')
    assert r.status_code == 200
    pages = _pages_text(r.data)
    # Monday + Tuesday packed onto page 1.
    page1 = pages[0]
    assert page1.count('Class') == 1
    assert page1.count('BREAK') == 1
    assert 'MONDAY' in page1 and 'TUESDAY' in page1


def test_packed_pdf_wed_thu_pair_also_has_single_header(app):
    batch_id, bid = _seed(app, 'PK2', periods_per_day=9, break_after=5)
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=packed')
    assert r.status_code == 200
    pages = _pages_text(r.data)
    assert len(pages) == 3  # Mon&Tue, Wed&Thu, Fri
    page2 = pages[1]
    assert page2.count('Class') == 1
    assert page2.count('BREAK') == 1
    assert 'WEDNESDAY' in page2 and 'THURSDAY' in page2


def test_single_day_per_page_pdf_shows_header_once(app):
    """layout=single (the default / A4): every day is its own separate
    physical page, so repeating the P#/times header on each one is just the
    same times five times over -- it's shown ONCE, on the very first page,
    and omitted on every page after that (the freed space goes to bigger
    data rows instead of staying blank)."""
    batch_id, bid = _seed(app, 'SGL', periods_per_day=9, break_after=5)
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf')
    assert r.status_code == 200
    pages = _pages_text(r.data)
    assert len(pages) == 5
    first, rest = pages[0], pages[1:]
    assert first.count('Class') == 1
    assert first.count('BREAK') == 1
    for page in rest:
        assert 'Class' not in page
        assert 'BREAK' not in page


def test_packed_pdf_last_lone_day_still_shows_its_own_header(app):
    """Friday is alone on its page (odd day count), so it must still show
    its own header -- it's the FIRST (and only) day in that page-group."""
    batch_id, bid = _seed(app, 'PK3', periods_per_day=9, break_after=5)
    c = _scoped_to_branch(_admin(app), bid)

    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=packed')
    assert r.status_code == 200
    pages = _pages_text(r.data)
    friday_page = pages[-1]
    assert 'FRIDAY' in friday_page
    assert friday_page.count('Class') == 1
    assert friday_page.count('BREAK') == 1
