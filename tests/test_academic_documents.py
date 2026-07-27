"""Academic Documents & Publishing system — catalogue, collections, certificate
engine, and the shared render pipeline for the new document types."""
import re

import fitz
import pytest
from config import Config
from tests.conftest import login_token

from utils import document_catalog as cat
from utils import (doc_themes, certificate_templates as ce, letter_templates as lt,
                   graduate_docs as gd)


def _admin(app):
    c = app.test_client()
    tok = login_token(c)
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': tok})
    return c


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


def _fake_logo(max_h_mm=16, max_w_mm=40):
    from reportlab.lib.units import mm
    from reportlab.graphics.shapes import Drawing, Circle
    from reportlab.lib import colors
    d = Drawing(max_h_mm * mm, max_h_mm * mm)
    d.add(Circle(max_h_mm * mm / 2, max_h_mm * mm / 2, max_h_mm * mm / 2,
                 fillColor=colors.HexColor('#0e8a64')))
    return d


@pytest.fixture(autouse=True)
def _school(monkeypatch):
    import utils.school as school
    monkeypatch.setattr(school, 'logo_flowable', _fake_logo, raising=False)
    monkeypatch.setattr(school, 'school_profile',
                        lambda: {'name': 'Bright Future Academy', 'address': 'Lagos',
                                 'phone': '0800', 'email': 'a@b.c', 'motto': 'Excellence'},
                        raising=False)


def test_catalog_registers_certificate_family():
    designed = set(cat.designed_types())
    for dt in ('transcript', 'slc', 'statement', 'graduation', 'completion',
               'attendance_cert', 'character_cert', 'merit_award', 'best_graduating',
               'best_subject', 'leadership_award', 'sports_award', 'excellence_award'):
        assert dt in designed, dt
        assert cat.label(dt)
        assert cat.category(dt)


def test_catalog_grouping_is_ordered_and_complete():
    grouped = cat.by_category()
    cats = [c for c, _ in grouped]
    assert cats == [c for c in cat.CATEGORY_ORDER if c in cats]
    flat = {dt for _c, items in grouped for dt, _l, _d in items}
    assert flat == set(cat.CATALOG)


def test_collections_library_is_rich():
    # A deep palette library backing the layouts.
    assert len(doc_themes.COLLECTIONS) >= 20
    assert ce.DEFAULT_TEMPLATE in ce.TEMPLATES


def test_certificate_templates_are_distinct_layouts():
    # Each certificate template is a DIFFERENT layout function bound to a DIFFERENT
    # palette — no two are the same design, and none is a mere recolour.
    from utils import cert_layouts as cl
    fns = [v['fn'] for v in cl.LAYOUTS.values()]
    themes = [v['theme'] for v in cl.LAYOUTS.values()]
    assert len(set(id(f) for f in fns)) == len(fns), 'a layout function is reused'
    assert len(set(themes)) == len(themes), 'a palette is reused across layouts'
    assert set(ce.TEMPLATES) == set(cl.LAYOUTS)


def test_letter_templates_are_distinct_layouts():
    from utils import letter_layouts as ll
    fns = [v['fn'] for v in ll.LAYOUTS.values()]
    themes = [v['theme'] for v in ll.LAYOUTS.values()]
    assert len(set(id(f) for f in fns)) == len(fns), 'a letter layout function is reused'
    assert len(set(themes)) == len(themes), 'a palette is reused across letter layouts'
    assert set(lt.TEMPLATES) == set(ll.LAYOUTS)


def test_statement_and_transcript_use_distinct_layouts():
    # These engines already ship genuinely distinct per-design layouts (not
    # recolours): each design is its own render function.
    from utils import sor_templates, transcript_templates
    for mod in (sor_templates, transcript_templates):
        fns = [v['render'] for v in mod.TEMPLATES.values()]
        assert len(set(id(f) for f in fns)) == len(fns)
        assert len(mod.TEMPLATES) >= 7


def test_every_certificate_type_renders_single_page_all_collections():
    types = [dt for dt in cat.designed_types() if cat.engine(dt) == cat.ENGINE_CERTIFICATE]
    assert types
    for dt in types:
        for key in ce.TEMPLATES:
            buf = gd.preview_document(dt, key)
            doc = fitz.open(stream=buf.read(), filetype='pdf')
            try:
                assert doc.page_count == 1, f'{dt}/{key} = {doc.page_count} pages'
            finally:
                doc.close()


