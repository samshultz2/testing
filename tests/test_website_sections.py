"""Website Builder — hero slider, staff/leadership, and holiday assignments.

The assignment tests are the important ones: admin uploads PDF/Word documents per
class, students download them from a public page, and everything is gated behind
a published site + the document's own publish flag.
"""
import io

from config import Config
from models import (db, SiteSettings, SitePage, SchoolSettings, HolidayAssignment)
from sqlalchemy.orm.attributes import flag_modified
from tests.conftest import login_token, auth_csrf
from utils.site_blocks import default_home_blocks, block_defaults


def _publish(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        if not SitePage.query.filter_by(slug='home').first():
            db.session.add(SitePage(slug='home', title='Home', blocks=default_home_blocks(), nav_order=0))
        SchoolSettings.set('school_name', 'Testville College', 'string')
        s = SiteSettings.get(); s.published = True; s.theme = {'preset': 'emerald'}
        db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _set_home_block(app, block):
    """Replace the home page's second block with a given block, return nothing."""
    with app.app_context():
        pg = SitePage.query.filter_by(slug='home').first()
        blocks = list(pg.blocks)
        blocks.insert(1, block)
        pg.blocks = blocks; flag_modified(pg, 'blocks'); db.session.commit()


# --- hero slider -----------------------------------------------------------
def test_hero_slider_renders_with_js(app):
    _publish(app)
    hero = block_defaults('hero'); hero['variant'] = 'slider'
    hero['props']['slides'] = ['/site/media/1', '/site/media/2', '/site/media/3']
    _set_home_block(app, hero)
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'data-wb-slider' in html and 'wb-slide' in html
    assert '/site/media/2' in html                       # a slide image is present
    assert 'nonce=' in html                              # slider script carries a CSP nonce


# --- staff / leadership ----------------------------------------------------
def test_staff_section_renders(app):
    _publish(app)
    staff = block_defaults('staff')
    staff['props']['items'] = [{'name': 'Mrs Ada Obi', 'role': 'Principal', 'image': '', 'bio': ''}]
    _set_home_block(app, staff)
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'wb-staff-card' in html and 'Mrs Ada Obi' in html and 'Principal' in html


# --- holiday assignments ---------------------------------------------------
def _pdf(name='hw.pdf'):
    return (io.BytesIO(b'%PDF-1.4 test'), name)


def _upload(c, **over):
    data = {'_csrf_token': auth_csrf(c), 'title': 'First term assignment',
            'session_label': '2024/2025', 'class_id': '', 'file': _pdf()}
    data.update(over)
    return c.post('/website/assignments/upload', data=data, content_type='multipart/form-data')


def test_admin_can_upload_assignment(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        before = HolidayAssignment.query.count()
    c = _admin(app)
    _upload(c, title='JSS1 Maths holiday work')
    with app.app_context():
        assert HolidayAssignment.query.count() == before + 1
        a = HolidayAssignment.query.order_by(HolidayAssignment.id.desc()).first()
        assert a.title == 'JSS1 Maths holiday work' and a.ext == 'pdf' and a.data


def test_assignment_rejects_non_document(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        before = HolidayAssignment.query.count()
    c = _admin(app)
    c.post('/website/assignments/upload',
           data={'_csrf_token': auth_csrf(c), 'title': 'bad', 'class_id': '',
                 'file': (io.BytesIO(b'MZ...'), 'malware.exe')},
           content_type='multipart/form-data')
    with app.app_context():
        assert HolidayAssignment.query.count() == before      # .exe rejected


def test_assignment_requires_title_and_file(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        before = HolidayAssignment.query.count()
    c = _admin(app)
    c.post('/website/assignments/upload',
           data={'_csrf_token': auth_csrf(c), 'title': '', 'class_id': '', 'file': _pdf()},
           content_type='multipart/form-data')
    with app.app_context():
        assert HolidayAssignment.query.count() == before


def test_public_assignments_grouped_and_downloadable(app):
    _publish(app)
    c = _admin(app)
    _upload(c, title='JSS1 English', class_id='')
    with app.app_context():
        SchoolSettings.set('school_name', 'Testville College', 'string')
        a = HolidayAssignment.query.order_by(HolidayAssignment.id.desc()).first()
        a.class_label = 'JSS 1'; db.session.commit()
        aid = a.id
    # place an assignments block on the home page and render
    _set_home_block(app, block_defaults('assignments'))
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert 'JSS 1' in html and 'JSS1 English' in html and f'/site/assignments/{aid}/download' in html
    # public download serves the bytes as an attachment
    r = app.test_client().get(f'/site/assignments/{aid}/download')
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert 'attachment' in r.headers.get('Content-Disposition', '')
    assert r.get_data().startswith(b'%PDF')


def test_assignment_download_gated_by_publish(app):
    _publish(app)
    c = _admin(app)
    _upload(c)
    with app.app_context():
        a = HolidayAssignment.query.order_by(HolidayAssignment.id.desc()).first()
        aid = a.id
    anon = app.test_client()
    assert anon.get(f'/site/assignments/{aid}/download').status_code == 200
    # hide the individual assignment -> public 404, admin can still fetch
    with app.app_context():
        db.session.get(HolidayAssignment, aid).is_published = False; db.session.commit()
    assert anon.get(f'/site/assignments/{aid}/download').status_code == 404
    assert c.get(f'/site/assignments/{aid}/download').status_code == 200
    # unpublish the whole site -> public 404 even though the doc is published
    with app.app_context():
        db.session.get(HolidayAssignment, aid).is_published = True
        SiteSettings.get().published = False; db.session.commit()
    assert anon.get(f'/site/assignments/{aid}/download').status_code == 404


def test_generated_site_has_assignments_page_and_slider_capable(app):
    from utils import site_generator
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        SchoolSettings.set('school_name', 'Slider Academy', 'string'); db.session.commit()
        site_generator.generate()
        slugs = {p.slug for p in SitePage.query.all()}
        assert 'holiday-assignments' in slugs
        home = SitePage.query.filter_by(slug='home').first()
        assert any(b['type'] == 'staff' for b in home.blocks)
        assignments_pg = SitePage.query.filter_by(slug='holiday-assignments').first()
        assert any(b['type'] == 'assignments' for b in assignments_pg.blocks)
