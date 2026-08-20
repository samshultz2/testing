"""Per-school WAEC/JAMB subject config: defaults, save/round-trip, per-stream
resolution (general + stream extras), and the settings page + extrapolate route.
"""
from config import Config
from tests.conftest import login_token, auth_csrf


def test_defaults_resolve_stream_subjects(app):
    with app.app_context():
        from utils.exam_subject_config import (get_config, stream_waec_subjects,
                                         stream_jamb_subjects)
        cfg = get_config()
        assert 'waec' in cfg and 'jamb' in cfg
        # WAEC science stream = general + science extras, English + Physics present.
        sci = stream_waec_subjects('Science')
        assert 'English Language' in sci and 'Physics' in sci
        # JAMB carries English (general) plus 3 stream subjects.
        jsci = stream_jamb_subjects('Science')
        assert 'English Language' in jsci and len(jsci) >= 4
        # Unknown stream → empty list (falsy), like the old dict.get.
        assert stream_waec_subjects('Nope') == []


def test_save_and_resolve_roundtrip(app):
    with app.app_context():
        from utils.exam_subject_config import save_config, stream_waec_subjects, get_config
        save_config({
            'waec': {'catalog': ['Mathematics', 'English Language', 'Fishery'],
                     'general': ['English Language'],
                     'streams': {'Science': ['Fishery'], 'Arts': [], 'Commercial': []}},
            'jamb': {'catalog': ['English Language'], 'general': ['English Language'],
                     'streams': {'Science': [], 'Arts': [], 'Commercial': []}},
        })
        sci = stream_waec_subjects('Science')
        assert sci == ['English Language', 'Fishery']   # general + stream, deduped/ordered
        assert 'Fishery' in get_config()['waec']['catalog']
        # Reset to defaults for other tests.
        from models import SchoolSettings, db
        SchoolSettings.query.filter_by(key='exam_subject_config').delete()
        db.session.commit()


def test_settings_page_and_extrapolate(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    # Settings page renders.
    r = c.get('/settings/exam-subjects')
    assert r.status_code == 200
    # Extrapolate route accepts a valid stream (JSON response).
    r2 = c.post('/students/apply-stream-subjects',
                data={'stream': 'Science', '_csrf_token': auth_csrf(c)})
    assert r2.status_code == 200
    body = r2.get_json()
    assert body is not None and body.get('stream') == 'Science'
    assert 'waec_filled' in body and 'jamb_filled' in body
    # An invalid stream is rejected.
    r3 = c.post('/students/apply-stream-subjects',
                data={'stream': 'Bogus', '_csrf_token': auth_csrf(c)})
    assert r3.status_code == 400
