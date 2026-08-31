"""Website Builder — first-party, privacy-friendly analytics.

Covers: a public page view is counted; an admin previewing a draft is NOT
counted; a repeat visit within a day counts as another view but the same unique
visitor; bots are ignored; no cookie is ever set on the public site; the admin
dashboard and CSV export render; the summary aggregates correctly.
"""
from config import Config
from models import (db, SiteSettings, SitePage, SchoolSettings,
                    SiteViewDaily, SiteVisitorDaily)
from tests.conftest import login_token, auth_csrf
from utils.site_blocks import default_home_blocks


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


def _views(app, path='/site/'):
    with app.app_context():
        row = SiteViewDaily.query.filter_by(path=path).first()
        return row.views if row else 0


# --- recording -------------------------------------------------------------
def test_public_view_is_counted(app):
    _publish(app)
    before = _views(app)
    app.test_client().get('/site/')
    assert _views(app) == before + 1


def test_admin_preview_is_not_counted(app):
    _publish(app)
    # unpublish so only an admin can see it — a preview must NOT inflate stats
    with app.app_context():
        SiteSettings.get().published = False; db.session.commit()
    before = _views(app)
    c = _admin(app)
    assert c.get('/site/').status_code == 200      # admin preview works
    assert _views(app) == before                    # but nothing recorded


def test_repeat_visit_adds_view_but_same_unique(app):
    _publish(app)
    with app.app_context():
        v_before = SiteViewDaily.query.filter_by(path='/site/').first()
        v_before = v_before.views if v_before else 0
        u_before = SiteVisitorDaily.query.count()
    c = app.test_client()
    ua = {'User-Agent': 'RepeatVisitorProbe/1.0'}    # distinct client -> its own unique row
    c.get('/site/', headers=ua); c.get('/site/', headers=ua)   # two hits, same client
    with app.app_context():
        assert SiteViewDaily.query.filter_by(path='/site/').first().views == v_before + 2
        assert SiteVisitorDaily.query.count() == u_before + 1   # one unique visitor, not two


def test_bot_is_ignored(app):
    _publish(app)
    before = _views(app)
    app.test_client().get('/site/', headers={'User-Agent': 'Googlebot/2.1'})
    assert _views(app) == before                    # bot traffic not counted


def test_public_site_sets_no_cookie(app):
    _publish(app)
    r = app.test_client().get('/site/')
    assert 'Set-Cookie' not in r.headers            # cookieless analytics


# --- summary ---------------------------------------------------------------
def test_summary_aggregates(app):
    from utils import site_analytics
    _publish(app)
    c = app.test_client()
    c.get('/site/'); c.get('/site/')
    with app.app_context():
        data = site_analytics.summary(days=30)
        assert data['total_views'] >= 2
        assert data['unique_visitors'] >= 1
        assert len(data['series']) == 30
        assert any(p['path'] == '/site/' for p in data['top_pages'])


# --- admin dashboard + export ----------------------------------------------
def test_admin_dashboard_renders(app):
    _publish(app)
    app.test_client().get('/site/')
    c = _admin(app)
    r = c.get('/website/analytics')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Website analytics' in html and 'Page views' in html


def test_analytics_csv_export(app):
    _publish(app)
    app.test_client().get('/site/')
    c = _admin(app)
    r = c.get('/website/analytics/export?days=30')
    assert r.status_code == 200
    assert 'text/csv' in r.headers.get('Content-Type', '')
    body = r.get_data(as_text=True)
    assert 'Page views' in body and 'Top page' in body


def test_analytics_requires_admin(app):
    _publish(app)
    # anonymous is redirected to login, not served the dashboard
    r = app.test_client().get('/website/analytics')
    assert r.status_code in (301, 302, 401, 403)
