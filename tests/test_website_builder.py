"""Website Builder: data model, tenant-safe public rendering, SEO, PII safety,
and the admin editor. The PII test is the important one — the public site must
never expose a student/parent/staff record."""
from config import Config
from models import db, SiteSettings, SitePage, Student, Branch, SchoolSettings
from tests.conftest import login_token, auth_csrf
from utils.site_blocks import default_home_blocks


def _publish(app, preset='emerald'):
    with app.app_context():
        from utils.finance_ledger import ensure_tables
        ensure_tables()
        if not SitePage.query.filter_by(slug='home').first():
            db.session.add(SitePage(slug='home', title='Home', blocks=default_home_blocks(), nav_order=0))
        SchoolSettings.set('school_name', 'Testville College', 'string')
        s = SiteSettings.get(); s.published = True; s.theme = {'preset': preset}
        db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


# --- model -----------------------------------------------------------------
def test_ensure_tables_creates_site_tables(app):
    from sqlalchemy import inspect
    from utils.finance_ledger import ensure_tables
    with app.app_context():
        ensure_tables()
        names = inspect(db.engine).get_table_names()
        assert 'site_settings' in names and 'site_pages' in names


def test_settings_singleton(app):
    with app.app_context():
        a = SiteSettings.get(); b = SiteSettings.get()
        assert a.id == b.id


# --- public rendering + gates ----------------------------------------------
def test_draft_site_is_404_for_public(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        db.session.add(SitePage(slug='home', title='Home', blocks=default_home_blocks()))
        db.session.commit()   # settings.published defaults False
    assert app.test_client().get('/site/').status_code == 404


def test_published_site_renders_with_seo(app):
    _publish(app)
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'Testville College' in html                       # single source of truth
    assert '"@type": "School"' in html                       # JSON-LD structured data
    assert 'rel="canonical"' in html and 'og:title' in html  # SEO/social
    assert 'wb-nav' in html and 'wb-footer' in html          # nav + footer blocks


def test_theme_changes_output(app):
    _publish(app, preset='midnight')
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert '#4f46e5' in html                                  # midnight primary applied
    with app.app_context():
        SiteSettings.get().theme = {'preset': 'coral'}; db.session.commit()
    html2 = app.test_client().get('/site/').get_data(as_text=True)
    assert '#e2574c' in html2 and '#4f46e5' not in html2      # genuinely different


def test_sitemap_and_robots(app):
    _publish(app)
    c = app.test_client()
    sm = c.get('/site/sitemap.xml')
    assert sm.status_code == 200 and 'urlset' in sm.get_data(as_text=True)
    rb = c.get('/site/robots.txt').get_data(as_text=True)
    assert 'Sitemap:' in rb and 'Allow: /site' in rb


def test_missing_page_404(app):
    _publish(app)
    assert app.test_client().get('/site/does-not-exist').status_code == 404


# --- the critical one: no PII ever reaches the public site -----------------
def test_public_site_never_exposes_student_pii(app):
    _publish(app)
    with app.app_context():
        st = Student(student_id=Student.generate_student_id(), first_name='Topsecret',
                     surname='Learner', gender='Male', is_active=True,
                     branch_id=Branch.get_default().id)
        db.session.add(st); db.session.commit()
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'Topsecret' not in html and 'Learner' not in html


# --- admin editor ----------------------------------------------------------
def test_admin_can_manage_site(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
    c = _admin(app)
    # opening the builder seeds a home page and renders
    r = c.get('/website/')
    assert r.status_code == 200 and 'Website Builder' in r.get_data(as_text=True)
    with app.app_context():
        home = SitePage.query.filter_by(slug='home').first()
        assert home is not None
        n_before = len(home.blocks)
        pid = home.id
    tok = auth_csrf(c)
    # add a testimonials block
    c.post(f'/website/pages/{pid}/block/add', data={'type': 'testimonials', '_csrf_token': tok})
    with app.app_context():
        assert len(SitePage.query.get(pid).blocks) == n_before + 1
    # publish
    c.post('/website/publish', data={'published': 'on', '_csrf_token': tok})
    with app.app_context():
        assert SiteSettings.get().published is True


def _png(w=2000, h=1200, color=(30, 80, 160)):
    import io
    from PIL import Image
    buf = io.BytesIO(); Image.new('RGB', (w, h), color).save(buf, 'JPEG'); buf.seek(0)
    return buf


# --- media (images stored in the tenant DB) --------------------------------
def test_media_upload_downscales_and_stores(app):
    from models import SiteMedia
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
    c = _admin(app); c.get('/website/')
    c.post('/website/media/upload',
           data={'file': (_png(2000, 1200), 'hero.jpg'), '_csrf_token': auth_csrf(c)},
           content_type='multipart/form-data')
    with app.app_context():
        m = SiteMedia.query.first()
        assert m is not None
        assert m.width == 1600 and m.mime == 'image/jpeg'    # downscaled from 2000w
        assert 0 < (m.bytes or 0) < 500_000                  # optimised small


def test_media_upload_rejects_non_image(app):
    import io
    from models import SiteMedia
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
    c = _admin(app); c.get('/website/')
    with app.app_context():
        before = SiteMedia.query.count()
    c.post('/website/media/upload',
           data={'file': (io.BytesIO(b'not an image'), 'x.txt'), '_csrf_token': auth_csrf(c)},
           content_type='multipart/form-data')
    with app.app_context():
        assert SiteMedia.query.count() == before        # rejected, nothing stored


def test_media_serving_is_publish_gated_and_cached(app):
    from models import SiteMedia
    _publish(app)                       # published site
    c = _admin(app); c.get('/website/')
    c.post('/website/media/upload',
           data={'file': (_png(400, 300), 'p.jpg'), '_csrf_token': auth_csrf(c)},
           content_type='multipart/form-data')
    with app.app_context():
        mid = SiteMedia.query.first().id
    url = f'/site/media/{mid}'
    # published -> anonymous can fetch, with a long cache + ETag
    anon = app.test_client()
    r = anon.get(url)
    assert r.status_code == 200 and r.mimetype == 'image/jpeg'
    assert 'max-age=31536000' in r.headers.get('Cache-Control', '')
    assert anon.get(url, headers={'If-None-Match': r.headers['ETag']}).status_code == 304
    # unpublish -> anonymous is 404, but admin preview still works
    with app.app_context():
        SiteSettings.get().published = False; db.session.commit()
    assert app.test_client().get(url).status_code == 404
    assert c.get(url).status_code == 200


def test_uploaded_image_renders_in_hero(app):
    from models import SiteMedia, SitePage
    from sqlalchemy.orm.attributes import flag_modified
    _publish(app)
    c = _admin(app); c.get('/website/')
    c.post('/website/media/upload',
           data={'file': (_png(1000, 700), 'bg.jpg'), '_csrf_token': auth_csrf(c)},
           content_type='multipart/form-data')
    with app.app_context():
        url = f'/site/media/{SiteMedia.query.first().id}'
        pg = SitePage.query.filter_by(slug='home').first()
        blocks = list(pg.blocks)
        blocks[1]['variant'] = 'image-bg'; blocks[1]['props']['bg_image'] = url
        pg.blocks = blocks; flag_modified(pg, 'blocks'); db.session.commit()
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'wb-hero image-bg' in html and url in html


def test_admin_add_block_rejects_unknown_type(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
    c = _admin(app)
    c.get('/website/')
    with app.app_context():
        pid = SitePage.query.filter_by(slug='home').first().id
    r = c.post(f'/website/pages/{pid}/block/add', data={'type': 'evil', '_csrf_token': auth_csrf(c)})
    assert r.status_code == 400
