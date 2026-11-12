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


def test_a_session_can_swap_subjects_and_students_follow(app):
    """A session swaps one subject; its sitting uses the new set, other
    sittings keep the usual one, and students already filled can be updated."""
    from models import db, SchoolSettings, Student
    from utils.exam_subject_config import (set_sitting, stream_waec_subjects, sitting_changes,
                                           current_exam_year, get_config)
    with app.app_context():
        SchoolSettings.query.filter_by(key='exam_subject_config').delete()
        db.session.commit()
        y = current_exam_year() or 2026
        base = get_config()['waec']
        gen = [s for s in base['general'] if s != 'Civic Education'] + ['Data Processing']
        set_sitting('waec', y, gen, base['streams'])
        try:
            this = stream_waec_subjects('Science', y)
            other = stream_waec_subjects('Science', y - 5)
            assert 'Data Processing' in this and 'Civic Education' not in this
            assert 'Civic Education' in other and 'Data Processing' not in other
            ch = {c['stream']: c for c in sitting_changes('waec', y)}
            assert ch['Science']['added'] == ['Data Processing'] and ch['Science']['removed'] == ['Civic Education']
            # The usual set's save keeps the session's own set.
            from utils.exam_subject_config import save_config
            save_config({'waec': {'catalog': base['catalog'], 'general': base['general'], 'streams': base['streams']}})
            assert str(y) in get_config()['waec']['years']
        finally:
            SchoolSettings.query.filter_by(key='exam_subject_config').delete()
            db.session.commit()


def test_exam_subjects_page_session_view(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    from utils.exam_subject_config import current_exam_year
    with app.app_context():
        y = current_exam_year() or 2026
    page = c.get(f'/settings/exam-subjects?year={y}').get_data(as_text=True)
    assert 'Usual subjects' in page and str(y) in page
    tok = auth_csrf(c)
    r = c.post(f'/settings/exam-subjects?year={y}', data={'_csrf_token': tok, 'action': 'save_year', 'year': y,
               'waec_general[]': ['English Language', 'Mathematics', 'Data Processing']})
    assert r.status_code in (302, 303)
    with app.app_context():
        from utils.exam_subject_config import stream_waec_subjects
        assert 'Data Processing' in stream_waec_subjects('Arts', y)
    c.post(f'/settings/exam-subjects?year={y}', data={'_csrf_token': tok, 'action': 'clear_year', 'year': y})
    with app.app_context():
        from utils.exam_subject_config import stream_waec_subjects
        assert 'Data Processing' not in stream_waec_subjects('Arts', y)
        from models import SchoolSettings, db
        SchoolSettings.query.filter_by(key='exam_subject_config').delete()
        db.session.commit()


def test_update_their_lists_swaps_only_the_changed_subjects(app, monkeypatch):
    from types import SimpleNamespace
    from models import db, SchoolSettings
    import routes.settings as rs
    from utils.exam_subject_config import set_sitting, get_config
    with app.app_context():
        SchoolSettings.query.filter_by(key='exam_subject_config').delete()
        db.session.commit()
        base = get_config()['waec']
        set_sitting('waec', 2099, [s for s in base['general'] if s != 'Civic Education'] + ['Data Processing'],
                    base['streams'])
        st = SimpleNamespace(id=1, stream='Arts', waec_subjects='Civic Education, Literature in English, Fishery',
                             jamb_subjects='')
        st.waec_subject_list = [x.strip() for x in st.waec_subjects.split(',')]
        st.jamb_subject_list = []
        monkeypatch.setattr(rs, '_sitting_students', lambda year: [st])
        try:
            assert rs._sitting_stale(2099)['waec'] == 1
            assert rs._apply_sitting_to_students(2099) == 1
            have = [x.strip() for x in st.waec_subjects.split(',')]
            assert 'Civic Education' not in have and 'Data Processing' in have
            assert 'Fishery' in have and 'Literature in English' in have      # their own picks kept
        finally:
            SchoolSettings.query.filter_by(key='exam_subject_config').delete()
            db.session.commit()
