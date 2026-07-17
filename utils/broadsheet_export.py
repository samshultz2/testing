"""Broadsheet & score-sheet exports in multiple formats.

Two products:

1. A **filled broadsheet** (subject totals per student, ranked) rendered as PDF,
   Word (.docx) or a high-resolution PNG — alongside the existing Excel export.
2. A **blank score-entry sheet** (A4, one subject) with the school's own
   assessment columns (any number of CAs, optional Holiday Assignment, optional
   Practical/Mid-term, CBT, PBT/Theory, Exam Total, General Total) and the class
   roster pre-printed in separate First / Middle / Surname columns — ready to
   photocopy and fill by hand.

Columns are derived from the tenant's active ``AssessmentType`` rows, so a school
that runs 2 CAs and no Holiday Assignment gets exactly those columns.
"""
import io

from models import (db, Term, ClassArmAssignment, ClassSubject, Subject, Student,
                    StudentEnrollment, StudentScore, AssessmentType, SchoolSettings, GradeScale)
from utils.assessments import is_midterm, is_theory, is_cbt


# --------------------------------------------------------------------------- #
# Assessment-column layout (school-configurable)
# --------------------------------------------------------------------------- #

def _is_ca(at):
    code = (at.short_name or at.name or '').upper().replace(' ', '')
    return code.startswith('CA') or 'CONTINUOUS' in code


def _is_ha(at):
    code = (at.short_name or '').upper()
    name = (at.name or '').upper()
    return code in ('HA', 'HW') or 'HOLIDAY' in name or 'ASSIGNMENT' in name


def score_columns():
    """Ordered blank-sheet score columns from the active assessment types.

    Returns a list of dicts ``{'label', 'max', 'kind'}`` where ``kind`` is one of
    ca / ha / peme / cbt / theory / other, deduplicated by short name and ordered
    as CAs → HA → Practical/Mid-term → CBT → Theory → anything else."""
    types = AssessmentType.query.filter_by(is_active=True).order_by(
        AssessmentType.order, AssessmentType.id).all()
    seen, uniq = set(), []
    for at in types:
        key = (at.short_name or at.name or '').upper()
        if key and key not in seen:
            seen.add(key)
            uniq.append(at)

    def label_for(at, kind):
        if kind == 'cbt':
            return 'CBT'
        if kind == 'theory':
            return 'PBT/THEORY'
        if kind == 'peme':
            return 'P.E/M.E'
        if kind == 'ha':
            return at.short_name or 'HA'
        return at.short_name or at.name

    buckets = {'ca': [], 'ha': [], 'peme': [], 'cbt': [], 'theory': [], 'other': []}
    for at in uniq:
        if _is_ca(at):
            kind = 'ca'
        elif _is_ha(at):
            kind = 'ha'
        elif is_midterm(at):
            kind = 'peme'
        elif is_cbt(at):
            kind = 'cbt'
        elif is_theory(at):
            kind = 'theory'
        else:
            kind = 'other'
        buckets[kind].append({'label': label_for(at, kind), 'max': at.max_score, 'kind': kind})
    ordered = (buckets['ca'] + buckets['ha'] + buckets['peme'] + buckets['other']
               + buckets['cbt'] + buckets['theory'])
    return ordered


# --------------------------------------------------------------------------- #
# Shared filled-broadsheet model
# --------------------------------------------------------------------------- #

