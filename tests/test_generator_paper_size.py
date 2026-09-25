"""A3/A4 paper-size choice for the timetable generator's Excel/PDF exports,
plus A3's "packed" (2 days per page/sheet) layout option for the by-day
exports."""
from io import BytesIO
from config import Config
from models import db, Branch, GenTimetableResult, GenTimetableRule
from tests.conftest import login_token

_SEQ = [0]


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _seed(app):
    """A small batch: 3 class-arms, 5 weekdays, one subject-less-marked slot
    each — enough rows to exercise every export path without co-scheduling
    complexity, which is irrelevant to paper-size handling."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'PS{_SEQ[0]}'
        bid = Branch.get_default().id
        batch_id = f'zzpaper-{tag}'
        db.session.add(GenTimetableRule(rule_type='periods_per_day', value='8',
                                        school_level='sss', is_active=True, branch_id=bid))
        db.session.add(GenTimetableRule(rule_type='break_after_period', value='4',
                                        school_level='sss', is_active=True, branch_id=bid))
        for cn in ('A', 'B', 'C'):
            for d in range(5):
                for p in (1, 2):
                    db.session.add(GenTimetableResult(
                        branch_id=bid, batch_id=batch_id, school_level='sss',
                        class_name=f'Zz{tag}{cn}', arm_name='Main',
                        day_of_week=d, period_number=p))
        db.session.commit()
        return batch_id


def test_export_by_class_default_is_a4(app):
    import openpyxl
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export')
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.data))
    ws = wb[wb.sheetnames[0]]
    assert str(ws.page_setup.paperSize) == str(ws.PAPERSIZE_A4)


def test_export_by_class_a3_sets_paper_size(app):
    import openpyxl
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export?paper=a3')
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.data))
    ws = wb[wb.sheetnames[0]]
    assert str(ws.page_setup.paperSize) == str(ws.PAPERSIZE_A3)


def test_export_by_day_a3_single_is_one_sheet_per_day(app):
    import openpyxl
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day?paper=a3&layout=single')
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.data))
    assert len(wb.sheetnames) == 5
    assert str(wb[wb.sheetnames[0]].page_setup.paperSize) == str(wb[wb.sheetnames[0]].PAPERSIZE_A3)


def test_export_by_day_a3_packed_is_two_days_per_sheet(app):
    import openpyxl
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day?paper=a3&layout=packed')
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.data))
    # 5 days packed 2-per-sheet -> 3 sheets (2, 2, 1), each on A3.
    assert len(wb.sheetnames) == 3
    for name in wb.sheetnames:
        assert str(wb[name].page_setup.paperSize) == str(wb[name].PAPERSIZE_A3)
    # Both days on the first (fully-packed) sheet actually contain a day
    # header — not just the first, blank-padded to look packed.
    first_sheet = wb[wb.sheetnames[0]]
    all_text = ' '.join(str(cell.value) for row in first_sheet.iter_rows() for cell in row if cell.value)
    assert 'MONDAY' in all_text and 'TUESDAY' in all_text


def test_export_by_day_a4_ignores_packed_layout(app):
    """A4 never packs — there's no room to keep two days legible — so
    ?layout=packed on A4 is silently ignored, still one sheet per day."""
    import openpyxl
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day?paper=a4&layout=packed')
    assert r.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(r.data))
    assert len(wb.sheetnames) == 5
    assert str(wb[wb.sheetnames[0]].page_setup.paperSize) == str(wb[wb.sheetnames[0]].PAPERSIZE_A4)


def test_export_by_day_pdf_a3_packed_generates_fewer_pages(app):
    """Can't easily extract reportlab PDF text in this env (no pypdf), but we
    can count pages via PyMuPDF and confirm packed halves the page count."""
    import fitz
    batch_id = _seed(app)
    c = _admin(app)

    r_single = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=single')
    assert r_single.status_code == 200
    doc_single = fitz.open(stream=r_single.data, filetype='pdf')
    pages_single = doc_single.page_count
    doc_single.close()

    r_packed = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=packed')
    assert r_packed.status_code == 200
    doc_packed = fitz.open(stream=r_packed.data, filetype='pdf')
    pages_packed = doc_packed.page_count
    doc_packed.close()

    assert pages_single == 5    # one page per weekday
    assert pages_packed == 3    # 2+2+1 days per page


def test_export_by_day_pdf_a4_ignores_packed_layout(app):
    import fitz
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a4&layout=packed')
    assert r.status_code == 200
    doc = fitz.open(stream=r.data, filetype='pdf')
    assert doc.page_count == 5
    # A4 page size (landscape), not A3's.
    rect = doc[0].rect
    doc.close()
    from reportlab.lib.pagesizes import A4, landscape
    a4_w, a4_h = landscape(A4)
    assert abs(rect.width - a4_w) < 2 and abs(rect.height - a4_h) < 2


def test_export_by_day_pdf_a3_page_is_bigger_than_a4(app):
    import fitz
    from reportlab.lib.pagesizes import A3, A4, landscape
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=single')
    doc = fitz.open(stream=r.data, filetype='pdf')
    rect = doc[0].rect
    doc.close()
    a3_w, a3_h = landscape(A3)
    assert abs(rect.width - a3_w) < 2 and abs(rect.height - a3_h) < 2
    a4_w, _ = landscape(A4)
    assert a3_w > a4_w


def _words(page):
    return page.get_text('words')


def _word(words, text):
    """First word box (x0, y0, x1, y1) exactly matching `text`."""
    for w in words:
        if w[4] == text:
            return w[:4]
    raise AssertionError(f'word {text!r} not found on page')


def _first_column_border_x(page):
    """X-position of the grid line separating the class-code column from the
    first period column — the ground truth for where that column actually
    ends, as opposed to inferring it from a neighboring word's position."""
    xs = set()
    for d in page.get_drawings():
        for item in d.get('items', []):
            if item[0] == 'l':
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) < 0.01:
                    xs.add(round(p1.x, 1))
    xs = sorted(xs)
    return xs[1]   # xs[0] is the page's own left border