def test_certificate_content_is_data_driven_by_doc_type():
    school = {'name': 'Bright Future Academy'}
    base = ce.sample_ctx(school)

    def title_for(dt):
        ctx = dict(base, doc_type=dt)
        return ce._content(ctx)['title']

    assert title_for('graduation') == 'Graduation Certificate'
    assert 'Character' in title_for('character_cert')
    assert 'Best Graduating' in title_for('best_graduating')


def test_pronouns_follow_gender():
    school = {'name': 'X'}
    ctx = ce.sample_ctx(school)
    ctx['doc_type'] = 'character_cert'

    class S:
        full_name = 'John Doe'
        gender = 'Male'
        student_id = 'X1'
    ctx['student'] = S()
    body = ' '.join(ce._content(ctx)['body'])
    assert 'his time' in body and 'her time' not in body


def test_branding_overrides_collection_palette():
    base = doc_themes.resolve('classic')
    over = doc_themes.resolve('classic', {'primary_color': '#123456'})
    assert over['primary'] == '#123456'
    assert base['primary'] != '#123456'


def test_designed_docs_membership_via_catalog():
    assert 'graduation' in gd.DESIGNED_DOCS
    assert 'merit_award' in gd.DESIGNED_DOCS
    assert 'admission' in gd.DESIGNED_DOCS
    assert 'nonexistent_type' not in gd.DESIGNED_DOCS


def test_letter_family_registered():
    letters = [dt for dt in cat.designed_types() if cat.engine(dt) == cat.ENGINE_LETTER]
    for dt in ('admission', 'acceptance', 'transfer', 'withdrawal', 'confirmation',
               'recommendation', 'university_recommendation', 'scholarship_recommendation',
               'employment_recommendation', 'reference'):
        assert dt in letters, dt


def test_every_letter_type_renders_single_page():
    letters = [dt for dt in cat.designed_types() if cat.engine(dt) == cat.ENGINE_LETTER]
    assert letters
    for dt in letters:
        for key in ('classic', 'executive', 'premium'):
            buf = gd.preview_document(dt, key)
            doc = fitz.open(stream=buf.read(), filetype='pdf')
            try:
                assert doc.page_count == 1, f'{dt}/{key} = {doc.page_count} pages'
            finally:
                doc.close()


def test_letters_are_portrait_certificates_are_landscape():
    assert lt.is_landscape('classic') is False
    assert ce.is_landscape('classic') is True


def test_letter_content_data_driven_and_pronoun_aware():
    ctx = lt.sample_ctx({'name': 'Bright Future Academy'})
    ctx['doc_type'] = 'employment_recommendation'
    ctx['academic'] = {'cumulative': 78.5}

    class S:
        full_name = 'John Doe'
        gender = 'Male'
        student_id = 'ADM-1'
    ctx['student'] = S()
    c = lt._content(ctx)
    assert c['title'] == 'Employment Recommendation'
    body = ' '.join(c['body'])
    assert '78.5%' in body and ' he ' in f' {body} '


def test_clearance_certificates_registered_as_certificate_engine():
    for dt in ('fee_clearance', 'graduation_clearance'):
        assert cat.engine(dt) == cat.ENGINE_CERTIFICATE
        assert cat.category(dt) == 'Administrative'