def build_model(term_id, assignment_id):
    """Shared broadsheet data: ranked students × subject totals. Returns a dict
    with ``term``, ``assignment``, ``subjects`` and ``rows`` (already ranked)."""
    term = db.session.get(Term, term_id)
    asg = db.session.get(ClassArmAssignment, assignment_id)
    if not (term and asg):
        return None
    subjects = ClassSubject.query.filter_by(
        term_id=term_id, class_id=asg.class_id, is_active=True
    ).filter((ClassSubject.arm_id == None) | (ClassSubject.arm_id == asg.arm_id)  # noqa: E711
             ).join(Subject).order_by(Subject.name).all()
    enrollments = (StudentEnrollment.query
                   .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                   .join(Student).order_by(Student.surname, Student.first_name).all())
    pass_mark = SchoolSettings.get('pass_mark', 50)

    cs_ids = [cs.id for cs in subjects]
    sids = [e.student_id for e in enrollments]
    totals = {}                        # (student_id, cs_id) -> summed score
    if cs_ids and sids:
        for s in StudentScore.query.filter(
                StudentScore.student_id.in_(sids),
                StudentScore.class_subject_id.in_(cs_ids)).all():
            totals[(s.student_id, s.class_subject_id)] = totals.get(
                (s.student_id, s.class_subject_id), 0) + (s.score or 0)

    rows = []
    for e in enrollments:
        subj_totals = {cs.id: totals.get((e.student_id, cs.id), 0) for cs in subjects}
        grand = sum(subj_totals.values())
        avg = round(grand / len(subjects), 2) if subjects else 0
        passed = sum(1 for v in subj_totals.values() if v >= pass_mark)
        failed = sum(1 for v in subj_totals.values() if 0 < v < pass_mark)
        rows.append({'student': e.student, 'subjects': subj_totals, 'total': round(grand, 1),
                     'average': avg, 'passed': passed, 'failed': failed})
    rows.sort(key=lambda r: r['average'], reverse=True)
    for i, r in enumerate(rows, 1):
        r['position'] = i
    return {'term': term, 'assignment': asg, 'subjects': subjects, 'rows': rows,
            'pass_mark': pass_mark}


def _school_name():
    try:
        from utils.school import school_profile
        return school_profile().get('name') or 'School'
    except Exception:
        return 'School'


def _fname(assignment, term, ext):
    base = (assignment.display_name or 'broadsheet').replace(' ', '_')
    return f"broadsheet_{base}_{term.name.replace(' ', '_')}.{ext}"


# --------------------------------------------------------------------------- #
# Filled broadsheet — PDF (reportlab, landscape A4)
# --------------------------------------------------------------------------- #

def _theme():
    from reportlab.lib.colors import HexColor
    return HexColor('#0D6A4E'), HexColor('#C9A227'), HexColor('#F4F7F5'), HexColor('#14211C')


def broadsheet_pdf(term_id, assignment_id):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
    from utils.web_exports import pdf_escape

    m = build_model(term_id, assignment_id)
    if not m:
        return None
    primary, accent, light, ink = _theme()
    styles = getSampleStyleSheet()
    h = ParagraphStyle('h', parent=styles['Title'], fontSize=15, textColor=primary, spaceAfter=2)
    sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=9.5, textColor=colors.HexColor('#6B7A74'))
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=7.5, leading=9)

    subjects = m['subjects']
    head = ['Pos', 'Student'] + [(cs.subject.short_name or cs.subject.name[:6]) for cs in subjects] \
        + ['Total', 'Avg', 'Grade']
    data = [head]
    for r in m['rows']:
        row = [str(r['position']), Paragraph(pdf_escape(r['student'].full_name), cell)]
        for cs in subjects:
            v = r['subjects'].get(cs.id, 0)
            row.append(str(round(v, 1)) if v else '–')
        row += [str(r['total']), str(r['average']),
                GradeScale.get_grade(r['average']) if r['average'] else '–']
        data.append(row)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=10 * mm, bottomMargin=10 * mm,
                            leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f"Broadsheet — {m['assignment'].display_name}")
    avail = landscape(A4)[0] - 16 * mm
    name_w, pos_w, tail_w = 44 * mm, 9 * mm, 12 * mm
    subj_w = max(9 * mm, (avail - pos_w - name_w - 3 * tail_w) / max(len(subjects), 1))
    widths = [pos_w, name_w] + [subj_w] * len(subjects) + [tail_w, tail_w, tail_w]

    t = Table(data, colWidths=widths, repeatRows=1)
    ts = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D5DED9')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light]),
        ('FONTNAME', (-3, 1), (-1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])
    t.setStyle(ts)

    elems = [Paragraph(pdf_escape(_school_name()), h),
             Paragraph(f"Broadsheet · {pdf_escape(m['assignment'].display_name)} · "
                       f"{pdf_escape(m['term'].full_name)}", sub),
             Spacer(1, 6), t]
    doc.build(elems)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Filled broadsheet — Word (.docx)
