"""Broadsheet multi-format export (PDF / Word / HD image) + blank score sheet."""
from config import Config
from models import (db, Branch, AcademicSession, Term, SchoolClass, ClassArm,
                    ClassArmAssignment, Student, StudentEnrollment, Subject, ClassSubject,
                    AssessmentType, StudentScore)
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


_SEQ = [0]


def _seed(app):
    with app.app_context():
        _SEQ[0] += 1
        tag = f'EX{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject(name=f'{tag}-English', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        at = (AssessmentType.query.filter_by(short_name='CA1').first()
              or AssessmentType(name='1st CA', short_name='CA1', max_score=5, order=1, is_active=True))
        if at.id is None:
            db.session.add(at); db.session.flush()
        for i in range(3):
            s = Student(student_id=f'{tag}-{i}', first_name=f'First{i}', middle_name='Mid',
                        surname=f'Sur{i}', gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
            db.session.add(StudentScore(student_id=s.id, class_subject_id=cs.id,
                                        assessment_type_id=at.id, score=4))
        db.session.commit()
        return dict(term=term.id, asg=caa.id)


def test_score_columns_reflect_active_assessment_types(app):
    from utils.broadsheet_export import score_columns
    with app.app_context():
        labels = [c['label'] for c in score_columns()]
        # CBT is always relabelled "CBT"; theory is "PBT/THEORY"; practical is "P.E/M.E"
        assert 'CBT' in labels and 'PBT/THEORY' in labels
        assert any(l.startswith('CA') for l in labels)


def test_broadsheet_pdf_word_image(app):
    ids = _seed(app)
    c = _admin(app)
    q = f"term_id={ids['term']}&assignment_id={ids['asg']}"

    r = c.get(f'/subjects/broadsheet/export?{q}&format=pdf')
    assert r.status_code == 200
    assert 'application/pdf' in r.headers['Content-Type']
    assert r.get_data()[:4] == b'%PDF'

    r = c.get(f'/subjects/broadsheet/export?{q}&format=word')
    assert r.status_code == 200
    assert 'wordprocessingml' in r.headers['Content-Type']
    assert r.get_data()[:2] == b'PK'

    r = c.get(f'/subjects/broadsheet/export?{q}&format=image')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'image/png'
    assert r.get_data()[:8] == b'\x89PNG\r\n\x1a\n'

    # default is still Excel (back-compat)
    r = c.get(f'/subjects/broadsheet/export?{q}')
    assert 'spreadsheetml' in r.headers['Content-Type']


def test_blank_score_sheet_pdf(app):
    ids = _seed(app)
    c = _admin(app)
    r = c.get(f"/subjects/broadsheet/blank-sheet?term_id={ids['term']}&assignment_id={ids['asg']}&subject=Mathematics")
    assert r.status_code == 200
    assert 'application/pdf' in r.headers['Content-Type']
    assert r.get_data()[:4] == b'%PDF'


def _seed_large(app, n=60):
    """A class large enough that the broadsheet spills onto more than one page."""
    with app.app_context():
        _SEQ[0] += 1
        tag = f'BIG{_SEQ[0]}'
        bid = Branch.get_default().id
        sess = AcademicSession(name=f'{tag}-Sess'); db.session.add(sess); db.session.flush()
        term = Term(session_id=sess.id, term_number=1, name='First Term'); db.session.add(term); db.session.flush()
        sc = SchoolClass.query.first(); arm = ClassArm.query.first()
        caa = ClassArmAssignment(class_id=sc.id, arm_id=arm.id, term_id=term.id, branch_id=bid)
        db.session.add(caa); db.session.flush()
        subj = Subject(name=f'{tag}-English', is_active=True); db.session.add(subj); db.session.flush()
        cs = ClassSubject(subject_id=subj.id, class_id=sc.id, arm_id=arm.id, term_id=term.id, is_active=True)
        db.session.add(cs); db.session.flush()
        at = (AssessmentType.query.filter_by(short_name='CA1').first()
              or AssessmentType(name='1st CA', short_name='CA1', max_score=5, order=1, is_active=True))
        if at.id is None:
            db.session.add(at); db.session.flush()
        for i in range(n):
            s = Student(student_id=f'{tag}-{i}', first_name=f'First{i}', middle_name='Mid',
                        surname=f'Sur{i}', gender='Male', is_active=True, branch_id=bid)
            db.session.add(s); db.session.flush()
            db.session.add(StudentEnrollment(student_id=s.id, class_arm_assignment_id=caa.id, is_active=True))
            db.session.add(StudentScore(student_id=s.id, class_subject_id=cs.id,
                                        assessment_type_id=at.id, score=4))
        db.session.commit()
        return dict(term=term.id, asg=caa.id)


def test_broadsheet_png_captures_every_page(app):
    """A multi-page broadsheet must export as one tall PNG covering all pages,
    not just the first (regression for the single-page image bug)."""
    import fitz
    from PIL import Image
    import io as _io
    from utils.broadsheet_export import broadsheet_pdf, broadsheet_png
    ids = _seed_large(app, n=60)
    with app.app_context():
        pdf = broadsheet_pdf(ids['term'], ids['asg'])
        doc = fitz.open(stream=pdf, filetype='pdf')
        assert doc.page_count > 1                       # roster really spills
        png = broadsheet_png(ids['term'], ids['asg'], dpi=100)
        img = Image.open(_io.BytesIO(png))
        # stitched height ≈ sum of per-page heights (well beyond a single page)
        one_page_h = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(100 / 72.0, 100 / 72.0)).height
        assert img.height > one_page_h * 1.5


