"""Graduate document generation (Phase 2) — School Leaving Certificate, Statement
of Result, Academic Transcript, and Testimonial / Character Certificate.

Each document is a reportlab PDF carrying the school letterhead, a unique document
number, the issue date, a QR code + verification code that resolve to a PUBLIC
verification page (/verify/<code>), a light watermark, and signature lines. The
issue record lives in ``GraduateDocument``; the PDF is rendered on demand from the
permanent record so a reprint always reflects the stored history.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image as RLImage, HRFlowable, KeepInFrame)

# Room reserved (mm) at the foot of the page for the shared verification block.
# Kept close to the real footprint of the QR + verification lines (~36mm) so the
# body extends as far down the page as possible without crowding the footer.
_FOOTER_RESERVE = 38

_PRIMARY = colors.HexColor('#0e3a2f')
_ACCENT = colors.HexColor('#0e8a64')
_MUTED = colors.HexColor('#64748b')


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v or ''))


def _pronouns(gender):
    """A full, grammatically-correct pronoun set for document prose.

    Keys: S subject-capitalised, s subject, o object, p possessive,
    r reflexive, was the past 'be' form (singular they takes 'were')."""
    g = (gender or '').strip().lower()
    if g.startswith('m'):
        return {'S': 'He', 's': 'he', 'o': 'him', 'p': 'his',
                'r': 'himself', 'was': 'was'}
    if g.startswith('f'):
        return {'S': 'She', 's': 'she', 'o': 'her', 'p': 'her',
                'r': 'herself', 'was': 'was'}
    return {'S': 'They', 's': 'they', 'o': 'them', 'p': 'their',
            'r': 'themselves', 'was': 'were'}


def issue(student, doc_type, actor=None):
    """Get-or-create the GraduateDocument for (student, doc_type). On a repeat
    issue it bumps reprint_count. Returns the row (committed)."""
    from models import db, GraduateDocument, GRADUATE_DOC_TYPES
    if doc_type not in GRADUATE_DOC_TYPES:
        raise ValueError('Unknown document type')
    doc = GraduateDocument.query.filter_by(student_id=student.id, doc_type=doc_type).first()
    year = (student.graduation_date.year if student.graduation_date
            else __import__('datetime').date.today().year)
    if doc is None:
        # unique verification code (retry on the astronomically-rare collision)
        for _ in range(5):
            code = GraduateDocument.new_code()
            if not GraduateDocument.query.filter_by(verification_code=code).first():
                break
        doc = GraduateDocument(
            student_id=student.id, doc_type=doc_type,
            document_number=GraduateDocument.make_number(doc_type, student, year),
            verification_code=code, issued_by=actor, reprint_count=0)
        db.session.add(doc)
    else:
        doc.reprint_count = (doc.reprint_count or 0) + 1
        if actor:
            doc.issued_by = actor
    db.session.commit()
    return doc


def _qr_flowable(url, size_mm=26):
    try:
        import qrcode
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        return RLImage(buf, width=size_mm * mm, height=size_mm * mm)
    except Exception:
        return None


def _watermark(school_name):
    text = (school_name or 'CERTIFIED').upper()

    def draw(canvas, doc):
        canvas.saveState()
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(45)
        canvas.setFont('Helvetica-Bold', 60)
        canvas.setFillColor(colors.Color(0.06, 0.54, 0.39, alpha=0.06))
        canvas.drawCentredString(0, 0, text[:28])
        canvas.restoreState()
    return draw


# Document types whose layout is chosen from a per-school design catalog.
# Driven by the central document catalog so new designed types register once.
def _designed_docs():
    from utils import document_catalog
    return tuple(document_catalog.designed_types())


class _DesignedDocs:
    """Back-compat: ``doc_type in DESIGNED_DOCS`` stays valid while the set of
    designed document types is sourced from the catalog."""
    def __contains__(self, doc_type):
        return _is_designed(doc_type)

    def __iter__(self):
        return iter(_designed_docs())


DESIGNED_DOCS = _DesignedDocs()


def _is_designed(doc_type):
    from utils import document_catalog
    return document_catalog.is_designed(doc_type)


def _design_module(doc_type):
    from utils import document_catalog as cat
    from utils import (transcript_templates, slc_templates, sor_templates,
                       certificate_templates, letter_templates)
    return {cat.ENGINE_TRANSCRIPT: transcript_templates, cat.ENGINE_SLC: slc_templates,
            cat.ENGINE_STATEMENT: sor_templates,
            cat.ENGINE_CERTIFICATE: certificate_templates,
            cat.ENGINE_LETTER: letter_templates}.get(cat.engine(doc_type))


def design_key_for(doc_type):
    """The design this school has chosen for ``doc_type`` (falls back to default)."""
    mod = _design_module(doc_type)
    if mod is None:
        return None
    try:
        from models import DocTemplatePref
        p = DocTemplatePref.query.filter_by(doc_type=doc_type).first()
        if p and p.template_key and p.template_key in mod.TEMPLATES:
            return p.template_key
    except Exception:
        pass
    return mod.DEFAULT_TEMPLATE


def _margins_for(mod, key, land):
    """(top, bottom, left, right) page margins in mm. A design module may expose a
    ``page_margins(key)`` hook to request tighter margins (e.g. a statement that
    should fill the page); otherwise the standard document margins apply."""
    fn = getattr(mod, 'page_margins', None)
    if fn:
        try:
            m = fn(key)
            if m:
                return m
        except Exception:
            pass
    return (16, 18, 18, 18) if land else (16, 20, 20, 20)


def _apply_layout(mod, key, ctx, pagesize):
    """Attach the usable body height (page minus margins minus footer reserve) to
    the ctx so designs that fill the page know how much room they have."""
    land = mod.is_landscape(key)
    mt, mb, _ml, _mr = _margins_for(mod, key, land)
    reserve = 34 if land else _FOOTER_RESERVE
    ctx['_avail'] = (pagesize[1] - (mt + mb) * mm) - reserve * mm
    return ctx


def _fit_body(el, pagesize, margins, reserve=_FOOTER_RESERVE):
    """Wrap a document body so it can never spill onto a second page: it renders at
    full size when it fits, and is scaled down only as much as needed otherwise.
    ``reserve`` mm at the foot is left for the verification footer that follows."""
    mt, mb, ml, mr = margins
    frame_w = pagesize[0] - (ml + mr) * mm
    body_h = pagesize[1] - (mt + mb) * mm - reserve * mm
    return [KeepInFrame(frame_w, body_h, list(el), mode='shrink', hAlign='CENTER', vAlign='TOP')]


def _fit_page(body, footer, pagesize, margins):
    """Fit the body AND its footer together inside the full printable area as one
    shrink-frame, so a document can NEVER spill onto a second page. The body is
    laid out to leave footer room (via ctx['_avail'] = frame − reserve); wrapping
    the pair in a frame of the *full* height means any small over-run is scaled
    down here instead of pushing the footer onto page 2."""
    mt, mb, ml, mr = margins
    frame_w = pagesize[0] - (ml + mr) * mm
    frame_h = pagesize[1] - (mt + mb) * mm
    return [KeepInFrame(frame_w, frame_h, list(body) + list(footer),
                        mode='shrink', hAlign='CENTER', vAlign='TOP')]


def list_designs(doc_type):
    mod = _design_module(doc_type)
    return mod.list_templates() if mod else []


def valid_design(doc_type, key):
    mod = _design_module(doc_type)
    return bool(mod and key in mod.TEMPLATES)


def _slc_fields(ctx):
    """Derive School-Leaving-Certificate prose fields from the record."""
    from datetime import date
    academic = ctx.get('academic') or {}
    cum = academic.get('cumulative')
    perf = ''
    if cum is not None:
        perf = ('Excellent' if cum >= 75 else 'Very Good' if cum >= 65 else 'Good'
                if cum >= 55 else 'Average' if cum >= 45 else 'Fair')
    subs = sorted({s['subject'] for t in academic.get('terms', []) for s in t.get('subjects', [])})
    st = ctx['student']
    from_year = (ctx.get('admission_session') or '').split('/')[0]
    to_year = (str(st.graduation_date.year) if getattr(st, 'graduation_date', None)
               else (ctx.get('grad_session') or '').split('/')[-1])
    doc = ctx.get('doc')
    issued = (doc.created_at.strftime('%d %B %Y') if doc and getattr(doc, 'created_at', None)
              else date.today().strftime('%d %B %Y'))
    ctx.update(performance=perf, subjects_list=', '.join(subs),
               character='Satisfactory', from_year=from_year, to_year=to_year, issued=issued)
    return ctx


def _doc_ctx(student, doc, school, rec):
    grad_when = (student.graduation_date.strftime('%B %Y') if student.graduation_date
                 else (rec.get('admission_session') or ''))
    grad_session = ''
    try:
        from models import AcademicSession, db
        if student.graduation_session_id:
            gs = db.session.get(AcademicSession, student.graduation_session_id)
            grad_session = gs.name if gs else ''
    except Exception:
        pass
    ctx = {'student': student, 'academic': rec.get('academic') or {}, 'bio': rec.get('bio') or {},
           'school': school, 'grad_when': grad_when, 'grad_session': grad_session,
           'admission_session': rec.get('admission_session') or '', 'doc': doc,
           'doc_type': getattr(doc, 'doc_type', None), 'waec': _waec(student)}
    return _slc_fields(ctx)


def _waec(student):
    """The student's WAEC result (latest exam year): [{'subject','grade'}], plus the
    year. Empty when none recorded."""
    try:
        from models import WAECResult
        rows = WAECResult.query.filter_by(student_id=student.id).all()
    except Exception:
        return {}
    if not rows:
        return {}
    year = max(r.exam_year for r in rows if r.exam_year) if any(r.exam_year for r in rows) else None
    subs = sorted([{'subject': r.subject, 'grade': r.grade} for r in rows
                   if r.exam_year == year], key=lambda s: s['subject'] or '')
    return {'year': year, 'subjects': subs}


def _verification_footer(doc, verify_url, small):
    els = [Spacer(1, 14), HRFlowable(width='100%', thickness=0.5, color=_MUTED)]
    vlines = [Paragraph(f"<b>Document No.</b> {_esc(doc.document_number)}", small),
              Paragraph(f"<b>Verification code:</b> {_esc(doc.verification_code)}", small),
              Paragraph(f"Verify this document at<br/>{_esc(verify_url)}", small)]
    if doc.reprint_count:
        vlines.append(Paragraph(f"<i>Reprint #{doc.reprint_count}</i>", small))
    qr = _qr_flowable(verify_url)
    if qr is not None:
        foot = Table([[vlines, qr]], colWidths=[None, 30 * mm])
        foot.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        els.append(foot)
    else:
        els += vlines
    return els


def _page_painter(school_name, decorator=None):
    """Combine the watermark with an optional per-design page decorator (border)."""
    wm = _watermark(school_name)

    def paint(canvas, doc):
        wm(canvas, doc)
        if decorator is not None:
            try:
                decorator(canvas, doc)
            except Exception:
                pass
    return paint


def preview_document(doc_type, template_key):
    """Render a sample document with the given design (no real student needed)."""
    from reportlab.lib.pagesizes import landscape
    from utils.school import school_profile
    mod = _design_module(doc_type)
    if mod is None:
        raise ValueError('Unknown document type')
    school = school_profile()
    ctx = mod.sample_ctx(school)
    ctx['doc_type'] = doc_type            # certificate engine renders per doc type
    _slc_fields(ctx)                      # sample gets SLC prose fields too
    land = mod.is_landscape(template_key)
    pagesize = landscape(A4) if land else A4
    mt, mb, ml, mr = _margins_for(mod, template_key, land)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=pagesize,
                            leftMargin=ml * mm, rightMargin=mr * mm,
                            topMargin=mt * mm, bottomMargin=mb * mm, title='Document preview')
    ss = getSampleStyleSheet()
    small = ParagraphStyle('s', parent=ss['Normal'], fontSize=8, textColor=_MUTED)
    _apply_layout(mod, template_key, ctx, pagesize)
    body = mod.build_flowables(template_key, ctx)
    footer = [Spacer(1, 12), HRFlowable(width='100%', thickness=0.5, color=_MUTED),
              Paragraph('<b>PREVIEW — sample data.</b> A QR code and verification code '
                        'appear here on a real document.', small)]
    el = _fit_page(body, footer, pagesize, (mt, mb, ml, mr))
    on_page = _page_painter(school['name'], mod.page_decorator(template_key))
    pdf.build(el, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    return buf


def render(student, doc, verify_url):
    """Return (BytesIO, filename) for a graduate document PDF."""
    from utils.school import school_profile, logo_flowable, logo_header_flowable
    from utils.graduate_record import build_record
    from models import GRADUATE_DOC_TYPES

    school = school_profile()
    rec = build_record(student)
    label = GRADUATE_DOC_TYPES.get(doc.doc_type, 'Document')

    ss = getSampleStyleSheet()
    small = ParagraphStyle('s', parent=ss['Normal'], fontSize=8, textColor=_MUTED)

    # Transcripts & School Leaving Certificates use a school-chosen design (which
    # may be landscape); everything else uses the standard portrait body.
    if doc.doc_type in DESIGNED_DOCS:
        from reportlab.lib.pagesizes import landscape
        mod = _design_module(doc.doc_type)
        key = design_key_for(doc.doc_type)
        land = mod.is_landscape(key)
        pagesize = landscape(A4) if land else A4
        mt, mb, ml, mr = _margins_for(mod, key, land)
        buf = io.BytesIO()
        pdf = SimpleDocTemplate(buf, pagesize=pagesize,
                                leftMargin=ml * mm, rightMargin=mr * mm,
                                topMargin=mt * mm, bottomMargin=mb * mm,
                                title=f'{label} — {student.full_name}')
        ctx = _apply_layout(mod, key, _doc_ctx(student, doc, school, rec), pagesize)
        el = _fit_page(mod.build_flowables(key, ctx),
                       _verification_footer(doc, verify_url, small), pagesize, (mt, mb, ml, mr))
        on_page = _page_painter(school['name'], mod.page_decorator(key))
        pdf.build(el, onFirstPage=on_page, onLaterPages=on_page)
        buf.seek(0)
        return buf, f"{doc.doc_type}_{(student.student_id or student.id)}.pdf"

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=16 * mm, bottomMargin=20 * mm,
                            title=f'{label} — {student.full_name}')
    center = ParagraphStyle('c', parent=ss['Normal'], alignment=TA_CENTER)
    sch = ParagraphStyle('sch', parent=center, fontSize=17, leading=20, textColor=_PRIMARY)
    muted = ParagraphStyle('m', parent=center, fontSize=8.5, textColor=_MUTED)
    title = ParagraphStyle('t', parent=center, fontSize=15, leading=18, spaceBefore=8,
                           spaceAfter=8, textColor=_ACCENT, fontName='Helvetica-Bold')
    body = ParagraphStyle('b', parent=ss['Normal'], fontSize=11.5, leading=18,
                          alignment=TA_JUSTIFY, spaceAfter=6)

    el = []
    # ---- letterhead ----
    head_items = [(Paragraph(_esc(school['name'] or 'School'), sch), school['name'] or 'School',
                   'Helvetica-Bold', 17)]
    if school.get('address'):
        head_items.append((Paragraph(_esc(school['address']), muted), school['address'], 'Helvetica', 8.5))
    line3 = ' · '.join([x for x in [school.get('phone'), school.get('email')] if x])
    if line3:
        head_items.append((Paragraph(_esc(line3), muted), line3, 'Helvetica', 8.5))
    logo = logo_flowable(max_h_mm=16, max_w_mm=26)
    header = logo_header_flowable(logo, head_items) if logo is not None else None
    if header is not None:
        el.append(header)
    else:
        for para, *_ in head_items:
            el.append(para)
    el.append(Spacer(1, 4))
    el.append(HRFlowable(width='100%', thickness=1, color=_ACCENT))
    el.append(Paragraph(label.upper(), title))

    grad_when = (student.graduation_date.strftime('%B %Y') if student.graduation_date
                 else (rec.get('admission_session') or ''))
    grad_session = ''
    try:
        from models import AcademicSession, db
        if student.graduation_session_id:
            gs = db.session.get(AcademicSession, student.graduation_session_id)
            grad_session = gs.name if gs else ''
    except Exception:
        pass
    pron = _pronouns(student.gender)

    # ---- per-type body ----
    el += _body_for(doc.doc_type, student, rec, school, grad_when, grad_session,
                    pron, body, small, center)

    # ---- signatures ----
    el.append(Spacer(1, 18))
    sig = Table([['_' * 26, '', '_' * 26],
                 [Paragraph('Principal', small), '', Paragraph('Registrar', small)]],
                colWidths=[60 * mm, 30 * mm, 60 * mm])
    sig.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                             ('TOPPADDING', (0, 1), (-1, 1), 2)]))
    el.append(sig)

    # ---- keep the body on a single page, then the verification footer ----
    story = _fit_body(el, A4, (16, 20, 20, 20))
    story += _verification_footer(doc, verify_url, small)

    wm = _watermark(school['name'])
    pdf.build(story, onFirstPage=wm, onLaterPages=wm)
    buf.seek(0)
    fname = f"{doc.doc_type}_{(student.student_id or student.id)}.pdf"
    return buf, fname


def _body_for(doc_type, student, rec, school, grad_when, grad_session, pron, body, small, center):
    S, s, o, pp, rf, was = (pron['S'], pron['s'], pron['o'],
                            pron['p'], pron['r'], pron['was'])
    name = student.full_name
    adm = student.student_id or ''
    school_name = school.get('name') or 'the school'
    els = []

    if doc_type == 'slc':
        els.append(Paragraph(
            f"This is to certify that <b>{_esc(name)}</b> (Admission No. {_esc(adm)}) "
            f"was a bona fide student of <b>{_esc(school_name)}</b> and successfully "
            f"completed the Senior Secondary School (SSS3) programme"
            + (f" in the {_esc(grad_session)} academic session" if grad_session else "")
            + (f", graduating in {_esc(grad_when)}" if grad_when else "") + ".", body))
        els.append(Paragraph(
            f"During {pp} time in the school, {s} {was} of good conduct and character, "
            f"and left in good standing. This certificate is issued at {pp} request "
            f"for whatever legitimate purpose it may serve.", body))

    elif doc_type == 'testimonial':
        els.append(Paragraph(
            f"This testimonial is issued in respect of <b>{_esc(name)}</b> "
            f"(Admission No. {_esc(adm)}), a former student of <b>{_esc(school_name)}</b>"
            + (f" who graduated in {_esc(grad_when)}" if grad_when else "") + ".", body))
        els.append(Paragraph(
            f"Throughout {pp} stay, {s} demonstrated commendable discipline, respect and "
            f"cooperation, and maintained a good relationship with both staff and peers. "
            f"{S} {was} diligent in {pp} studies and conducted {rf} in a manner worthy "
            f"of emulation.", body))
        els.append(Paragraph(
            f"We therefore recommend {_esc(name)} without reservation and wish {o} "
            f"success in {pp} future endeavours.", body))

    elif doc_type == 'statement':
        els.append(Paragraph(
            f"This is a statement of the academic record of <b>{_esc(name)}</b> "
            f"(Admission No. {_esc(adm)}) of <b>{_esc(school_name)}</b>"
            + (f", who graduated in {_esc(grad_when)}" if grad_when else "") + ".", body))
        ac = rec.get('academic') or {}
        if ac.get('cumulative') is not None:
            els.append(Paragraph(f"<b>Cumulative average:</b> {ac['cumulative']}% "
                                 f"across {ac.get('terms_count', 0)} assessed term(s).", body))
        terms = ac.get('terms') or []
        last = terms[-1] if terms else None
        if last and last.get('subjects'):
            els.append(Spacer(1, 4))
            els.append(Paragraph(f"Most recent results — {_esc(last.get('session'))} "
                                 f"{_esc(last.get('term'))}:", small))
            els.append(_subject_table(last['subjects']))
        if not terms:
            els.append(Paragraph("No internal academic results are on record for this "
                                 "student.", body))

    elif doc_type == 'recommendation':
        els.append(Paragraph("To whom it may concern,", body))
        els.append(Paragraph(
            f"I write to recommend <b>{_esc(name)}</b> (Admission No. {_esc(adm)}), "
            f"a graduate of <b>{_esc(school_name)}</b>"
            + (f" ({_esc(grad_when)})" if grad_when else "") + ". "
            f"Throughout {pp} time with us, {s} distinguished {rf} through "
            f"dedication, integrity and a strong work ethic.", body))
        ac = rec.get('academic') or {}
        if ac.get('cumulative') is not None:
            els.append(Paragraph(
                f"{S} maintained a cumulative average of {ac['cumulative']}%, and "
                f"consistently applied {rf} to both academic and co-curricular life.", body))
        els.append(Paragraph(
            f"I am confident {s} will be a valuable addition to any institution or "
            f"organisation, and I recommend {o} without reservation.", body))

    elif doc_type == 'conduct':
        els.append(Paragraph(
            f"This report certifies the conduct of <b>{_esc(name)}</b> "
            f"(Admission No. {_esc(adm)}), a graduate of <b>{_esc(school_name)}</b>"
            + (f" who left in {_esc(grad_when)}" if grad_when else "") + ".", body))
        disc = rec.get('discipline') or []
        if not disc:
            els.append(Paragraph(
                f"The school has <b>no record of any disciplinary infraction</b> against "
                f"this student. {S} {was} of good behaviour throughout {pp} stay.", body))
        else:
            els.append(Paragraph(f"The following {len(disc)} conduct record(s) are on file:", body))
            rows = [['Date', 'Category', 'Severity', 'Action taken']]
            for r in disc:
                rows.append([r.get('date', ''), r.get('category', ''),
                             r.get('severity') or '—', r.get('action') or '—'])
            t = Table(rows, colWidths=[28 * mm, 45 * mm, 30 * mm, 57 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), _PRIMARY), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
            els.append(t)

    elif doc_type == 'notification':
        els.append(Paragraph(
            f"This slip notifies the results of <b>{_esc(name)}</b> "
            f"(Admission No. {_esc(adm)}) of <b>{_esc(school_name)}</b>"
            + (f", {_esc(grad_when)}" if grad_when else "") + ".", body))
        ac = rec.get('academic') or {}
        terms = ac.get('terms') or []
        last = terms[-1] if terms else None
        if last and last.get('subjects'):
            els.append(Paragraph(f"{_esc(last.get('session'))} · {_esc(last.get('term'))}"
                                 + (f" — average {last['average']}%" if last.get('average') is not None else ''), small))
            els.append(_subject_table(last['subjects']))
        elif ac.get('cumulative') is not None:
            els.append(Paragraph(f"Cumulative average: <b>{ac['cumulative']}%</b>.", body))
        else:
            els.append(Paragraph("No internal results are on record for this student.", body))
        els.append(Spacer(1, 4))
        els.append(Paragraph("This is a preliminary notification and does not replace the "
                             "official statement of result or certificate.", small))

    elif doc_type == 'transcript':
        els.append(Paragraph(
            f"Academic transcript for <b>{_esc(name)}</b> (Admission No. {_esc(adm)}) — "
            f"the complete internal academic history held by <b>{_esc(school_name)}</b>.", body))
        ac = rec.get('academic') or {}
        if ac.get('cumulative') is not None:
            els.append(Paragraph(f"<b>Cumulative average:</b> {ac['cumulative']}%", body))
        for t in (ac.get('terms') or []):
            els.append(Spacer(1, 6))
            avg = f" — term average {t['average']}%" if t.get('average') is not None else ''
            els.append(Paragraph(f"<b>{_esc(t.get('session'))} · {_esc(t.get('term'))}</b>{avg}", small))
            els.append(_subject_table(t.get('subjects') or []))
        if not (ac.get('terms')):
            els.append(Paragraph("No internal academic results are on record.", body))

    return els


def _subject_table(subjects):
    rows = [['Subject', 'Score', 'Grade', 'Position']]
    for s in subjects:
        rows.append([s.get('subject', ''), _fmt(s.get('score')), s.get('grade') or '—',
                     str(s.get('position') or '—')])
    t = Table(rows, colWidths=[85 * mm, 25 * mm, 25 * mm, 25 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _fmt(v):
    return '' if v is None else (str(int(v)) if float(v).is_integer() else str(v))
