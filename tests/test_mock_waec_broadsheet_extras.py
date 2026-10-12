"""Mock WAEC broadsheet "what else should be on it" additions: AB (absent)
marking from the grid, the arm/position/subjects-sat/remark columns, and the
watermark/page-number/printed-on/exam-date/branch-name/paper-size toggles —
all independently selectable the same way the signature and Credits/Average
toggles already are."""
import re
import uuid
from datetime import date

import pytest

from config import Config
from models import db, Branch, Student, AcademicSession
from models.mock_waec import MockWAECExam, MockWAECResult, MockWAECAnalytics, waec_grade_from_score
from tests.conftest import login_token, auth_csrf, enroll_sss3


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _session(app):
    with app.app_context():
        s = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='2025/2026', is_active=True)
        db.session.add(s); db.session.commit()
        return s.id


def _exam(app, session_id, n):
    with app.app_context():
        ex = MockWAECExam(name=f'Mock {n}', exam_number=n, session_id=session_id,
                          exam_date=date(2026, 2, 15))
        db.session.add(ex); db.session.commit()
        return ex.id


def _student(app, adm, first, surname):
    with app.app_context():
        s = Student(student_id=adm, first_name=first, surname=surname, gender='Male')
        db.session.add(s); db.session.commit()
        return s.id


def _seed_results(app, exam_id, sid, scores):
    with app.app_context():
        for subj, sc in scores.items():
            db.session.add(MockWAECResult(student_id=sid, mock_exam_id=exam_id,
                                          subject=subj, score=sc, grade=waec_grade_from_score(sc)))
        db.session.commit()


def _slug(subj):
    return re.sub(r'[^a-z0-9]+', '-', subj.lower()).strip('-')


def test_grid_marks_and_clears_absence(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=90)
    sid = _student(app, 'AB' + uuid.uuid4().hex[:5].upper(), 'Ada', 'Absent')
    enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)

    # Check AB for Mathematics -> a result row is created with is_absent=True
    # and no score, even though the score box itself was left blank.
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'absent_{sid}_{_slug("Mathematics")}': 'on',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row is not None and row.is_absent is True
        assert row.score is None and row.grade is None

    # Entering a real score afterwards (AB unchecked) clears the absence.
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'score_{sid}_{_slug("Mathematics")}': '72',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row.is_absent is False and row.score == 72 and row.grade == 'B2'


def test_grid_absence_wins_over_a_stray_score_value(app):
    """If both the AB box and a leftover score value are posted for the same
    cell, absence must win -- a student can't be both absent and scored."""
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=91)
    sid = _student(app, 'AW' + uuid.uuid4().hex[:5].upper(), 'Win', 'Absence')
    enroll_sss3(app, sid)
    c = _admin(app)
    tok = auth_csrf(c)
    c.post(f'/mock-waec/exam/{exam_id}/grid', data={
        '_csrf_token': tok, 'action': 'save', 'col': ['Mathematics'],
        f'absent_{sid}_{_slug("Mathematics")}': 'on',
        f'score_{sid}_{_slug("Mathematics")}': '55',
    }, follow_redirects=True)
    with app.app_context():
        row = MockWAECResult.query.filter_by(mock_exam_id=exam_id, student_id=sid,
                                             subject='Mathematics').first()
        assert row.is_absent is True and row.score is None


