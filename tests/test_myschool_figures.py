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
    monkeypatch.setattr(myschool_figures, '_browser_html', lambda url: None)
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
