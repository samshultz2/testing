"""The public marketing homepage is served by the app on a platform host, and
its content is editable live from the control plane.

Proves:
  * a platform host (www) serves the marketing homepage at `/`,
  * a real school host does NOT (it's their login-gated dashboard),
  * editing the stored content changes the page immediately,
  * with MULTI_TENANT off there is no interception.
"""
import pytest


@pytest.fixture()
def mt(tmp_path, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    monkeypatch.setenv('TENANT_DB_DIR', str(tmp_path / 'tenants'))
    from utils import tenancy, provisioning, tenant_runtime
    tenancy._reset_engine()
    tenant_runtime.reset_engines()
    tenancy.init_control_plane()
    tenancy.register_tenant('Pioneer', 'pioneer', 'a@pioneer.test')
    provisioning.provision('pioneer', admin_password='Zebra!Mango42Q')

    from app import create_app
    from config import Config

    class MTConfig(Config):
        TESTING = True
        MULTI_TENANT = True
        TENANT_BASE_DOMAIN = 'posyhub.test'
        TENANT_PRICE_KOBO = 5000000            # ₦50,000
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(tmp_path / 'fallback.db')
        WTF_CSRF_ENABLED = False

    app = create_app(MTConfig)
    yield app, tenancy
    tenant_runtime.reset_engines()
    tenancy._reset_engine()


def test_platform_host_serves_marketing_home(mt):
    app, _ = mt
    c = app.test_client()
    r = c.get('/', headers={'Host': 'www.posyhub.test'})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Run your whole school' in body          # default hero
    assert '/register' in body                       # CTA points at signup
    assert '50,000' in body                          # price derived from config


def test_real_school_host_is_not_marketing(mt):
    app, _ = mt
    c = app.test_client()
    r = c.get('/', headers={'Host': 'pioneer.posyhub.test'})
    # a real school's `/` is the login-gated dashboard, never the marketing page
    assert r.status_code == 302
    assert '/login' in (r.headers.get('Location') or '')


def test_homepage_content_is_editable_live(mt):
    app, _ = mt
    from utils import site_content
    with app.test_request_context():
        content = site_content.get_homepage()
        content['hero_title'] = 'A Totally New Headline'
        content['faqs'] = [{'q': 'Custom question?', 'a': 'Custom answer.'}]
        site_content.save_homepage(content)
    body = app.test_client().get('/', headers={'Host': 'www.posyhub.test'}).get_data(as_text=True)
    assert 'A Totally New Headline' in body
    assert 'Custom question?' in body


def test_flag_off_has_no_marketing_interception(client):
    # Default (single-school) app from conftest: `/` is the normal app root,
    # which for an anonymous user redirects to login — not the marketing page.
    r = client.get('/')
    assert r.status_code in (301, 302)
    assert 'Run your whole school' not in r.get_data(as_text=True)


def test_subdomain_availability_check(mt):
    app, _ = mt
    c = app.test_client()
    H = {'Host': 'signup.posyhub.test'}
    # already provisioned in the fixture -> taken
    assert c.get('/register/check?subdomain=pioneer', headers=H).get_json()['available'] is False
    # reserved
    assert c.get('/register/check?subdomain=www', headers=H).get_json()['available'] is False
    # too short / invalid
    assert c.get('/register/check?subdomain=ab', headers=H).get_json()['available'] is False
    assert c.get('/register/check?subdomain=Bad_Name', headers=H).get_json()['available'] is False
    # free
    r = c.get('/register/check?subdomain=brandnew', headers=H).get_json()
    assert r['available'] is True


def test_homepage_has_seo_and_new_sections(mt):
    app, _ = mt
    c = app.test_client()
    body = c.get('/', headers={'Host': 'www.posyhub.test'}).get_data(as_text=True)
    # SEO / social / structured data
    assert 'application/ld+json' in body
    assert 'og:title' in body and 'twitter:card' in body
    assert 'rel="canonical"' in body
    assert '"@type": "FAQPage"' in body
    # new sections
    assert 'Skip to content' in body                 # a11y skip link
    assert 'id="contact"' in body and 'id="security"' in body
    assert 'Privacy Policy' in body and 'Terms of Service' in body   # footer legal


def test_legal_pages_render(mt):
    app, _ = mt
    c = app.test_client()
    H = {'Host': 'www.posyhub.test'}
    for slug, title in [('privacy', 'Privacy Policy'), ('terms', 'Terms of Service'),
                        ('cookies', 'Cookie Policy')]:
        r = c.get(f'/legal/{slug}', headers=H)
        assert r.status_code == 200
        assert title in r.get_data(as_text=True)
    # unknown slug redirects home
    assert c.get('/legal/nope', headers=H).status_code in (301, 302)


def test_line_editor_round_trips():
    from utils.site_content import parse_pairs, format_pairs
    text = 'Title A | Body A\nTitle B | Body B'
    items = parse_pairs(text, ('title', 'body'))
    assert items == [{'title': 'Title A', 'body': 'Body A'},
                     {'title': 'Title B', 'body': 'Body B'}]
    assert format_pairs(items, ('title', 'body')) == text
