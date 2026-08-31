"""Website Builder — public admissions application + fee.

Covers: a free application creates a Website-sourced Applicant; a paid
application is gated on verified payment (nothing created until the callback
verifies); the honeypot silently drops bots; status lookup requires a matching
surname (no enumeration by number alone); admissions-closed is a 404 to POSTs.
"""
from config import Config
from models import db, SiteSettings, SitePage, SchoolSettings, Applicant, Branch
from tests.conftest import login_token, auth_csrf
from utils.site_blocks import default_home_blocks


def _publish(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables
        ensure_tables()
        if not SitePage.query.filter_by(slug='home').first():
            db.session.add(SitePage(slug='home', title='Home', blocks=default_home_blocks(), nav_order=0))
        SchoolSettings.set('school_name', 'Testville College', 'string')
        s = SiteSettings.get(); s.published = True; s.theme = {'preset': 'emerald'}
        db.session.commit()


def _open_admissions(app, *, fee='0'):
    with app.app_context():
        SchoolSettings.set('web_admissions_open', '1', 'string')
        SchoolSettings.set('web_admissions_fee', str(fee), 'string')
        db.session.commit()


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _csrf(c, url='/site/apply'):
    """Prime an anonymous session by GETting a page, then read its CSRF token."""
    c.get(url)
    return auth_csrf(c)


def _form(**over):
    data = {'first_name': 'Ada', 'surname': 'Obi', 'parent_name': 'Mr Obi',
            'parent_phone': '08030000000', '_csrf_token': ''}
    data.update(over)
    return data


# --- the form is reachable + gated ----------------------------------------
def test_apply_page_renders_when_published(app):
    _publish(app); _open_admissions(app)
    r = app.test_client().get('/site/apply')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Apply to Testville College' in html and 'name="website"' in html   # honeypot present


def test_apply_404_when_site_unpublished(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
        SiteSettings.get().published = False; db.session.commit()   # shared-DB: force draft
    assert app.test_client().get('/site/apply').status_code == 404


# --- free application creates an Applicant ---------------------------------
def test_free_application_creates_website_applicant(app):
    _publish(app); _open_admissions(app, fee='0')
    with app.app_context():
        before = Applicant.query.count()
    c = app.test_client()
    tok = _csrf(c)
    r = c.post('/site/apply', data=_form(_csrf_token=tok))
    assert r.status_code == 200
    assert 'Application submitted' in r.get_data(as_text=True)
    with app.app_context():
        assert Applicant.query.count() == before + 1
        a = Applicant.query.order_by(Applicant.id.desc()).first()
        assert a.source == 'Website' and a.status == 'Applied'
        assert a.first_name == 'Ada' and a.surname == 'Obi'


def test_validation_errors_do_not_create(app):
    _publish(app); _open_admissions(app)
    with app.app_context():
        before = Applicant.query.count()
    c = app.test_client()
    tok = _csrf(c)
    # missing surname + no contact
    r = c.post('/site/apply', data={'first_name': 'Ada', 'parent_name': 'Mr Obi', '_csrf_token': tok})
    assert r.status_code == 200 and 'Required' in r.get_data(as_text=True)
    with app.app_context():
        assert Applicant.query.count() == before


# --- honeypot silently drops bots ------------------------------------------
def test_honeypot_drops_bot_without_creating(app):
    _publish(app); _open_admissions(app)
    with app.app_context():
        before = Applicant.query.count()
    c = app.test_client()
    tok = _csrf(c)
    r = c.post('/site/apply', data=_form(_csrf_token=tok, website='http://spam'))
    assert r.status_code == 200 and 'Thank you' in r.get_data(as_text=True)
    with app.app_context():
        assert Applicant.query.count() == before      # nothing created


# --- admissions closed rejects POSTs ---------------------------------------
def test_closed_admissions_rejects_post(app):
    _publish(app)
    with app.app_context():
        SchoolSettings.set('web_admissions_open', '0', 'string'); db.session.commit()
        before = Applicant.query.count()
    c = app.test_client()
    # the closed page shows no form, so prime the CSRF token from the track page
    r = c.post('/site/apply', data=_form(_csrf_token=_csrf(c, '/site/apply/track')))
    assert r.status_code == 404
    with app.app_context():
        assert Applicant.query.count() == before


# --- paid application is gated on verified payment -------------------------
def test_paid_application_requires_verified_payment(app, monkeypatch):
    _publish(app); _open_admissions(app, fee='5000')
    from utils import payments
    monkeypatch.setattr(payments, 'is_configured', lambda: True)
    monkeypatch.setattr(payments, 'initialize',
                        lambda **k: {'ok': True, 'authorization_url': 'https://pay.example/redirect'})
    c = app.test_client()
    with app.app_context():
        before = Applicant.query.count()
    # submit -> redirected to the gateway, NOTHING created yet
    r = c.post('/site/apply', data=_form(_csrf_token=_csrf(c)))
    assert r.status_code == 302 and 'pay.example' in r.headers['Location']
    with app.app_context():
        assert Applicant.query.count() == before

    # callback with a verified payment -> now the applicant exists, fee booked
    monkeypatch.setattr(payments, 'verify', lambda ref: {'ok': True})
    # pull the pending reference out of the session to build the callback
    with c.session_transaction() as sess:
        ref = sess['apply_pending']['ref']
    r2 = c.get(f'/site/apply/callback?reference={ref}')
    assert r2.status_code == 200 and 'Payment confirmed' in r2.get_data(as_text=True)
    with app.app_context():
        assert Applicant.query.count() == before + 1
        a = Applicant.query.order_by(Applicant.id.desc()).first()
        assert a.source == 'Website'


def test_failed_payment_creates_nothing(app, monkeypatch):
    _publish(app); _open_admissions(app, fee='5000')
    from utils import payments
    monkeypatch.setattr(payments, 'is_configured', lambda: True)
    monkeypatch.setattr(payments, 'initialize',
                        lambda **k: {'ok': True, 'authorization_url': 'https://pay.example/r'})
    c = app.test_client()
    c.post('/site/apply', data=_form(_csrf_token=_csrf(c)))
    with app.app_context():
        before = Applicant.query.count()
    monkeypatch.setattr(payments, 'verify', lambda ref: {'ok': False})
    with c.session_transaction() as sess:
        ref = sess['apply_pending']['ref']
    r = c.get(f'/site/apply/callback?reference={ref}')
    assert 'not completed' in r.get_data(as_text=True)
    with app.app_context():
        assert Applicant.query.count() == before


# --- status lookup requires matching surname (no enumeration) --------------
def test_track_requires_matching_surname(app):
    _publish(app); _open_admissions(app)
    c = app.test_client()
    c.post('/site/apply', data=_form(_csrf_token=_csrf(c)))
    with app.app_context():
        no = Applicant.query.order_by(Applicant.id.desc()).first().application_no
    # right number, wrong surname -> not found
    r = c.post('/site/apply/track', data={'application_no': no, 'surname': 'Wrong', '_csrf_token': auth_csrf(c)})
    assert "couldn't find" in r.get_data(as_text=True)
    # right number + surname -> found
    r2 = c.post('/site/apply/track', data={'application_no': no, 'surname': 'Obi', '_csrf_token': auth_csrf(c)})
    assert no in r2.get_data(as_text=True) and 'Applied' in r2.get_data(as_text=True)


# --- admin can configure online admissions ---------------------------------
def test_admin_can_configure_admissions(app):
    with app.app_context():
        from utils.finance_ledger import ensure_tables; ensure_tables()
    c = _admin(app); c.get('/website/')
    c.post('/website/admissions', data={'web_admissions_open': 'on', 'fee': '2500',
                                        'intro': 'Welcome!', '_csrf_token': auth_csrf(c)})
    with app.app_context():
        from utils import site_admissions
        cfg = site_admissions.settings()
        assert cfg['open'] is True and cfg['fee'] == 2500.0 and cfg['intro'] == 'Welcome!'
