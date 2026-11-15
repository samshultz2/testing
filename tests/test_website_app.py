"""Website Builder app: the JSON screens and the save bugs fixed with the
redesign (colours that never cleared, unknown/reserved page addresses,
section saves without JSON, misleading upload messages)."""
import io

from models import db, SiteSettings, SitePage
from tests.conftest import auth_csrf
from tests.test_website_builder import _publish, _admin, _png

FETCH = {'X-Requested-With': 'fetch'}


def _home(app):
    with app.app_context():
        pg = SitePage.query.filter_by(slug='home').first()
        return pg.id, [b['type'] for b in pg.blocks]


def test_every_screen_returns_app_data(app):
    _publish(app)
    c = _admin(app)
    pid, _ = _home(app)
    for url, page in (('/website/', 'home'), (f'/website/pages/{pid}', 'page'), ('/website/news', 'news'),
                      ('/website/media', 'media'), ('/website/assignments', 'assignments'),
                      ('/website/analytics', 'analytics')):
        r = c.get(url)
        assert r.status_code == 200 and 'id="web-app"' in r.get_data(as_text=True)
        d = c.get(url, headers=FETCH).get_json()
        assert d['page'] == page and d['nav']['home'] == '/website/'
    d = c.get(f'/website/pages/{pid}', headers=FETCH).get_json()
    hero = next(b for b in d['blocks'] if b['type'] == 'hero')
    kinds = {f['key']: f['kind'] for f in hero['fields']}
    assert kinds['heading'] == 'text' and kinds['image'] == 'image' and kinds['slides'] == 'images'
    assert kinds['primary_href'] == 'link'
    about = next(b for b in d['blocks'] if b['type'] == 'about')
    assert {f['key']: f['kind'] for f in about['fields']}['points'] == 'strings'


def test_choosing_a_preset_without_custom_colours_uses_its_colours(app):
    """A colour picker always posts a value, so colours saved once used to
    stick forever and a new preset kept the old colours."""
    _publish(app)
    c = _admin(app)
    tok = auth_csrf(c)
    c.post('/website/theme', data={'_csrf_token': tok, 'preset': 'emerald', 'custom_colors': 'on',
                                   'primary': '#123456', 'accent': '#abcdef'})
    with app.app_context():
        assert SiteSettings.get().theme['primary'] == '#123456'
    c.post('/website/theme', data={'_csrf_token': tok, 'preset': 'coral', 'custom_colors': 'off',
                                   'primary': '#123456', 'accent': '#abcdef'})
    with app.app_context():
        t = SiteSettings.get().theme
        assert t['preset'] == 'coral' and 'primary' not in t and 'accent' not in t
    html = app.test_client().get('/site/').get_data(as_text=True)
    assert '#e2574c' in html                       # coral's own colour is live
    # junk colour values are never stored
    c.post('/website/theme', data={'_csrf_token': tok, 'preset': 'coral', 'custom_colors': 'on',
                                   'primary': 'red;}body{', 'accent': '#abcdef'})
    with app.app_context():
        t = SiteSettings.get().theme
        assert 'primary' not in t and t['accent'] == '#abcdef'


def test_section_save_validates_and_persists(app):
    _publish(app)
    c = _admin(app)
    pid, types = _home(app)
    i = types.index('values')
    tok = auth_csrf(c)
    hdr = dict(FETCH, **{'X-CSRFToken': tok})
    items = [{'title': 'Vision', 'body': 'To lead.'}, {'title': 'Motto', 'body': 'Learn'}]
    r = c.post(f'/website/pages/{pid}/block/{i}/save', headers=hdr,
               json={'expect': 'values', 'variant': 'stacked', 'enabled': False,
                     'props': {'heading': 'What we stand for', 'items': items, 'evil': 'x'}})
    j = r.get_json()
    assert j['ok'], j
    with app.app_context():
        blk = SitePage.query.get(pid).blocks[i]
        assert blk['props']['heading'] == 'What we stand for' and blk['props']['items'] == items
        assert 'evil' not in blk['props'] and blk['variant'] == 'stacked' and blk['enabled'] is False
    # wrong shape is refused, nothing changes
    r = c.post(f'/website/pages/{pid}/block/{i}/save', headers=hdr,
               json={'expect': 'values', 'props': {'heading': ['not', 'text']}})
    assert r.status_code == 400 and not r.get_json()['ok']
    # the section moved in another tab → refused with fresh data
    r = c.post(f'/website/pages/{pid}/block/{i}/save', headers=hdr, json={'expect': 'hero', 'props': {}})
    assert r.status_code == 409 and r.get_json()['stale'] and r.get_json()['page']['blocks']


