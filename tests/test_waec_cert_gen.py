"""WAEC result certificate generator — data/component/renderer core + routes."""
from models import db, Branch, Student, WAECResult
from config import Config
from utils import waec_result_gen as W

_YR = 2299
_SEQ = [0]


def _seed(app, grades=None):
    grades = grades or {'Mathematics': 'A1', 'English Language': 'B2', 'Physics': 'A1',
                        'Chemistry': 'B2', 'Biology': 'A1', 'Economics': 'B3',
                        'Government': 'A1', 'Civic Education': 'A1', 'Geography': 'C4'}
    with app.app_context():
        bid = Branch.get_default().id
        _SEQ[0] += 1
        st = Student(student_id=f'WCG-{_SEQ[0]}', first_name='Daniel', surname=f'Okafor{_SEQ[0]}',
                     gender='Male', is_active=True, branch_id=bid, waec_reg_number='4251203045')
        db.session.add(st); db.session.flush()
        for sub, g in grades.items():
            db.session.add(WAECResult(student_id=st.id, exam_year=_YR, subject=sub, grade=g))
        db.session.commit()
        return st.id


def _admin(app):
    from tests.conftest import login_token
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_build_context_and_stats(app):
    sid = _seed(app)
    with app.app_context():
        st = db.session.get(Student, sid)
        ctx = W.build_context(st, _YR)
    assert len(ctx['results']) == 9
    s = ctx['stats']
    assert s['total'] == 9 and s['credits'] == 9 and s['a1'] == 5
    assert s['distinctions'] == 8 and s['classification'] == 'Distinction'
    # reversed WAEC scale (A1=9…F9=1): 9*5 + 8*2 + 7 + 6 = 74 / 9 ≈ 8.22
    assert abs(s['average'] - 8.22) < 0.01
    # grade descriptions attached
    maths = next(r for r in ctx['results'] if r['subject'] == 'Mathematics')
    assert maths['grade'] == 'A1' and maths['desc'] == 'Excellent'


def test_components_availability_and_presets(app):
    sid = _seed(app)
    with app.app_context():
        ctx = W.build_context(db.session.get(Student, sid), _YR)
    show = W.default_show(ctx)
    assert show['subjects'] and show['grades']
    # no photo uploaded for this student -> photo component unavailable and forced off
    assert show['student_photo'] is False
    # requesting an unavailable component can never turn it on
    forced = W.resolve_show(ctx, {'student_photo': True})
    assert forced['student_photo'] is False
    # a preset selects only its keys (that are available)
    parent = W.preset_show(ctx, 'parent')
    assert parent['subjects'] and parent['grades'] and parent['school_name']
    assert parent['school_stamp'] is False
    warns = W.missing_warnings(ctx, {'student_photo': True})
    assert any('photograph' in w.lower() for w in warns)


def test_render_all_templates_pdf_png_jpeg(app):
    sid = _seed(app)
    with app.app_context():
        ctx = W.build_context(db.session.get(Student, sid), _YR)
        show = W.default_show(ctx)
        for key in W.TEMPLATES:
            pdf = W.render_pdf(ctx, key, show)
            data = pdf.getvalue()
            assert data[:4] == b'%PDF' and len(data) > 1000
            png = W.render_image(pdf, 'png')
            assert png[:8] == b'\x89PNG\r\n\x1a\n' and len(png) > 2000
            jpg = W.render_image(pdf, 'jpg')
            assert jpg[:2] == b'\xff\xd8' and len(jpg) > 2000


def test_render_handles_many_subjects(app):
    grades = {f'Subject {i}': 'C4' for i in range(1, 14)}   # 13 subjects -> compact table
    sid = _seed(app, grades)
    with app.app_context():
        ctx = W.build_context(db.session.get(Student, sid), _YR)
        assert len(ctx['results']) == 13
        pdf = W.render_pdf(ctx, 'classic', W.default_show(ctx))
        assert pdf.getvalue()[:4] == b'%PDF'
        assert any('13 subjects' in w for w in W.missing_warnings(ctx, {}))


def test_generator_page_and_picker(app):
    sid = _seed(app)
    c = _admin(app)
    r = c.get(f'/results/waec/certificate?student_id={sid}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Live preview' in body and 'Classic Academic' in body and 'Included information' in body
    # picker lists students with WAEC results
    assert c.get('/results/waec/certificate').status_code == 200


def test_preview_returns_png(app):
    sid = _seed(app)
    c = _admin(app)
    r = c.get(f'/results/waec/certificate/preview?student_id={sid}&year={_YR}'
              '&template=premium&c=school_name,student_name,subjects,grades,grade_desc')
    assert r.status_code == 200 and r.mimetype == 'image/png'
    assert r.data[:8] == b'\x89PNG\r\n\x1a\n'


def test_generate_downloads_and_audits(app):
    sid = _seed(app)
    c = _admin(app)
    tok = 'a' * 64
    with c.session_transaction() as s:
        s['_csrf_token'] = tok
    r = c.post('/results/waec/certificate/generate',
               data={'_csrf_token': tok, 'student_id': sid, 'year': _YR, 'template': 'classic',
                     'format': 'pdf', 'c': 'school_name,student_name,subjects,grades,grade_desc'})
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert r.data[:4] == b'%PDF'
    assert 'attachment' in (r.headers.get('Content-Disposition') or '')
    # PNG format too
    r = c.post('/results/waec/certificate/generate',
               data={'_csrf_token': tok, 'student_id': sid, 'year': _YR, 'template': 'creative',
                     'format': 'png', 'preset': 'social'})
    assert r.status_code == 200 and r.mimetype == 'image/png'
