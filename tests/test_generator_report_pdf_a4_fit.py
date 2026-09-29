"""Generator report PDFs (teacher workload, unassigned slots, period count) all
build on _simple_table_pdf, which auto-fits its row height/font to land a
realistic table on ONE A4-landscape page instead of spilling its last row or
two onto an otherwise-empty second sheet."""
import fitz

from config import Config
from models import db, Branch, GenTeacher, GenTimetableResult, GenTimetableRule
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed_workload(app, n_teachers, periods_each=25):
    """n_teachers, each with periods_each GenTimetableResult rows spread
    across a 5-day/8-period week -- enough to exercise the teacher-workload
    report's real row count."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'PDFA4-{_SEQ[0]}'
        bid = Branch.get_default().id
        batch_id = f'zz{tag}'
        for i in range(n_teachers):
            t = GenTeacher(branch_id=bid, name=f'Zz {tag} Teacher {i:03d}', school_level='sss',
                           max_periods_per_day=6, max_periods_per_week=30)
            db.session.add(t); db.session.flush()
            for p in range(periods_each):
                db.session.add(GenTimetableResult(
                    branch_id=bid, batch_id=batch_id, school_level='sss',
                    class_name=f'Zz{tag}Class', arm_name='Main',
                    day_of_week=p % 5, period_number=(p // 5) % 8 + 1,
                    teacher_id=t.id))
        db.session.commit()
        return batch_id


def _pdf_page_count(response_data):
    doc = fitz.open(stream=response_data, filetype='pdf')
    try:
        return doc.page_count, [(p.rect.width, p.rect.height) for p in doc]
    finally:
        doc.close()


def test_moderate_teacher_count_fits_one_page(app):
    """20 teachers is a realistic single-branch school -- must land on one
    page, not spill its last row onto an almost-empty second sheet."""
    batch_id = _seed_workload(app, 20)
    c = _admin(app)
    r = c.get(f'/generator/reports/teacher-workload/{batch_id}/pdf')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    n_pages, sizes = _pdf_page_count(r.data)
    assert n_pages == 1
    # A4 landscape in points: 841.89 x 595.28 (72pt/inch on 297mm x 210mm).
    w, h = sizes[0]
    assert abs(w - 841.89) < 1 and abs(h - 595.28) < 1


def test_small_teacher_count_fits_one_page(app):
    batch_id = _seed_workload(app, 5)
    c = _admin(app)
    r = c.get(f'/generator/reports/teacher-workload/{batch_id}/pdf')
    n_pages, _ = _pdf_page_count(r.data)
    assert n_pages == 1


def test_very_large_teacher_count_paginates_instead_of_erroring(app):
    """Past what even the smallest legible font/padding tier can fit on one
    page, it must paginate cleanly (not crash, not shrink to something
    illegible) -- every teacher still appears somewhere across the pages."""
    n = 60
    batch_id = _seed_workload(app, n)
    c = _admin(app)
    r = c.get(f'/generator/reports/teacher-workload/{batch_id}/pdf')
    assert r.status_code == 200
    n_pages, _ = _pdf_page_count(r.data)
    assert n_pages >= 2
    doc = fitz.open(stream=r.data, filetype='pdf')
    try:
        full_text = ''.join(p.get_text() for p in doc)
    finally:
        doc.close()
    assert full_text.count('Teacher ') >= n   # every seeded teacher's row made it in somewhere


def test_unassigned_report_pdf_still_renders(app):
    """Same shared _simple_table_pdf, different report -- basic smoke check
    that the auto-fit change didn't break this caller too."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'PDFA4U-{_SEQ[0]}'
        bid = Branch.get_default().id
        batch_id = f'zz{tag}'
        db.session.add(GenTimetableRule(rule_type='periods_per_day', value='8',
                                        school_level='sss', is_active=True, branch_id=bid))
        # A couple of results so the batch/branch resolve, but plenty of
        # empty slots remain (that's the report's whole subject).
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=batch_id, school_level='sss',
            class_name=f'Zz{tag}Class', arm_name='Main', day_of_week=0, period_number=1))
        db.session.commit()
    c = _admin(app)
    r = c.get(f'/generator/reports/unassigned/{batch_id}/pdf')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    n_pages, _ = _pdf_page_count(r.data)
    assert n_pages >= 1


def test_period_count_report_pdf_still_renders(app):
    """Same shared _simple_table_pdf, third caller."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'PDFA4P-{_SEQ[0]}'
        bid = Branch.get_default().id
        batch_id = f'zz{tag}'
        db.session.add(GenTimetableResult(
            branch_id=bid, batch_id=batch_id, school_level='sss',
            class_name=f'Zz{tag}Class', arm_name='Main', day_of_week=0, period_number=1))
        db.session.commit()
    c = _admin(app)
    r = c.get(f'/generator/reports/period-count/{batch_id}/pdf')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/pdf'
    n_pages, _ = _pdf_page_count(r.data)
    assert n_pages >= 1
