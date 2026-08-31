"""Website Builder — AI copywriting assistant.

Covers: the feature self-disables without an API key; the editor hides the
button when unavailable; copy_fields selects only editable text (never links or
images); the model reply parser is robust to markdown fences and junk; a
successful generation writes the draft into the block (but the admin still saves
it); and only non-personal branding is passed to the model (no student PII).
"""
from config import Config
from models import db, SiteSettings, SitePage, SchoolSettings, Student, Branch
from tests.conftest import login_token, auth_csrf
from utils.site_blocks import default_home_blocks
from utils import site_ai


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


# --- pure helpers ----------------------------------------------------------
def test_copy_fields_selects_text_only():
    props = {'heading': 'Hi', 'subheading': 'There', 'primary_href': '/x',
             'primary_label': 'Go', 'image': '', 'bg_image': '', 'stats': [1, 2]}
    fields = set(site_ai.copy_fields(props))
    assert fields == {'heading', 'subheading', 'primary_label'}    # no href/image/list


def test_parse_handles_markdown_and_junk():
    fields = ['heading', 'subheading']
    good = '```json\n{"heading": "Welcome", "subheading": "A great school", "x": 1}\n```'
    out = site_ai._parse(good, fields)
    assert out == {'heading': 'Welcome', 'subheading': 'A great school'}    # x dropped
    assert site_ai._parse('not json at all', fields) == {}                  # junk -> empty
    assert site_ai._parse('{"heading": 42}', fields) == {}                  # non-string ignored


def test_unavailable_without_key(app, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    assert site_ai.is_available() is False
    # and with no fields or unavailable, suggest returns empty without calling out
    assert site_ai.suggest_block_copy('Hero', ['heading'], {}, branding={'name': 'X'}) == {}


# --- editor gating ---------------------------------------------------------
def test_editor_hides_ai_when_unavailable(app, monkeypatch):
    monkeypatch.setattr(site_ai, 'is_available', lambda: False)
    _publish(app)
    c = _admin(app)
    with app.app_context():
        pid = SitePage.query.filter_by(slug='home').first().id
    html = c.get(f'/website/pages/{pid}').get_data(as_text=True)
    assert 'Write with AI' not in html


def test_editor_shows_ai_when_available(app, monkeypatch):
    monkeypatch.setattr(site_ai, 'is_available', lambda: True)
    _publish(app)
    c = _admin(app)
    with app.app_context():
        pid = SitePage.query.filter_by(slug='home').first().id
    html = c.get(f'/website/pages/{pid}').get_data(as_text=True)
    assert 'Write with AI' in html


def test_ai_route_unavailable_changes_nothing(app, monkeypatch):
    monkeypatch.setattr(site_ai, 'is_available', lambda: False)
    _publish(app)
    c = _admin(app)
    with app.app_context():
        pg = SitePage.query.filter_by(slug='home').first()
        pid = pg.id
        hero_idx = next(i for i, b in enumerate(pg.blocks) if b['type'] == 'hero')
        before = pg.blocks[hero_idx]['props'].get('heading')
    c.post(f'/website/pages/{pid}/block/{hero_idx}/ai', data={'_csrf_token': auth_csrf(c)})
    with app.app_context():
        after = SitePage.query.filter_by(slug='home').first().blocks[hero_idx]['props'].get('heading')
        assert after == before                       # nothing generated or changed


# --- successful generation (model mocked) ----------------------------------
def test_ai_route_applies_draft(app, monkeypatch):
    _publish(app)
    monkeypatch.setattr(site_ai, 'is_available', lambda: True)
    captured = {}

    def fake_suggest(label, fields, current, *, branding, tone='', keywords=''):
        captured['branding'] = branding
        captured['fields'] = fields
        return {'heading': 'A Place to Belong and Grow'}

    monkeypatch.setattr(site_ai, 'suggest_block_copy', fake_suggest)
    c = _admin(app)
    with app.app_context():
        pg = SitePage.query.filter_by(slug='home').first()
        pid = pg.id
        hero_idx = next(i for i, b in enumerate(pg.blocks) if b['type'] == 'hero')
    c.post(f'/website/pages/{pid}/block/{hero_idx}/ai',
           data={'_csrf_token': auth_csrf(c), 'tone': 'warm', 'keywords': 'STEM'})
    with app.app_context():
        blk = SitePage.query.filter_by(slug='home').first().blocks[hero_idx]
        assert blk['props']['heading'] == 'A Place to Belong and Grow'
    # branding was passed, and it carries the school name (single source of truth)
    assert captured['branding'].get('name') == 'Testville College'
    assert 'heading' in captured['fields']


def test_ai_only_sends_branding_never_pii(app, monkeypatch):
    _publish(app)
    # a student whose name must never be handed to the model
    with app.app_context():
        db.session.add(Student(student_id=Student.generate_student_id(), first_name='Zerakiel',
                               surname='Ndlovu', gender='Male', is_active=True,
                               branch_id=Branch.get_default().id))
        db.session.commit()
    monkeypatch.setattr(site_ai, 'is_available', lambda: True)
    seen = {}

    def fake_suggest(label, fields, current, *, branding, tone='', keywords=''):
        seen['payload'] = repr((label, fields, current, branding, tone, keywords))
        return {'heading': 'Ok'}

    monkeypatch.setattr(site_ai, 'suggest_block_copy', fake_suggest)
    c = _admin(app)
    with app.app_context():
        pg = SitePage.query.filter_by(slug='home').first()
        pid = pg.id
        hero_idx = next(i for i, b in enumerate(pg.blocks) if b['type'] == 'hero')
    c.post(f'/website/pages/{pid}/block/{hero_idx}/ai', data={'_csrf_token': auth_csrf(c)})
    assert 'Zerakiel' not in seen['payload'] and 'Ndlovu' not in seen['payload']