# --------------------------------------------------------------------------- #

def broadsheet_docx(term_id, assignment_id):
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_ORIENT

    m = build_model(term_id, assignment_id)
    if not m:
        return None
    subjects = m['subjects']
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = sec.page_height, sec.page_width
    for attr in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'):
        setattr(sec, attr, Inches(0.4))

    title = doc.add_paragraph()
    run = title.add_run(_school_name()); run.bold = True; run.font.size = Pt(16)
    run.font.color.rgb = RGBColor(0x0D, 0x6A, 0x4E)
    meta = doc.add_paragraph(f"Broadsheet · {m['assignment'].display_name} · {m['term'].full_name}")
    meta.runs[0].font.size = Pt(10)

    head = ['Pos', 'Student'] + [(cs.subject.short_name or cs.subject.name[:6]) for cs in subjects] \
        + ['Total', 'Avg', 'Grade']
    table = doc.add_table(rows=1, cols=len(head))
    table.style = 'Light Grid Accent 1'
    for i, htext in enumerate(head):
        c = table.rows[0].cells[i]
        c.text = htext
        for p in c.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for rn in p.runs:
                rn.bold = True; rn.font.size = Pt(8)
    for r in m['rows']:
        cells = table.add_row().cells
        cells[0].text = str(r['position'])
        cells[1].text = r['student'].full_name
        idx = 2
        for cs in subjects:
            v = r['subjects'].get(cs.id, 0)
            cells[idx].text = str(round(v, 1)) if v else '–'; idx += 1
        cells[idx].text = str(r['total'])
        cells[idx + 1].text = str(r['average'])
        cells[idx + 2].text = GradeScale.get_grade(r['average']) if r['average'] else '–'
        for c in cells:
            for p in c.paragraphs:
                for rn in p.runs:
                    rn.font.size = Pt(8)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Filled broadsheet — high-resolution PNG (render the PDF at high DPI)
# --------------------------------------------------------------------------- #

def broadsheet_png(term_id, assignment_id, dpi=200):
    """Render the broadsheet PDF's first page to a high-resolution PNG."""
    pdf = broadsheet_pdf(term_id, assignment_id)
    if not pdf:
        return None
    import fitz
    doc = fitz.open(stream=pdf, filetype='pdf')
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
    return pix.tobytes('png')


# --------------------------------------------------------------------------- #
# Blank score-entry sheet (A4, one subject) — reportlab
# --------------------------------------------------------------------------- #

