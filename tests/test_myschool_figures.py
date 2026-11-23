"""Fetch missing diagrams from myschool.ng: find the question's page (by its
myschool number, or by matching its wording in the subject-year listing),
read the figure, save a copy and attach it. All offline via monkeypatch."""
import re
import uuid

from config import Config
from tests.conftest import login_token
from tests.test_myschool import _img_fixture


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c):
    return re.search(r'name="csrf-token" content="([0-9a-f]+)"',
                     c.get('/students').get_data(as_text=True)).group(1)


STEM = 'In the figure, AB is parallel to CD then x + y + z is'
IMG = '<img src="https://myschool.ng/storage/classroom/fig-abcd.png">'


def _fake_site(monkeypatch, slug, with_img=True, listing_text=True):
    from utils import myschool as ms
    from utils import mock_figures, myschool_figures
    myschool_figures._CACHE.clear()
    calls = []

    def fetch(url, session, **k):
        calls.append(url)
        if re.search(rf'/classroom/{slug}\?', url):
            if 'page=1' not in url:
                return '<div>no more</div>'
            other = '<div class="q"><p>Which is a vector quantity among these options?</p><a href="/classroom/%s/700?exam_type=jamb&exam_year=2014">View</a></div>' % slug
            mine = ('<div class="q"><p>%s</p><a href="/classroom/%s/777?exam_type=jamb&exam_year=2014">View</a></div>'
                    % (STEM if listing_text else 'Question 2', slug))
            return '<main>' + other + mine + '</main>'
        if '/777' in url:
            return _img_fixture(STEM, IMG if with_img else '')
        if '/700' in url:
            return _img_fixture('Which is a vector quantity among these options?', '')
        return None
    monkeypatch.setattr(ms, 'fetch', fetch)
    monkeypatch.setattr(mock_figures, 'save_copy', lambda url: '/static/img/logo-mark.svg' if 'fig-abcd' in url else None)
    monkeypatch.setattr(myschool_figures, '_browser', lambda url, want_png=False: (None, None))
    return calls


def _question(app, **kw):
    from models import db, Subject, MockJAMBQuestion
    with app.app_context():
        s = Subject(name='Mathematics' if not Subject.query.filter_by(name='Mathematics').first()
                    else 'Maths ' + uuid.uuid4().hex[:4], is_active=True)
        db.session.add(s); db.session.flush()
        from utils import myschool as ms
        q = MockJAMBQuestion(mock_exam_id=None, subject_id=s.id, question_text=STEM, option_a='185°',
                             option_b='200°', option_c='270°', option_d='360°', correct_option='D', marks=1,
                             exam_body='JAMB', exam_year='2014', needs_image=True, **kw)
        db.session.add(q); db.session.commit()
        return q.id, ms.subject_slug(s.name)


def test_pasted_question_matched_by_wording_and_attached(app, monkeypatch):
    qid, slug = _question(app, source='paste')
    _fake_site(monkeypatch, slug)
    c = _admin(app)
    r = c.post(f'/mock-jamb/bank/question/{qid}/fetch-figure', data={'_csrf_token': _csrf(c)})
    out = r.get_json()
    assert out['status'] == 'attached' and out['url'].split('?')[0].endswith('/777')
    from models import db, MockJAMBQuestion
    with app.app_context():
        q = db.session.get(MockJAMBQuestion, qid)
        assert q.image_url == '/static/img/logo-mark.svg' and q.needs_image is False
        assert q.source == 'myschool' and q.source_ref == '777'      # links to its page from now on


def test_listing_without_text_falls_back_to_opening_each_question(app, monkeypatch):
    qid, slug = _question(app, source='paste')
    calls = _fake_site(monkeypatch, slug, listing_text=False)
    c = _admin(app)
    out = c.post(f'/mock-jamb/bank/question/{qid}/fetch-figure', data={'_csrf_token': _csrf(c)}).get_json()
    assert out['status'] == 'attached'
    assert any('/700' in u for u in calls) and any('/777' in u for u in calls)


def test_known_myschool_number_and_no_diagram(app, monkeypatch):
    qid, slug = _question(app, source='myschool', source_ref='777')
    calls = _fake_site(monkeypatch, slug, with_img=False)
    c = _admin(app)
    out = c.post(f'/mock-jamb/bank/question/{qid}/fetch-figure', data={'_csrf_token': _csrf(c)}).get_json()
    assert out['status'] == 'no_image' and out['url'].split('?')[0].endswith('/777')
    assert not any('page=' in u for u in calls)                      # went straight to the page
    from models import db, MockJAMBQuestion
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid).needs_image is True


def test_no_year_is_not_found(app, monkeypatch):
    from models import db, MockJAMBQuestion
    qid, slug = _question(app, source='paste')
    with app.app_context():
        db.session.get(MockJAMBQuestion, qid).exam_year = None
        db.session.commit()
    _fake_site(monkeypatch, slug)
    c = _admin(app)
    out = c.post(f'/mock-jamb/bank/question/{qid}/fetch-figure', data={'_csrf_token': _csrf(c)}).get_json()
    assert out['status'] == 'not_found' and 'year' in out['message']
    html = c.get('/mock-jamb/bank/needs-images').get_data(as_text=True)
    assert 'Fetch from myschool' in html