# --- Phase 3: branding studio + grouped gallery (route-level) ---------------
def test_gallery_payload_groups_types_and_exposes_branding(app):
    c = _admin(app)
    r = c.get('/promotion/doc-templates?doc_type=transcript',
              headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200
    body = r.get_json()
    # SPA JSON may wrap the section payload; accept either shape.
    payload = body.get('data', body) if isinstance(body, dict) else body
    grouped = payload.get('doc_types_grouped') or []
    cats = [g['category'] for g in grouped]
    assert 'Academic Records' in cats and 'Awards & Recognition' in cats
    assert 'branding' in payload and 'branding_save_url' in payload
    assert len(payload['templates']) == len(gd.list_designs('transcript')) > 0
    # a certificate type offers the full collection library
    r2 = c.get('/promotion/doc-templates?doc_type=graduation',
               headers={'X-Requested-With': 'fetch'})
    body2 = r2.get_json()
    payload2 = body2.get('data', body2) if isinstance(body2, dict) else body2
    assert len(payload2['templates']) == len(ce.TEMPLATES)


# --- Phase 4: document verification audit trail -----------------------------
def _grad_with_doc(app, sid='VER1'):
    from models import db, Student
    with app.app_context():
        s = Student(student_id=sid, first_name='Ver', surname='Ifiable',
                    gender='Female', is_active=True, is_graduated=True,
                    graduate_status='Graduated')
        db.session.add(s); db.session.commit()
        sidn = s.id
    c = _admin(app)
    c.get(f'/promotion/graduates/{sidn}/document/slc')   # issue → creates code
    from models import GraduateDocument
    with app.app_context():
        d = GraduateDocument.query.filter_by(student_id=sidn, doc_type='slc').first()
        return sidn, d.verification_code


def test_public_verify_logs_valid_and_unknown(app):
    from models import DocumentVerification
    sid, code = _grad_with_doc(app, 'VERLOG')
    pub = app.test_client()
    # a genuine scan (code in the path) verifies + is logged as 'valid' / 'qr'
    r = pub.get(f'/verify/{code}')
    assert r.status_code == 200
    # an unknown code is logged as 'not_found'
    pub.get('/verify?code=ZZZ0000000')
    with app.app_context():
        rows = DocumentVerification.query.order_by(DocumentVerification.id).all()
        results = {v.result for v in rows}
        assert 'valid' in results and 'not_found' in results
        valid = [v for v in rows if v.result == 'valid'][0]
        assert valid.source == 'qr' and valid.student_id == sid
        # privacy: a salted hash is stored, never a raw IP
        assert valid.visitor_hash and len(valid.visitor_hash) == 64


def test_revoked_document_logs_revoked_result(app):
    from models import db, GraduateDocument, DocumentVerification
    sid, code = _grad_with_doc(app, 'VERREV')
    with app.app_context():
        d = GraduateDocument.query.filter_by(student_id=sid, doc_type='slc').first()
        d.revoked = True
        db.session.commit()
    app.test_client().get(f'/verify/{code}')
    with app.app_context():
        assert DocumentVerification.query.filter_by(result='revoked', student_id=sid).count() == 1


def test_admin_verifications_log_and_profile_count(app):
    sid, code = _grad_with_doc(app, 'VERADMIN')
    pub = app.test_client()
    pub.get(f'/verify/{code}')
    pub.get(f'/verify/{code}')
    c = _admin(app)
    r = c.get('/promotion/graduates/documents/verifications',
              headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200
    body = r.get_json()
    payload = body.get('data', body) if isinstance(body, dict) else body
    assert payload['summary']['valid'] >= 2
    assert any(row['result'] == 'valid' for row in payload['rows'])
    # the per-document verified count reaches the graduate profile
    rp = c.get(f'/promotion/graduates/{sid}', headers={'X-Requested-With': 'fetch'})
    pp = rp.get_json()
    ppd = pp.get('data', pp) if isinstance(pp, dict) else pp
    slc = [d for d in ppd['documents'] if d['type'] == 'slc'][0]
    assert slc['verify_count'] >= 2


def test_branding_save_roundtrip(app):
    from utils.school import document_branding
    c = _admin(app)
    tok = _csrf(c)
    r = c.post('/promotion/doc-templates/branding',
               data={'primary_color': '#123456', 'accent_color': '#abcdef',
                     'secondary_color': 'not-a-color', 'motto': 'Test Motto',
                     'verify_enabled': '0', '_csrf_token': tok},
               headers={'X-Requested-With': 'fetch'})
    assert r.status_code == 200
    with app.app_context():
        br = document_branding()
        assert br['primary_color'] == '#123456'
        assert br['accent_color'] == '#abcdef'
        assert br['secondary_color'] == ''          # invalid rejected
        assert br['motto'] == 'Test Motto'
        assert br['verify_enabled'] is False
    # the override reaches the theme
    with app.app_context():
        theme = doc_themes.resolve('classic', document_branding())
        assert theme['primary'] == '#123456'