def blank_sheet_pdf(term_id, assignment_id, subject_name=''):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
    from utils.web_exports import pdf_escape

    term = db.session.get(Term, term_id)
    asg = db.session.get(ClassArmAssignment, assignment_id)
    if not (term and asg):
        return None
    students = [e.student for e in (StudentEnrollment.query
                .filter_by(class_arm_assignment_id=assignment_id, is_active=True)
                .join(Student).order_by(Student.surname, Student.first_name).all())]
    cols = score_columns()
    # Plain black-and-white — no fills or shading (clean to photocopy).
    styles = getSampleStyleSheet()
    h = ParagraphStyle('h', parent=styles['Title'], fontSize=15, textColor=colors.black, spaceAfter=1)
    meta = ParagraphStyle('m', parent=styles['Normal'], fontSize=10, textColor=colors.black, leading=15)
    hd = ParagraphStyle('hd', parent=styles['Normal'], fontSize=6.8, leading=7.8,
                        alignment=1, textColor=colors.black, fontName='Helvetica-Bold')
    nm = ParagraphStyle('nm', parent=styles['Normal'], fontSize=8.5, leading=10)

    # Header row: S/N, First, Middle, Surname, <score cols…>, Exam Total, General Total
    def col_head(label, mx=None):
        txt = label + (f'<br/><font size=6>/{mx}</font>' if mx else '')
        return Paragraph(txt, hd)
    header = [Paragraph('S/N', hd), Paragraph('First Name', hd),
              Paragraph('Middle Name', hd), Paragraph('Surname', hd)]
    for c in cols:
        header.append(col_head(c['label'], c['max']))
    header += [col_head('Exam Total'), col_head('General Total')]
    data = [header]
    for i, st in enumerate(students, 1):
        row = [str(i), Paragraph(pdf_escape(st.first_name or ''), nm),
               Paragraph(pdf_escape(st.middle_name or ''), nm),
               Paragraph(pdf_escape(st.surname or ''), nm)]
        row += [''] * (len(cols) + 2)          # blank score cells
        data.append(row)
    # A few spare blank rows for late entrants
    for _ in range(3):
        data.append([''] * (4 + len(cols) + 2))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=8 * mm, bottomMargin=8 * mm,
                            leftMargin=8 * mm, rightMargin=8 * mm,
                            title=f"Score sheet — {asg.display_name}")
    avail = landscape(A4)[0] - 16 * mm
    sn_w = 8 * mm
    score_w = 12 * mm
    n_score = len(cols) + 2
    names_w = avail - sn_w - score_w * n_score
    name_each = max(24 * mm, names_w / 3)
    widths = [sn_w, name_each, name_each, name_each] + [score_w] * n_score

    # Tall rows so marks can be hand-written; fill the page.
    body_rows = len(data) - 1
    page_h = landscape(A4)[1] - 16 * mm - 34 * mm     # minus margins and header block
    header_h = 13 * mm
    row_h = max(8 * mm, min(15 * mm, (page_h - header_h) / max(body_rows, 1))) if body_rows else 10 * mm
    heights = [header_h] + [row_h] * body_rows

    t = Table(data, colWidths=widths, rowHeights=heights, repeatRows=1)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (4, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTSIZE', (0, 1), (0, -1), 8),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.black),
    ]))

    subj = subject_name or '__________________________'
    metaline = (f"<b>Class:</b> {pdf_escape(asg.display_name)} &nbsp;&nbsp; "
                f"<b>Term:</b> {pdf_escape(term.name)} &nbsp;&nbsp; "
                f"<b>Session:</b> {pdf_escape(term.session.name if term.session else '')} &nbsp;&nbsp; "
                f"<b>Subject:</b> {pdf_escape(subj)}")
    elems = [Paragraph(pdf_escape(_school_name()), h),
             Paragraph('Continuous Assessment / Examination Score Sheet', meta),
             Paragraph(metaline, meta), Spacer(1, 5), t]
    doc.build(elems)
    return buf.getvalue()


def blank_sheet_filename(assignment, term):
    base = (assignment.display_name or 'class').replace(' ', '_')
    return f"score_sheet_{base}_{term.name.replace(' ', '_')}.pdf"


# --------------------------------------------------------------------------- #
# Class analytics report (PDF) — KPIs + distributions + subject difficulty
# --------------------------------------------------------------------------- #