def test_broadsheet_arm_position_subjects_sat_remark(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=92)
    top = _student(app, 'TP' + uuid.uuid4().hex[:5].upper(), 'Top', 'Scorer')
    low = _student(app, 'LW' + uuid.uuid4().hex[:5].upper(), 'Low', 'Scorer')
    enroll_sss3(app, top)
    enroll_sss3(app, low)
    _seed_results(app, exam_id, top, {'Mathematics': 90, 'English Language': 85,
                                      'Biology': 80, 'Chemistry': 75, 'Physics': 70})
    _seed_results(app, exam_id, low, {'Mathematics': 30, 'English Language': 35})

    with app.app_context():
        bs = MockWAECAnalytics.get_broadsheet(exam_id)
        by_id = {r['student'].id: r for r in bs['rows']}
        assert by_id[top]['position'] == 1
        assert by_id[low]['position'] == 2
        assert by_id[top]['subjects_sat'] == 5
        assert by_id[top]['remark'] == 'Qualifies'      # 5 credits incl. both core subjects
        assert by_id[low]['remark'] == 'Not Qualified'  # only 2 subjects, both failed
        # Arm is resolved (possibly '') without raising even with no SSS3/term
        # setup beyond what enroll_sss3 creates.
        assert 'arm' in by_id[top]

    c = _admin(app)
    # Everything new, combined in as few requests as possible (the export
    # route is rate-limited -- see the broadsheet rate-limit lesson in
    # test_mock_waec_broadsheet.py).
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?'
             'arm_col=1&position=1&subjects_sat=1&remark=1&exam_date=1&mode=separate')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
    r2 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?'
              'arm_col=0&position=0&subjects_sat=0&remark=0&'
              'watermark_name=0&watermark_logo=0&branch_name=0&'
              'page_numbers=0&printed_on=0&exam_date=0')
    assert r2.status_code == 200 and r2.get_data()[:5] == b'%PDF-'

    # Regression: the "No. offered"/"No. passed"/etc. summary-row labels were
    # placed at a fixed column index that landed in the Arm column (too
    # narrow, so the text ran over its neighbours) whenever arm_col was on,
    # instead of staying under Name like they do with arm_col off. Checked
    # against the two responses already fetched above (no extra requests).
    import fitz

    def _label_x0(resp):
        doc = fitz.open(stream=resp.get_data(), filetype='pdf')
        try:
            words = doc[0].get_text('words')
            hit = next(w for w in words if w[4] == 'offered')
            return hit[0]
        finally:
            doc.close()

    assert _label_x0(r) == pytest.approx(_label_x0(r2), abs=3)

    # Regression: in mode=separate with several tail columns active (credits,
    # average, position, subjects_sat, remark -- all on in `r` above), each
    # tail column reserved a 2-unit footprint in the width calculation but
    # the column-width list only allocated it 1, leaving part of the page
    # unused; reportlab centres an under-width table in its frame, padding
    # out BOTH margins. Checked against the `r` response already fetched
    # above (no extra request).
    doc = fitz.open(stream=r.get_data(), filetype='pdf')
    try:
        page = doc[0]
        xs = []
        for d in page.get_drawings():
            for item in d['items']:
                if item[0] == 'l':
                    xs += [item[1].x, item[2].x]
                elif item[0] == 're':
                    xs += [item[1].x0, item[1].x1]
        left_margin = min(xs)
        right_margin = page.rect.width - max(xs)
    finally:
        doc.close()
    assert left_margin == pytest.approx(22.68, abs=2)    # 8mm
    assert right_margin == pytest.approx(22.68, abs=2)


def test_broadsheet_preview_exposes_new_toggles(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=93)
    prev = _admin(app).get(f'/mock-waec/exam/{exam_id}/broadsheet/print').get_data(as_text=True)
    for label in ('Exam date', 'Class arm column', 'Position column',
                  'Subjects sat column', 'Remark column',
                  'Branch name (header + watermark)',
                  'Watermark — school name', 'Watermark — school logo',
                  'Page numbers', 'Printed-on footer',
                  'A1 — large format', 'A0 — largest format'):
        assert label in prev
    blank_prev = _admin(app).get(f'/mock-waec/exam/{exam_id}/broadsheet/blank').get_data(as_text=True)
    assert 'Class arm column' in blank_prev and 'Watermark — school name' in blank_prev
    assert 'Branch name (header + watermark)' in blank_prev
    # Position/Subjects-sat/Remark are filled-in-sheet-only (no scores on a
    # blank recording sheet to rank or qualify on).
    assert 'Position column' not in blank_prev and 'Remark column' not in blank_prev


def test_blank_broadsheet_renders_with_arm_and_watermark_toggles(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=94)
    sid = _student(app, 'BK' + uuid.uuid4().hex[:5].upper(), 'Blank', 'Arm')
    enroll_sss3(app, sid)
    with app.app_context():
        db.session.get(Student, sid).waec_subjects = 'Mathematics,English Language'
        db.session.commit()
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?'
             'arm_col=1&watermark_name=1&watermark_logo=1&branch_name=1&page_numbers=1')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
    r2 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?'
              'arm_col=0&watermark_name=0&watermark_logo=0&branch_name=0')
    assert r2.status_code == 200 and r2.get_data()[:5] == b'%PDF-'


