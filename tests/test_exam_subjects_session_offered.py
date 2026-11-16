"""The Add/Edit student forms only offer the subjects ticked for a session on
Settings → Exam Subjects."""
from tests.test_branch_overview import _legacy_admin


def test_offered_follows_session_ticks(app):
    from utils.exam_subject_config import get_config, save_config, set_sitting, offered
    with app.app_context():
        cfg = get_config()
        cat = cfg['waec']['catalog'] + ['Zz Session Only']
        save_config({'waec': {'catalog': cat, 'general': cfg['waec']['general'], 'streams': cfg['waec']['streams']}})
        set_sitting('waec', 2091, ['English Language', 'Mathematics'], {'Science': ['Zz Session Only']})
        got = offered('waec', 2091)
        assert got == [c for c in cat if c in ('English Language', 'Mathematics', 'Zz Session Only')]
        assert 'Zz Session Only' not in offered('waec', 2092) or 'Zz Session Only' in get_config()['waec']['general']


def test_add_form_carries_subjects_per_session(app):
    c = _legacy_admin(app)
    d = c.get('/students/add', headers={'Accept': 'application/json', 'X-Requested-With': 'fetch'})
    if not d.is_json:
        import json, re
        m = re.search(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', d.get_data(as_text=True), re.S)
        data = json.loads(m.group(1))
    else:
        data = d.get_json()
    opts = data['options']
    assert 'subjects_by_year' in opts
    for y, v in opts['subjects_by_year'].items():
        assert v['waec'] and v['label']
