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


def test_executive_template_registered_and_renders(app):
    # the new Executive Academic 2026 layout is part of the collection…
    assert 'executive' in W.TEMPLATES and 'executive' in W._CANVAS_DRAW
    assert W.TEMPLATES['executive']['name'] == 'Executive Academic — 2026'
    assert W.TEMPLATES['executive']['landscape'] is False
    assert any(t['key'] == 'executive' for t in W.list_templates())
    assert 'executive' in W.PRESETS
    sid = _seed(app)   # the 9 sample subjects (5 of them A1)
    with app.app_context():
        ctx = W.build_context(db.session.get(Student, sid), _YR)
        # …its full preset turns on the summary + seal + verification the design shows
        show = W.preset_show(ctx, 'executive')
        assert show['subjects'] and show['grades'] and show['total_subjects']
        assert show['a1_count'] and show['credits'] and show['school_stamp']
        # the drawn seal needs no uploaded stamp file to be offered
        assert show['school_stamp'] is True
        # counts come from the real data, not hard-coded (5 A1s, 9 credits)
        assert ctx['stats']['a1'] == 5 and ctx['stats']['credits'] == 9
        pdf = W.render_pdf(ctx, 'executive', show,
                           verify_url='https://example.test/verify/ABC')
        assert pdf.getvalue()[:4] == b'%PDF'
        # minimal selection still renders (rebalances without photo/summary/seal)
        minimal = W.resolve_show(ctx, {k: (k in {'school_name', 'student_name',
                                 'exam_name', 'exam_year', 'subjects', 'grades'})
                                 for k in W._ALL_COMPONENTS})
        assert W.render_pdf(ctx, 'executive', minimal).getvalue()[:4] == b'%PDF'


def test_academic_profile_template_registered_and_renders(app):
    assert 'profile' in W.TEMPLATES and 'profile' in W._CANVAS_DRAW
    assert W.TEMPLATES['profile']['name'] == 'Academic Profile — 2026'
    assert W.TEMPLATES['profile']['landscape'] is False
    assert 'profile' in W.PRESETS
    sid = _seed(app)                       # the 9 sample subjects (5 A1s)
    with app.app_context():
        ctx = W.build_context(db.session.get(Student, sid), _YR)
        show = W.preset_show(ctx, 'profile')
        assert show['subjects'] and show['grades'] and show['total_subjects']
        assert show['a1_count'] and show['credits']
        assert ctx['stats']['a1'] == 5 and ctx['stats']['credits'] == 9
        pdf = W.render_pdf(ctx, 'profile', show, verify_url='https://example.test/verify/ABC')
        assert pdf.getvalue()[:4] == b'%PDF'
        # renders on standard A4 (like every portrait template)
        import fitz
        doc = fitz.open(stream=pdf.getvalue(), filetype='pdf')
        assert round(doc[0].rect.width) == 595 and round(doc[0].rect.height) == 842
        # minimal selection still renders (rail rebalances without photo/summary)
        minimal = W.resolve_show(ctx, {k: (k in {'school_name', 'student_name',
                                 'exam_name', 'exam_year', 'subjects', 'grades'})
                                 for k in W._ALL_COMPONENTS})
        assert W.render_pdf(ctx, 'profile', minimal).getvalue()[:4] == b'%PDF'


