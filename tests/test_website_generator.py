"""Website Builder — one-click site generator.

Covers: the generator builds a full multi-page site from the school's identity;
two different schools get genuinely different designs; the same school is
deterministic; a 'salt' yields a different look; generated copy uses the school's
name (single source of truth); every generated page renders publicly without
error; and the admin route builds + replaces existing pages behind a login.
"""
from config import Config
from models import db, SiteSettings, SitePage, SchoolSettings
from tests.conftest import login_token, auth_csrf
from utils import site_generator


def _named(app, name):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        SchoolSettings.set('school_name', name, 'string')
        db.session.commit()


def _fingerprint(app):
    with app.app_context():
        s = SiteSettings.get()
        home = SitePage.query.filter_by(slug='home').first()
        return (s.theme.get('preset'),
                tuple((b['type'], b['variant']) for b in home.blocks))


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


# --- generation ------------------------------------------------------------
def test_generates_full_multipage_site(app):
    _named(app, 'Greenfield Academy')
    with app.app_context():
        n = site_generator.generate()
        slugs = {p.slug for p in SitePage.query.all()}
    assert n == 5
    assert {'home', 'about', 'academics', 'admissions', 'contact'} <= slugs
    with app.app_context():
        home = SitePage.query.filter_by(slug='home').first()
        types = [b['type'] for b in home.blocks]
        assert types[0] in ('topbar', 'nav') and 'nav' in types
        assert types[-1] == 'footer' and 'hero' in types


def test_two_schools_get_different_designs(app):
    _named(app, 'Greenfield Academy');
    with app.app_context():
        site_generator.generate()
    fp_a = _fingerprint(app)
    _named(app, 'Sunrise International College')
    with app.app_context():
        site_generator.generate()
    fp_b = _fingerprint(app)
    assert fp_a != fp_b            # genuinely different, not one shared template


def test_same_school_is_deterministic(app):
    _named(app, 'Riverside Grammar')
    with app.app_context():
        site_generator.generate()
    fp1 = _fingerprint(app)
    with app.app_context():
        site_generator.generate()
    fp2 = _fingerprint(app)
    assert fp1 == fp2


def test_salt_changes_the_look(app):
    _named(app, 'Riverside Grammar')
    with app.app_context():
        site_generator.generate(salt='')
    base = _fingerprint(app)
    with app.app_context():
        site_generator.generate(salt='v2-xyz')
    other = _fingerprint(app)
    assert base != other           # a different variation


def test_copy_uses_school_name(app):
    _named(app, 'Peculiar Heights School')
    with app.app_context():
        site_generator.generate()
        home = SitePage.query.filter_by(slug='home').first()
        hero = next(b for b in home.blocks if b['type'] == 'hero')
        assert hero['props']['heading'] == 'Peculiar Heights School'
        assert SiteSettings.get().seo_title.startswith('Peculiar Heights School')


def test_generated_site_is_image_rich(app):
    _named(app, 'Greenfield Academy')
    with app.app_context():
        site_generator.generate()
        home = SitePage.query.filter_by(slug='home').first()
        hero = next(b for b in home.blocks if b['type'] == 'hero')
        # hero uses an image-bearing variant with a real image URL
        assert hero['variant'] in ('image-bg', 'split', 'image-right')
        assert (hero['props'].get('bg_image') or hero['props'].get('image'))
        # several sections carry imagery (about photo, gallery, cta bg…)
        with_images = [b for b in home.blocks
                       if b['props'].get('image') or b['props'].get('bg_image') or b['props'].get('images')]
        assert len(with_images) >= 3
        gallery = next((b for b in home.blocks if b['type'] == 'gallery'), None)
        if gallery:
            assert len(gallery['props'].get('images') or []) >= 3


def test_two_schools_get_different_photos(app):
    from models import SiteMedia
    _named(app, 'Greenfield Academy')
    with app.app_context():
        SiteMedia.query.delete(); db.session.commit()   # no uploads -> seeded stock path
    with app.app_context():
        site_generator.generate()
        a = next(b for b in SitePage.query.filter_by(slug='home').first().blocks
                 if b['type'] == 'hero')['props']
        a_img = a.get('bg_image') or a.get('image')
    _named(app, 'Sunrise International College')
    with app.app_context():
        site_generator.generate()
        b = next(bl for bl in SitePage.query.filter_by(slug='home').first().blocks
                 if bl['type'] == 'hero')['props']
        b_img = b.get('bg_image') or b.get('image')
    assert a_img and b_img and a_img != b_img