def test_broadsheet_branch_name_in_header_and_watermark(app):
    """A branch name should show up in the printed header (and the watermark
    text) when toggled on — one combined request, to stay within the
    'export' rate-limit budget shared across the whole test suite."""
    import fitz   # PyMuPDF — already used by tests/test_blank_sheet_name_order.py
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=96)
    sid = _student(app, 'BR' + uuid.uuid4().hex[:5].upper(), 'Bran', 'Chy')
    enroll_sss3(app, sid)
    _seed_results(app, exam_id, sid, {'Mathematics': 60})
    tag = 'ZzJemila' + uuid.uuid4().hex[:5].upper()
    with app.app_context():
        branch = Branch(name=tag, code=tag[:8])
        db.session.add(branch); db.session.commit()
        exam = db.session.get(MockWAECExam, exam_id)
        exam.branch_id = branch.id
        db.session.commit()

    c = _admin(app)
    r_on = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?branch_name=1')
    assert r_on.status_code == 200
    doc = fitz.open(stream=r_on.get_data(), filetype='pdf')
    try:
        text_on = doc[0].get_text()
    finally:
        doc.close()
    assert tag.upper() in text_on


def test_broadsheet_footer_sits_in_margins_not_overlapping_table(app):
    """Regression: "Generated on ..." and "Page X of Y" used to run
    horizontally across the top or bottom of the sheet -- on any page where
    the roster overflows onto a continuation page (no school header there,
    so the table starts right at the top margin) that collided with the
    table's own top edge. They now run vertically in the left/right margins
    instead, a region the table (which fills exactly the space between the
    margins) never reaches on any page."""
    import fitz
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=97)
    sid = _student(app, 'FP' + uuid.uuid4().hex[:5].upper(), 'Foot', 'Pos')
    enroll_sss3(app, sid)
    _seed_results(app, exam_id, sid, {'Mathematics': 60})
    c = _admin(app)

    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?printed_on=1&page_numbers=1&'
             'summary=0&grades=0&sig_principal=0&sig_hod_sci=0&sig_hod_arts=0')
    assert r.status_code == 200
    doc = fitz.open(stream=r.get_data(), filetype='pdf')
    try:
        page = doc[0]
        pw = page.rect.width
        words = page.get_text('words')
        generated = next(w for w in words if w[4] == 'Generated')
        page_word = next(w for w in words if w[4] == 'Page')

        # Also checked against this same response (no extra request): Credits
        # and Average should render narrower than the other columns (Arm,
        # Mathematics, Position, Subjects Sat, Remark are all full-weight and
        # default on alongside Credits/Average here).
        verts = []
        for d in page.get_drawings():
            for item in d['items']:
                if item[0] == 'l':
                    x0, y0 = item[1]
                    x1, y1 = item[2]
                    if abs(x0 - x1) < 0.01 and abs(y0 - y1) > 5:
                        verts.append((round(x0, 1), round(min(y0, y1), 1), round(max(y0, y1), 1)))
        longest = max(v[2] - v[1] for v in verts)
        cols = sorted(set(v[0] for v in verts if v[2] - v[1] > longest - 5))
        col_widths = [cols[i + 1] - cols[i] for i in range(len(cols) - 1)]
        # S/N, Name, Arm, Mathematics, Credits, Average, Position, Subjects Sat, Remark
        full_width = col_widths[3]              # Mathematics -- a full-weight column
        credits_w, average_w = col_widths[4], col_widths[5]
    finally:
        doc.close()

    margin = 22.68   # 8mm in points -- where the table itself begins/ends
    assert generated[2] < margin              # "Generated" stays left of the table
    assert page_word[0] > pw - margin         # "Page" stays right of the table

    assert credits_w < full_width * 0.8
    assert average_w < full_width * 0.8
    assert col_widths[6] == pytest.approx(full_width, abs=1)   # Position stays full-weight
    assert col_widths[8] == pytest.approx(full_width, abs=1)   # Remark stays full-weight