def _card(stem_block, between='', options_extra=''):
    return f"""
    <div class="card">
      <div class="qhead">{stem_block}</div>
      {between}
      <div class="opts">
        <div class="prevent-copy"><span class="uppercase">a</span><p>1</p>{options_extra}</div>
        <div class="prevent-copy"><span class="uppercase">b</span><p>2</p></div>
        <div class="prevent-copy"><span class="uppercase">c</span><p>3</p></div>
        <div class="prevent-copy"><span class="uppercase">d</span><p>4</p></div>
      </div>
      <div class="ans">Correct Option <span class="uppercase">a</span></div>
    </div>"""


def test_figure_found_in_a_sibling_block_not_in_options():
    from utils import myschool as ms
    # the diagram sits in its own block between the stem and the options
    p = ms.parse_detail(_card('<h1>In the figure, find x.</h1>',
                              between='<div class="fig"><img src="/storage/classroom/q55.png"></div>'))
    assert p['image_url'] == 'https://myschool.ng/storage/classroom/q55.png'
    # a picture inside an option row is a picture option, not the question's figure
    p = ms.parse_detail(_card('<h1>Which shape is a square?</h1>',
                              options_extra='<img src="/storage/classroom/opt-a.png">'))
    assert p['image_url'] is None and 'option' in p['image_debug']
    # a figure whose file name contains a "reject" word is still a figure
    p = ms.parse_detail(_card('<h1>The structure labelled X is</h1><img src="https://myschool.ng/storage/classroom/flagellum.png">'))
    assert p['image_url'].endswith('flagellum.png')
    # extension-less image-service path
    p = ms.parse_detail(_card('<h1>Use the graph shown.</h1><img src="/_ipx/w_600/storage/classroom/g1">'))
    assert p['image_url'] == 'https://myschool.ng/_ipx/w_600/storage/classroom/g1'


def test_inline_svg_diagram_is_kept():
    from utils import myschool as ms
    svg = ('<svg width="300" height="200" viewBox="0 0 300 200"><line x1="0" y1="0" x2="300" y2="200"/>'
           '<script>alert(1)</script><circle cx="50" cy="50" r="20" onclick="x()"/></svg>')
    p = ms.parse_detail(_card('<h1>In the diagram, find the angle.</h1>' + svg))
    assert p['image_url'] is None and p['image_svg'] and '<line' in p['image_svg']
    icon = '<svg class="icon" width="16" height="16"><path d="M0 0"/></svg>'
    assert ms.parse_detail(_card('<h1>Plain question?</h1>' + icon))['image_svg'] is None


def test_svg_saved_and_screenshot_fallback(app, monkeypatch):
    from models import db, MockJAMBQuestion
    from utils import myschool as ms
    from utils import mock_figures, myschool_figures
    with app.app_context():
        url = mock_figures.save_svg('<svg width="10" height="10"><script>bad()</script><rect onload="x()" width="5" height="5"/></svg>')
        import os
        from flask import current_app
        body = open(os.path.join(current_app.root_path, url.lstrip('/'))).read()
        assert url.endswith('.svg') and '<script' not in body and 'onload' not in body and 'xmlns=' in body
    # no picture in the page HTML, but the browser can screenshot the drawn figure
    qid, slug = _question(app, source='myschool', source_ref='777')
    _fake_site(monkeypatch, slug, with_img=False)
    monkeypatch.setattr(myschool_figures, '_browser', lambda url, want_png=False: ('<html></html>', b'PNGDATA'))
    monkeypatch.setattr(mock_figures, 'save_png_bytes', lambda b: '/static/img/logo-mark.svg' if b == b'PNGDATA' else None)
    c = _admin(app)
    out = c.post(f'/mock-jamb/bank/question/{qid}/fetch-figure', data={'_csrf_token': _csrf(c)}).get_json()
    assert out['status'] == 'attached' and 'screenshot' in out['message']
    with app.app_context():
        assert db.session.get(MockJAMBQuestion, qid).image_url == '/static/img/logo-mark.svg'


def test_extensionless_and_picture_source_figures():
    from utils import myschool as ms
    p = ms.parse_detail(_card('<h1>Use the diagram above to answer this question</h1>',
                              between='<div><img src="https://cdn.example.net/q/31331" width="600" height="400"></div>'))
    assert p['image_url'] == 'https://cdn.example.net/q/31331'
    p = ms.parse_detail(_card('<h1>Study the figure.</h1><picture><source srcset="/storage/classroom/f1.webp 1x">'
                              '<img src="data:image/gif;base64,R0lGOD"></picture>'))
    assert p['image_url'] == 'https://myschool.ng/storage/classroom/f1.webp'
    # tiny icons and site logos are still ignored
    p = ms.parse_detail(_card('<h1>Plain question?</h1><img src="https://x.net/a/b" width="16" height="16">'
                              '<img src="https://x.net/myschool-logo.png">'))
    assert p['image_url'] is None
    from utils.myschool import _rejected
    assert not _rejected('https://myschool.ng/uploads/flagellum.png') and not _rejected('/img/catalogue.jpg')
    assert _rejected('/img/site-logo.png') and _rejected('https://x.net/icons/a.png')