def test_meridian_template_registered_and_renders(app):
    assert 'meridian' in W.TEMPLATES and 'meridian' in W._CANVAS_DRAW
    assert W.TEMPLATES['meridian']['name'] == 'Meridian — 2026'
    assert W.TEMPLATES['meridian']['landscape'] is False
    assert 'meridian' in W.PRESETS
    sid = _seed(app)
    with app.app_context():
        ctx = W.build_context(db.session.get(Student, sid), _YR)
        show = W.preset_show(ctx, 'meridian')
        assert show['subjects'] and show['grades'] and show['total_subjects']
        assert ctx['stats']['a1'] == 5 and ctx['stats']['credits'] == 9
        pdf = W.render_pdf(ctx, 'meridian', show, verify_url='https://example.test/verify/ABC')
        assert pdf.getvalue()[:4] == b'%PDF'
        import fitz
        doc = fitz.open(stream=pdf.getvalue(), filetype='pdf')
        assert round(doc[0].rect.width) == 595 and round(doc[0].rect.height) == 842
        # rebalances with the photo / summary / seal removed
        minimal = W.resolve_show(ctx, {k: (k in {'school_name', 'student_name',
                                 'exam_name', 'exam_year', 'subjects', 'grades'})
                                 for k in W._ALL_COMPONENTS})
        assert W.render_pdf(ctx, 'meridian', minimal).getvalue()[:4] == b'%PDF'


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
    # live search: a fetch request returns JSON matches (no full page)
    r = c.get('/results/waec/certificate?q=Okafor', headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200 and r.is_json
    data = r.get_json()
    assert 'students' in data and any('Okafor' in s['full_name'] for s in data['students'])
    assert all('url' in s and 'student_id' in s for s in data['students'])


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


def _csrf(c):
    with c.session_transaction() as s:
        s['_csrf_token'] = 'a' * 64
    return 'a' * 64


def test_generate_records_issue_and_public_verify(app):
    from models import WAECCertIssue
    sid = _seed(app)
    c = _admin(app)
    tok = _csrf(c)
    c.post('/results/waec/certificate/generate',
           data={'_csrf_token': tok, 'student_id': sid, 'year': _YR, 'template': 'prestige',
                 'format': 'pdf', 'c': 'school_name,student_name,subjects,grades,qr_code,verification_code'})
    with app.app_context():
        rec = WAECCertIssue.query.filter_by(student_id=sid).order_by(WAECCertIssue.id.desc()).first()
        assert rec is not None and rec.code.startswith('WR-')
        code = rec.code
    # public verify page — no login required
    pub = app.test_client()
    r = pub.get(f'/results/waec/verify/{code}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Authentic' in body and code in body
    # unknown code → not found (still 200, shows message)
    r = pub.get('/results/waec/verify/WR-NOPE9999')
    assert r.status_code == 200 and 'No document found' in r.get_data(as_text=True)


def test_template_management_and_recommendation(app):
    from models import WAECCertTemplate, Student
    sid = _seed(app)
    c = _admin(app)
    tok = _csrf(c)
    # create a year-specific default template using the Creative design
    r = c.post('/results/waec/certificate/templates',
               data={'_csrf_token': tok, 'name': 'WAEC Sentinel Creative', 'base_layout': 'creative',
                     'year': _YR, 'is_default': 'on', 'preset': 'official'})
    assert r.status_code in (302, 200)
    with app.app_context():
        t = WAECCertTemplate.query.filter_by(name='WAEC Sentinel Creative').first()
        assert t and t.base_layout == 'creative' and t.year == _YR and t.is_default
    # the generator pre-selects the assigned design for that year
    g = c.get(f'/results/waec/certificate?student_id={sid}&year={_YR}').get_data(as_text=True)
    assert 'WAEC Sentinel Creative' in g            # recommended banner
    assert 'value="creative"' in g and 'checked' in g


def test_bulk_zip_generation(app):
    import io, zipfile
    _seed(app); _seed(app)                          # two students, same sentinel year
    c = _admin(app)
    tok = _csrf(c)
    with app.app_context():
        from models import Student, WAECResult
        ids = [s.id for s in Student.query.join(WAECResult)
               .filter(WAECResult.exam_year == _YR).distinct().all()]
    r = c.post('/results/waec/certificate/bulk',
               data={'_csrf_token': tok, 'year': _YR, 'template': 'classic', 'format': 'pdf',
                     'student_ids': [str(i) for i in ids]})
    assert r.status_code == 200 and r.mimetype == 'application/zip'
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    names = zf.namelist()
    assert len(names) >= 2 and all(n.endswith('.pdf') for n in names)


def test_save_and_use_preset(app):
    from models import WAECCertPreset
    sid = _seed(app)
    c = _admin(app)
    tok = _csrf(c)
    r = c.post('/results/waec/certificate/presets',
               data={'_csrf_token': tok, 'name': 'My Preset',
                     'c': 'school_name,student_name,subjects,grades'})
    assert r.status_code in (302, 200)
    with app.app_context():
        p = WAECCertPreset.query.filter_by(name='My Preset').first()
        assert p and set(p.components()) == {'school_name', 'student_name', 'subjects', 'grades'}
    # it now appears in the generator's preset list
    g = c.get(f'/results/waec/certificate?student_id={sid}&year={_YR}').get_data(as_text=True)
    assert 'My Preset' in g