def test_broadsheet_and_blank_accept_a1_and_a0_paper_sizes(app):
    import fitz
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=98)
    sid = _student(app, 'PS' + uuid.uuid4().hex[:5].upper(), 'Paper', 'Size')
    enroll_sss3(app, sid)
    _seed_results(app, exam_id, sid, {'Mathematics': 60})
    c = _admin(app)

    r_a1 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf?size=A1')
    assert r_a1.status_code == 200 and r_a1.get_data()[:5] == b'%PDF-'
    doc = fitz.open(stream=r_a1.get_data(), filetype='pdf')
    try:
        assert doc[0].rect.width == pytest.approx(2383.94, abs=1)   # landscape A1
    finally:
        doc.close()

    r_a0 = c.get(f'/mock-waec/exam/{exam_id}/broadsheet/blank.pdf?size=A0')
    assert r_a0.status_code == 200 and r_a0.get_data()[:5] == b'%PDF-'
    doc = fitz.open(stream=r_a0.get_data(), filetype='pdf')
    try:
        assert doc[0].rect.width == pytest.approx(3370.39, abs=1)   # landscape A0
    finally:
        doc.close()


def test_faint_logo_image_background_is_transparent_not_a_box():
    """Regression: reportlab's ``mask='auto'`` only honours an image's own
    alpha channel. The first cut of the logo watermark just lightened a flat
    (no-alpha) image and passed ``mask='auto'`` -- with nothing for "auto" to
    mask on, the whole rectangle (background included) drew fully opaque, as
    a hard grey box instead of a faint watermark. The derived image's
    background corner must stay far more transparent than its ink."""
    import os
    import tempfile
    from PIL import Image, ImageDraw
    from utils.mock_waec_pdf import _faint_logo_image

    im = Image.new('RGB', (200, 200), 'white')
    ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill='black')
    fd, path = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        im.save(path)
        wm = _faint_logo_image(path)
        assert wm.mode == 'RGBA'
        corner_alpha = wm.getpixel((2, 2))[3]     # background, outside the ellipse
        center_alpha = wm.getpixel((100, 100))[3]  # ink, inside the ellipse
        assert corner_alpha < 5                    # background stays (near-)invisible
        assert center_alpha > corner_alpha * 5      # ink is visibly faint, not an opaque box
    finally:
        os.remove(path)


def test_big_paper_sizes_get_taller_rows_than_a4():
    """A3 and bigger have enough spare vertical room that a request to "make
    the rows a tiny bit taller" is better served by slightly more generous
    padding/row-height than by precisely computing how many fewer students
    fit per page -- reportlab's own automatic Table pagination then fits
    fewer rows per page as a natural side effect. Pure unit check of the
    helpers (no PDF render / HTTP call needed, and they're otherwise only
    exercised indirectly): A3 and up must be taller than A4, and every big
    size must agree with every other (not just A3 specifically)."""
    from reportlab.lib.units import mm
    from utils.mock_waec_pdf import _BIG_SIZES, _row_pad, _row_h

    assert _BIG_SIZES == {'A3', 'A2', 'A1', 'A0'}

    a4_pad = _row_pad('A4')
    a4_h = _row_h('A4', 8.5)
    assert a4_h == pytest.approx(8.5 * mm)
    for big in _BIG_SIZES:
        assert _row_pad(big) > a4_pad
        assert _row_h(big, 8.5) > a4_h
        assert _row_h(big, 8.5) == pytest.approx(9.4 * mm)
        # Every big size behaves the same as every other -- this isn't an
        # A3-only special case.
        assert _row_pad(big) == _row_pad('A3')

    # Falls back to the A4 (not-big) behaviour for an unrecognised/blank size.
    assert _row_pad(None) == a4_pad
    assert _row_pad('') == a4_pad


def test_broadsheet_shows_ab_for_absent_subject(app):
    ssid = _session(app)
    exam_id = _exam(app, ssid, n=95)
    sid = _student(app, 'MA' + uuid.uuid4().hex[:5].upper(), 'Marked', 'Absent')
    enroll_sss3(app, sid)
    with app.app_context():
        r = MockWAECResult(student_id=sid, mock_exam_id=exam_id, subject='Mathematics',
                           score=None, grade=None, is_absent=True)
        db.session.add(r); db.session.commit()
        bs = MockWAECAnalytics.get_broadsheet(exam_id)
        row = next(r for r in bs['rows'] if r['student'].id == sid)
        assert row['credits'] == 0 and row['average_score'] is None
    c = _admin(app)
    r = c.get(f'/mock-waec/exam/{exam_id}/broadsheet.pdf')
    assert r.status_code == 200 and r.get_data()[:5] == b'%PDF-'