def _class_code(batch_id):
    """The first class-arm's printed short code for a batch from `_seed`
    (class 'A', arm 'Main' -> tag + 'A' + 'M'), matching get_short_code()."""
    tag = batch_id.split('-', 1)[1]
    return f'Zz{tag}AM'


def test_export_by_day_pdf_a3_single_class_column_text_stays_in_its_column(app):
    """Regression: on A3 the font grows with the page, but the first
    (Class-code) column used to stay a fixed physical width — so a class
    code (e.g. "ZzPS1AM") spilled past the column's own border, even off
    the left edge of the page in the worst case, instead of the column
    growing to match the bigger font. Column widths must scale with page
    width too, not just row heights with page height."""
    import fitz
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=single')
    doc = fitz.open(stream=r.data, filetype='pdf')
    page = doc[0]
    words = _words(page)
    border_x = _first_column_border_x(page)
    doc.close()
    class_code_box = _word(words, _class_code(batch_id))
    assert class_code_box[0] >= 0                 # not off the left edge of the page
    assert class_code_box[2] <= border_x + 1       # not past its column's own border


def test_export_by_day_pdf_a3_packed_class_column_text_stays_in_its_column(app):
    import fitz
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=packed')
    doc = fitz.open(stream=r.data, filetype='pdf')
    page = doc[0]
    words = _words(page)
    border_x = _first_column_border_x(page)
    doc.close()
    class_code_box = _word(words, _class_code(batch_id))
    assert class_code_box[0] >= 0
    assert class_code_box[2] <= border_x + 1


def test_export_by_day_pdf_a3_single_day_header_does_not_overlap_period_row(app):
    """Regression: the day-name row's font/row-height ratio was tuned at A4
    scale using reportlab's default (fixed-point) leading and padding; once
    scaled up ~1.45x for A3 the day name (e.g. "MONDAY") visibly bled down
    into the period-header row below it. Compared against "P1" rather than
    "Class": "P1" is the top line of a stacked 3-line cell (P1/start/end)
    that VALIGN MIDDLE positions higher in the row than the single-line
    "Class" label next to it, so it's the one that actually collides first."""
    import fitz
    batch_id = _seed(app)
    c = _admin(app)
    r = c.get(f'/generator/results/{batch_id}/export_by_day_pdf?paper=a3&layout=single')
    doc = fitz.open(stream=r.data, filetype='pdf')
    words = _words(doc[0])
    doc.close()
    day_box = _word(words, 'MONDAY')
    p1_box = _word(words, 'P1')
    assert day_box[3] <= p1_box[1]   # MONDAY's bottom edge is above P1's top edge