def test_stock_module_is_deterministic_and_distinct():
    from utils import site_stock
    assert site_stock.pick('Greenfield', 'hero') == site_stock.pick('Greenfield', 'hero')
    assert site_stock.pick('Greenfield', 'hero') != site_stock.pick('Sunrise', 'hero')
    assert site_stock.pick('Greenfield', 'hero') != site_stock.pick('Greenfield', 'about')
    assert len(site_stock.gallery('Greenfield', 6)) == 6
    assert len(set(site_stock.gallery('Greenfield', 6))) == 6      # all distinct


def test_generated_pages_allow_stock_images_via_csp(app):
    _named(app, 'Greenfield Academy')
    with app.app_context():
        site_generator.generate()
        SiteSettings.get().published = True
        db.session.commit()
    r = app.test_client().get('/site/')
    csp = r.headers.get('Content-Security-Policy', '')
    img_src = csp.split('img-src')[1].split(';')[0]
    assert 'https:' in img_src                     # external stock photos are allowed


def test_generated_site_uses_professional_fonts(app):
    _named(app, 'Greenfield Academy')
    with app.app_context():
        site_generator.generate()
        SiteSettings.get().published = True
        db.session.commit()
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'fonts.googleapis.com' in html            # a real font pairing is loaded


def test_generated_site_has_genre_sections(app):
    _named(app, 'Greenfield Academy')
    with app.app_context():
        site_generator.generate()
        SiteSettings.get().published = True
        db.session.commit()
        types = [b['type'] for b in SitePage.query.filter_by(slug='home').first().blocks]
    assert 'topbar' in types                          # contact/social bar like real school sites
    assert 'gallery' in types and 'faq' in types or 'logos' in types
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'wb-topbar' in html                         # and it actually renders


def _png(color=(40, 90, 160)):
    import io
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (800, 600), color).save(b, 'JPEG'); b.seek(0)
    return b


def test_generator_prefers_school_gallery_images(app):
    """When the school has uploaded photos, the generated site uses THEM, not
    stock — directly addressing the request that images come from the gallery."""
    _named(app, 'Greenfield Academy')
    c = _admin(app); c.get('/website/')
    for i, col in enumerate([(200, 60, 60), (60, 160, 90), (70, 90, 200)]):
        c.post('/website/media/upload',
               data={'file': (_png(col), f'p{i}.jpg'), '_csrf_token': auth_csrf(c)},
               content_type='multipart/form-data')
    with app.app_context():
        site_generator.generate()
        SiteSettings.get().published = True
        db.session.commit()
        hero = next(b for b in SitePage.query.filter_by(slug='home').first().blocks
                    if b['type'] == 'hero')
        img = hero['props'].get('bg_image') or hero['props'].get('image')
        assert img and img.startswith('/site/media/')       # the school's own upload
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert '/site/media/' in html and 'picsum.photos' not in html


def test_every_generated_page_renders(app):
    _named(app, 'Greenfield Academy')
    with app.app_context():
        site_generator.generate()
        SiteSettings.get().published = True
        db.session.commit()
        slugs = [p.slug for p in SitePage.query.all()]
    c = app.test_client()
    for slug in slugs:
        url = '/site/' if slug == 'home' else f'/site/{slug}'
        assert c.get(url).status_code == 200


# --- admin route -----------------------------------------------------------
def test_admin_generate_replaces_pages(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        SchoolSettings.set('school_name', 'Greenfield Academy', 'string')
        # a stray hand-made page that a rebuild should clear out
        db.session.add(SitePage(slug='old-junk', title='Junk', blocks=[], nav_order=9))
        db.session.commit()
    c = _admin(app); c.get('/website/')
    c.post('/website/generate', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        slugs = {p.slug for p in SitePage.query.all()}
        assert 'old-junk' not in slugs
        assert 'home' in slugs and 'admissions' in slugs


def test_generate_requires_admin(app):
    r = app.test_client().post('/website/generate', data={'_csrf_token': 'x'})
    assert r.status_code in (301, 302, 400, 401, 403)
