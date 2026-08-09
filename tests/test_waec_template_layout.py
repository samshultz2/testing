"""Layout-regression guard for every WAEC result template.

Renders each registered template and asserts on the PDF's extracted text and
page geometry — deterministic and environment-independent (no pixel baselines),
so it catches the classes of bugs seen in practice: a subject/grade silently
dropped, a template crashing when the subject count reflows (5 / 9 / 13),
the wrong page size, or the student name / year going missing — without being
flaky across fonts or CI hosts.
"""
import fitz
from models import db, Branch, Student, WAECResult
from utils import waec_result_gen as W

_YR = 2298
_SEQ = [0]

# A stable 9-subject sample (mixed grades so every grade band is exercised).
_NINE = {'Mathematics': 'A1', 'English Language': 'B2', 'Physics': 'A1',
         'Chemistry': 'B2', 'Biology': 'A1', 'Economics': 'B3',
         'Government': 'A1', 'Civic Education': 'A1', 'Data Processing': 'B2'}
_FIVE = dict(list(_NINE.items())[:5])
_THIRTEEN = dict(_NINE, **{'Further Mathematics': 'B3', 'Agricultural Science': 'C4',
                           'Geography': 'B2', 'Literature in English': 'C5'})


def _ctx(app, grades):
    with app.app_context():
        bid = Branch.get_default().id
        _SEQ[0] += 1
        st = Student(student_id=f'WTL-{_SEQ[0]}', first_name='Daniel', surname=f'Okafor{_SEQ[0]}',
                     gender='Male', is_active=True, branch_id=bid, waec_reg_number='4251200099')
        db.session.add(st); db.session.flush()
        for sub, g in grades.items():
            db.session.add(WAECResult(student_id=st.id, exam_year=_YR, subject=sub, grade=g))
        db.session.commit()
        ctx = W.build_context(db.session.get(Student, st.id), _YR)
    return ctx


def _text(pdf_buf):
    doc = fitz.open(stream=pdf_buf.getvalue(), filetype='pdf')
    return ' '.join(page.get_text() for page in doc).upper(), doc


def _expected_page(key):
    tpl = W.TEMPLATES[key]
    return (842, 595) if tpl['landscape'] else (595, 842)   # (w, h) rounded


def test_every_template_renders_all_content(app):
    """Each template shows the student name, the year, and — crucially — every
    subject and every grade (a dropped column is the failure we guard against)."""
    ctx = _ctx(app, _NINE)
    with app.app_context():
        for key in W.TEMPLATES:
            show = W.default_show(ctx)
            pdf = W.render_pdf(ctx, key, show, verify_url='https://verify.test/ABC')
            assert pdf.getvalue()[:4] == b'%PDF', key
            text, doc = _text(pdf)
            w, h = round(doc[0].rect.width), round(doc[0].rect.height)
            assert (w, h) == _expected_page(key), f'{key}: page {w}x{h}'
            assert 'DANIEL' in text, f'{key}: student name missing'
            assert str(_YR) in text, f'{key}: exam year missing'
            # every subject's leading word appears (robust to wrapping / casing)
            for subj in _NINE:
                head = subj.upper().split()[0]
                assert head in text, f'{key}: subject "{subj}" missing'
            # every distinct grade appears somewhere on the sheet
            for grade in set(_NINE.values()):
                assert grade in text, f'{key}: grade {grade} missing'
            doc.close()


def test_every_template_reflows_across_subject_counts(app):
    """5, 9 and 13 subjects must each render a valid A4 page for every template
    (guards the reflow crashes / overflow we fixed in the newer designs)."""
    with app.app_context():
        for grades in (_FIVE, _NINE, _THIRTEEN):
            ctx = _ctx(app, grades)
            for key in W.TEMPLATES:
                show = W.default_show(ctx)
                pdf = W.render_pdf(ctx, key, show, verify_url='https://verify.test/X')
                assert pdf.getvalue()[:4] == b'%PDF', f'{key} @ {len(grades)} subjects'
                text, doc = _text(pdf)
                # the last subject in a 13-subject sheet must still be present
                last = list(grades)[-1].upper().split()[0]
                assert last in text, f'{key}: last subject dropped at {len(grades)} subjects'
                doc.close()


def test_every_template_survives_minimal_components(app):
    """With almost everything toggled off (no photo/summary/seal/verification),
    each template must still produce a valid page rather than crash or leave a
    broken element."""
    ctx = _ctx(app, _NINE)
    keep = {'school_name', 'student_name', 'exam_name', 'exam_year', 'subjects', 'grades'}
    with app.app_context():
        minimal = W.resolve_show(ctx, {k: (k in keep) for k in W._ALL_COMPONENTS})
        for key in W.TEMPLATES:
            pdf = W.render_pdf(ctx, key, minimal)
            assert pdf.getvalue()[:4] == b'%PDF', key


def test_raster_outputs_are_nontrivial(app):
    """PNG and JPEG raster paths produce real images (not empty)."""
    ctx = _ctx(app, _NINE)
    with app.app_context():
        show = W.default_show(ctx)
        pdf = W.render_pdf(ctx, 'monument', show, verify_url='https://verify.test/IMG')
        png = W.render_image(pdf, 'png', 2.0)
        jpg = W.render_image(pdf, 'jpg', 2.0)
        assert png[:8] == b'\x89PNG\r\n\x1a\n' and len(png) > 5000
        assert jpg[:2] == b'\xff\xd8' and len(jpg) > 3000
