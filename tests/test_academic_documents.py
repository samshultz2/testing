"""Academic Documents & Publishing system — catalogue, collections, certificate
engine, and the shared render pipeline for the new document types."""
import fitz
import pytest

from utils import document_catalog as cat
from utils import (doc_themes, certificate_templates as ce, letter_templates as lt,
                   graduate_docs as gd)


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
    # A deep collection library so every document type has many templates.
    assert len(doc_themes.COLLECTIONS) >= 20
    assert len(ce.TEMPLATES) == len(doc_themes.COLLECTIONS)
    assert ce.DEFAULT_TEMPLATE in ce.TEMPLATES


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