def analytics_pdf(term_id, assignment_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
    from utils.web_exports import pdf_escape
    from utils.results_analytics import class_analytics

    term = db.session.get(Term, term_id)
    asg = db.session.get(ClassArmAssignment, assignment_id)
    if not (term and asg):
        return None
    a = class_analytics(term_id, assignment_id, use_cache=False)
    s = (a or {}).get('summary') or {}
    if not s.get('assessed'):
        return None
    primary, accent, light, ink = _theme()
    styles = getSampleStyleSheet()
    h = ParagraphStyle('h', parent=styles['Title'], fontSize=16, textColor=primary, spaceAfter=1)
    sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#6B7A74'))
    hh = ParagraphStyle('hh', parent=styles['Heading2'], fontSize=12, textColor=primary, spaceBefore=8, spaceAfter=4)
    muted = ParagraphStyle('mu', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#6B7A74'))

    def kpi_table():
        cells = [
            ('Class average', s.get('class_average')), ('Pass rate', f"{s.get('pass_rate')}%"),
            ('Highest avg', s.get('highest')), ('Lowest avg', s.get('lowest')),
            ('Students assessed', f"{s.get('assessed')}/{s.get('students')}"),
            ('Entry completion', f"{s.get('completion')}%"),
        ]
        if s.get('trend') is not None:
            cells.append(('vs last term', f"{'+' if s['trend'] > 0 else ''}{s['trend']}"))
        rows, row = [], []
        for i, (lbl, val) in enumerate(cells):
            row.append(Paragraph(f"<b><font size=15 color='#0D6A4E'>{pdf_escape(val)}</font></b>"
                                 f"<br/><font size=8 color='#6B7A74'>{pdf_escape(lbl)}</font>", muted))
            if len(row) == 3:
                rows.append(row); row = []
        if row:
            row += [''] * (3 - len(row)); rows.append(row)
        t = Table(rows, colWidths=[(A4[0] - 30 * mm) / 3] * 3)
        t.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0, colors.white),
                               ('BACKGROUND', (0, 0), (-1, -1), light),
                               ('INNERGRID', (0, 0), (-1, -1), 3, colors.white),
                               ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                               ('LEFTPADDING', (0, 0), (-1, -1), 10)]))
        return t

    def _bar_table(pairs, unit=''):
        mx = max([p[1] for p in pairs] + [1])
        data = []
        for label, val in pairs:
            w = int(round(38 * (val / mx))) if mx else 0
            bar = '█' * w
            data.append([Paragraph(pdf_escape(label), muted),
                         Paragraph(f"<font color='#0D6A4E'>{bar}</font> {pdf_escape(val)}{unit}", muted)])
        t = Table(data, colWidths=[45 * mm, A4[0] - 75 * mm])
        t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 8),
                               ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
        return t

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            title=f"Analytics — {asg.display_name}")
    elems = [Paragraph(pdf_escape(_school_name()), h),
             Paragraph(f"Class Performance Report · {pdf_escape(asg.display_name)} · "
                       f"{pdf_escape(term.full_name)}", sub),
             Spacer(1, 8), kpi_table(), Spacer(1, 4)]

    if a.get('score_bands'):
        elems += [Paragraph('Distribution of student averages', hh),
                  _bar_table([(b['band'], b['count']) for b in a['score_bands']])]
    if a.get('grade_distribution'):
        elems += [Paragraph('Grade distribution', hh),
                  _bar_table([(f"Grade {g['grade']}", g['count']) for g in a['grade_distribution']])]
    if a.get('gender'):
        elems += [Paragraph('By gender', hh),
                  _bar_table([(f"{g['group']} (avg {g['average']}, {g['pass_rate']}% pass)", g['count'])
                              for g in a['gender']])]
    if a.get('subjects'):
        elems += [Paragraph('Subject difficulty (hardest first)', hh)]
        srows = [['Subject', 'Average', 'Pass %', 'Assessed']]
        for sub_ in a['subjects']:
            srows.append([sub_['name'], str(sub_['average']) if sub_['assessed'] else '—',
                          (str(sub_['pass_rate']) + '%') if sub_['assessed'] else '—',
                          str(sub_['assessed'])])
        st = Table(srows, colWidths=[(A4[0] - 30 * mm) * f for f in (0.46, 0.18, 0.18, 0.18)], repeatRows=1)
        st.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'), ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D5DED9')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light]),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        elems.append(st)
    if a.get('intervention'):
        elems += [Paragraph(f"Needs attention ({len(a['intervention'])})", hh)]
        irows = [['Student', 'Average', 'Failing']]
        for st_ in a['intervention']:
            irows.append([st_['name'], str(st_['average']), str(st_['failed'])])
        it = Table(irows, colWidths=[(A4[0] - 30 * mm) * f for f in (0.6, 0.2, 0.2)], repeatRows=1)
        it.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#B43A2E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#D5DED9')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light]),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        elems.append(it)

    doc.build(elems)
    return buf.getvalue()


def analytics_filename(assignment, term):
    base = (assignment.display_name or 'class').replace(' ', '_')
    return f"analytics_{base}_{term.name.replace(' ', '_')}.pdf"