def test_broadsheet_pdf_is_monochrome(app):
    """The broadsheet PDF must have no colour/shading — only black on white."""
    import fitz
    from utils.broadsheet_export import broadsheet_pdf
    ids = _seed(app)
    with app.app_context():
        pdf = broadsheet_pdf(ids['term'], ids['asg'])
        doc = fitz.open(stream=pdf, filetype='pdf')
        pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(2, 2))
        px = pix.samples
        n = pix.n                                       # bytes per pixel (3 or 4)
        # every pixel must be greyscale (r≈g≈b): no coloured header/zebra fills
        for i in range(0, len(px), n * 37):             # sample every 37th pixel
            r, g, b = px[i], px[i + 1], px[i + 2]
            assert max(r, g, b) - min(r, g, b) <= 12


def test_blank_sheet_single_page_for_normal_class(app):
    """A normal-size class fits the blank score sheet on one page."""
    import fitz
    from utils.broadsheet_export import blank_sheet_pdf
    ids = _seed_large(app, n=40)
    with app.app_context():
        pdf = blank_sheet_pdf(ids['term'], ids['asg'], subject_name='Maths')
        doc = fitz.open(stream=pdf, filetype='pdf')
        assert doc.page_count == 1


def test_blank_sheet_spills_for_very_large_class(app):
    """A very large class (45+) spills onto a second page rather than cramming."""
    import fitz
    from utils.broadsheet_export import blank_sheet_pdf
    ids = _seed_large(app, n=70)
    with app.app_context():
        pdf = blank_sheet_pdf(ids['term'], ids['asg'], subject_name='Maths')
        doc = fitz.open(stream=pdf, filetype='pdf')
        assert doc.page_count >= 2


def test_export_requires_selection(app):
    c = _admin(app)
    r = c.get('/subjects/broadsheet/export?format=pdf', follow_redirects=False)
    assert r.status_code in (302, 303)
    r = c.get('/subjects/broadsheet/blank-sheet', follow_redirects=False)
    assert r.status_code in (302, 303)


def test_analytics_report_pdf(app):
    ids = _seed(app)
    c = _admin(app)
    r = c.get(f"/subjects/analytics/report.pdf?term_id={ids['term']}&assignment_id={ids['asg']}")
    assert r.status_code == 200
    assert 'application/pdf' in r.headers['Content-Type']
    assert r.get_data()[:4] == b'%PDF'


def test_class_analytics_has_score_bands_and_gender(app):
    from utils.results_analytics import class_analytics
    ids = _seed(app)
    with app.app_context():
        a = class_analytics(ids['term'], ids['asg'], use_cache=False)
        assert 'score_bands' in a and len(a['score_bands']) == 6
        assert 'gender' in a          # boys seeded -> at least one group
        assert any(g['group'] == 'Boys' for g in a['gender'])


def test_per_subject_drilldown_data(app):
    from utils.results_analytics import class_analytics
    ids = _seed(app)
    with app.app_context():
        a = class_analytics(ids['term'], ids['asg'], use_cache=False)
        sub = a['subjects'][0]
        assert 'grades' in sub and 'bands' in sub
        assert len(sub['bands']) == 6
        assert 'highest' in sub and 'lowest' in sub


def test_score_entry_exposes_blank_sheet_link(app):
    ids = _seed(app)
    c = _admin(app)
    html = c.get(f"/subjects/scores?term_id={ids['term']}&assignment_id={ids['asg']}").get_data(as_text=True)
    assert '/subjects/broadsheet/blank-sheet' in html