def test_new_sections_go_above_the_footer(app):
    _publish(app)
    c = _admin(app)
    pid, types = _home(app)
    assert types[-1] == 'footer'
    r = c.post(f'/website/pages/{pid}/block/add', headers=FETCH, data={'_csrf_token': auth_csrf(c), 'type': 'faq'})
    j = r.get_json()
    assert j['ok'] and j['page']['blocks'][-1]['type'] == 'footer'
    assert j['page']['blocks'][j['selected']]['type'] == 'faq'


def test_pages_reserved_address_slug_edit_and_menu_order(app):
    _publish(app)
    c = _admin(app)
    tok = auth_csrf(c)
    # "apply" belongs to the admissions form; a page there could never be opened
    r = c.post('/website/pages/new', headers=FETCH, data={'_csrf_token': tok, 'title': 'Apply'})
    assert r.status_code == 400
    r = c.post('/website/pages/new', headers=FETCH, data={'_csrf_token': tok, 'title': 'Our Fees'})
    assert r.get_json()['ok']
    r2 = c.post('/website/pages/new', headers=FETCH, data={'_csrf_token': tok, 'title': 'Gallery'})
    assert r2.get_json()['ok']
    with app.app_context():
        fees = SitePage.query.filter_by(slug='our-fees').first()
        gal = SitePage.query.filter_by(slug='gallery').first()
        home = SitePage.query.filter_by(slug='home').first()
        fid, gid, hid = fees.id, gal.id, home.id
    r = c.post(f'/website/pages/{fid}/meta', headers=FETCH,
               data={'_csrf_token': tok, 'title': 'Fees', 'slug': 'School Fees', 'show_in_nav': 'on', 'is_published': 'on'})
    assert r.get_json()['ok'] and r.get_json()['page']['pg']['slug'] == 'school-fees'
    r = c.post(f'/website/pages/{fid}/meta', headers=FETCH, data={'_csrf_token': tok, 'title': 'Fees', 'slug': 'gallery'})
    assert r.status_code == 400
    assert app.test_client().get('/site/school-fees').status_code == 200
    c.post('/website/pages/reorder', headers=FETCH, data={'_csrf_token': tok, 'order': f'{hid},{gid},{fid}'})
    with app.app_context():
        assert db.session.get(SitePage, gid).nav_order < db.session.get(SitePage, fid).nav_order
    # the home page can't be hidden
    c.post(f'/website/pages/{hid}/meta', headers=FETCH, data={'_csrf_token': tok, 'title': 'Home'})
    with app.app_context():
        assert db.session.get(SitePage, hid).is_published is True


def test_upload_reports_what_really_happened(app):
    _publish(app)
    c = _admin(app)
    tok = auth_csrf(c)
    r = c.post('/website/media/upload', headers=FETCH, content_type='multipart/form-data',
               data={'_csrf_token': tok, 'file': [(_png(300, 200), 'a.png'), (io.BytesIO(b'nope'), 'b.txt')]})
    j = r.get_json()
    assert j['ok'] and len(j['items']) == 1 and len(j['errors']) == 1
    r = c.post('/website/media/upload', headers=FETCH, content_type='multipart/form-data',
               data={'_csrf_token': tok, 'file': (io.BytesIO(b'nope'), 'b.txt')})
    assert r.status_code == 400 and not r.get_json()['ok']
    # the plain form no longer claims success when every file was rejected
    c.post('/website/media/upload', content_type='multipart/form-data',
           data={'_csrf_token': tok, 'file': (io.BytesIO(b'nope'), 'b.txt')})
    with c.session_transaction() as s:
        msgs = [m for _, m in s.get('_flashes', [])]
    assert not any('uploaded' in m for m in msgs)


def test_publishing_a_post_without_a_date_gets_today(app):
    from models import NewsPost
    _publish(app)
    c = _admin(app)
    tok = auth_csrf(c)
    r = c.post('/website/news/new', headers=FETCH, data={'_csrf_token': tok})
    with app.app_context():
        p = NewsPost.query.order_by(NewsPost.id.desc()).first()
        p.published_at = None; db.session.commit(); pid = p.id
    r = c.post(f'/website/news/{pid}/save', headers=FETCH,
               data={'_csrf_token': tok, 'title': 'Prize Day', 'body': 'Hello', 'is_published': 'on', 'cover_url': ''})
    j = r.get_json()
    assert j['ok'] and j['post']['published'] and j['post']['date']
