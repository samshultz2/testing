"""JAMB coded-syllabus import: parsing, reconcile-by-code, blueprint integration
and the bank syllabus routes."""
import itertools
import json
import os

import pytest

from config import Config
from models import db, Subject, MockJAMBSyllabus, MockJAMBSyllabusNode
from tests.conftest import login_token, auth_csrf

_SEQ = itertools.count()
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _clean_syllabi(app):
    """The session DB is shared; an imported syllabus overrides the built-in
    blueprint, so wipe imports after each test to keep other suites isolated."""
    yield
    with app.app_context():
        MockJAMBSyllabusNode.query.delete()
        MockJAMBSyllabus.query.delete()
        db.session.commit()


def _math_json():
    with open(os.path.join(_ROOT, 'data', 'jamb_syllabi', 'mathematics.json')) as f:
        return f.read()


def _english_json():
    with open(os.path.join(_ROOT, 'data', 'jamb_syllabi', 'english_language.json')) as f:
        return f.read()


def _subject(app, name):
    with app.app_context():
        s = Subject.query.filter_by(name=name).first()
        if not s:
            s = Subject(name=name, is_active=True)
            db.session.add(s)
            db.session.commit()
        return s.id


def test_all_bundled_syllabi_import_cleanly(app):
    """Every shipped data/jamb_syllabi/*.json parses and reconciles without error."""
    from utils.jamb_syllabus_import import import_syllabus
    base = os.path.join(_ROOT, 'data', 'jamb_syllabi')
    files = [f for f in os.listdir(base) if f.endswith('.json')]
    assert files, 'no bundled syllabi found'
    for fn in files:
        sid = _subject(app, f'Bundled-{fn}-{next(_SEQ)}')
        with app.app_context():
            subj = db.session.get(Subject, sid)
            with open(os.path.join(base, fn)) as fh:
                diff = import_syllabus(subj, fh.read(), fmt='json')
            assert diff['sections'] >= 1 and diff['items'] >= 1
            # every stored node carries a stable, prefixed code
            codes = [n.code for n in MockJAMBSyllabusNode.query
                     .join(MockJAMBSyllabus).filter(MockJAMBSyllabus.subject_id == sid).all()]
            assert codes and all('.' in c and c == c.upper() for c in codes)


def test_parse_json_prefixes_stable_codes():
    from utils.jamb_syllabus_import import parse
    d = parse(_math_json(), fmt='json')
    assert d['prefix'] == 'MATH' and d['total'] == 40
    codes = {n['code'] for n in d['nodes']}
    assert 'MATH.NUM' in codes and 'MATH.NUM.1' in codes and 'MATH.NUM.1.A' in codes
    kinds = {}
    for n in d['nodes']:
        kinds[n['kind']] = kinds.get(n['kind'], 0) + 1
    assert kinds == {'section': 5, 'topic': 23, 'item': 78}
    assert sum(s['count'] for s in d['blueprint']) == 40


def test_reconcile_add_rename_remove(app):
    from utils.jamb_syllabus_import import import_syllabus, parse, reconcile_syllabus
    sid = _subject(app, f'ReconMath{next(_SEQ)}')
    with app.app_context():
        subj = db.session.get(Subject, sid)
        diff = import_syllabus(subj, _math_json(), fmt='json')
        assert len(diff['added']) == 106 and not diff['removed']
        # Idempotent re-import: nothing changes.
        diff2 = import_syllabus(subj, _math_json(), fmt='json')
        assert not diff2['added'] and not diff2['renamed'] and not diff2['removed']

        # Rename one item + drop a whole section -> reconcile reflects both.
        data = parse(_math_json(), fmt='json', subject=subj.name)
        data['nodes'] = [n for n in data['nodes'] if not n['code'].startswith('MATH.STA')]
        for n in data['nodes']:
            if n['code'] == 'MATH.NUM.1.A':
                n['name'] = 'RENAMED operations'
        diff3 = reconcile_syllabus(subj, data)
        assert any(r['code'] == 'MATH.NUM.1.A' for r in diff3['renamed'])
        assert any(c.startswith('MATH.STA') for c in diff3['removed'])
        # The removed section's nodes are gone; the renamed one persists.
        assert MockJAMBSyllabusNode.query.filter_by(code='MATH.STA').first() is None
        assert MockJAMBSyllabusNode.query.filter_by(code='MATH.NUM.1.A').first().name == 'RENAMED operations'


def test_csv_import(app):
    from utils.jamb_syllabus_import import import_syllabus
    sid = _subject(app, f'CsvBio{next(_SEQ)}')
    csv_text = ('code,kind,name,parent,count\n'
                'BIO.CEL,section,Cell Biology,,6\n'
                'BIO.CEL.1,topic,The cell,BIO.CEL,\n'
                'BIO.CEL.1.A,item,Cell structure,BIO.CEL.1,\n')
    with app.app_context():
        subj = db.session.get(Subject, sid)
        diff = import_syllabus(subj, csv_text, fmt='csv')
        assert diff['sections'] == 1 and diff['topics'] == 1 and diff['items'] == 1
        node = MockJAMBSyllabusNode.query.filter_by(code='BIO.CEL.1.A').first()
        assert node is not None and node.kind == 'item'


def test_english_blueprint_drives_selection(app):
    """Once English's syllabus is imported, its 60-question blueprint wins."""
    from utils.jamb_syllabus_import import import_syllabus
    from utils.jamb_blueprint import blueprint_for, sections_for
    sid = _subject(app, 'English Language')
    with app.app_context():
        subj = db.session.get(Subject, sid)
        import_syllabus(subj, _english_json(), fmt='json')
        bp = blueprint_for('Use of English')     # alias resolves to english language
        assert bp['total'] == 60
        secs = {s['section'] for s in sections_for('English Language')}
        assert {'comprehension', 'summary', 'cloze', 'reading_text',
                'basic_grammar', 'vowels', 'emphatic_stress'} <= secs


def test_bank_syllabus_route_imports_bundled(app):
    sid = _subject(app, 'Mathematics')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.post('/mock-jamb/bank/syllabus/import',
               data={'_csrf_token': auth_csrf(c), 'subject_id': sid, 'bundled': 'mathematics'})
    assert r.status_code in (302, 303)
    body = c.get(f'/mock-jamb/bank/syllabus?subject_id={sid}').get_data(as_text=True)
    assert 'MATH.NUM.1.A' in body


def test_bundled_import_matches_renamed_subjects(app):
    """Bundled files resolve to renamed subjects (Accounting <- Principles of
    Accounts; Digital Technologies <- Computer Studies)."""
    acc = _subject(app, 'Accounting')
    dig = _subject(app, 'Digital Technologies')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    tok = auth_csrf(c)
    c.post('/mock-jamb/bank/syllabus/import',
           data={'_csrf_token': tok, 'subject_id': acc, 'bundled': 'principles_of_accounts'})
    c.post('/mock-jamb/bank/syllabus/import',
           data={'_csrf_token': tok, 'subject_id': dig, 'bundled': 'computer_studies'})
    with app.app_context():
        assert MockJAMBSyllabus.query.filter_by(subject_id=acc).first() is not None
        assert MockJAMBSyllabus.query.filter_by(subject_id=dig).first() is not None


def test_clear_syllabus_removes_it(app):
    """The clear action deletes a subject's imported syllabus and its nodes."""
    sid = _subject(app, f'ClearMe{next(_SEQ)}')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    with app.app_context():
        from utils.jamb_syllabus_import import import_syllabus
        import_syllabus(db.session.get(Subject, sid), _math_json(), fmt='json')
        assert MockJAMBSyllabus.query.filter_by(subject_id=sid).first() is not None
    c.post('/mock-jamb/bank/syllabus/clear',
           data={'_csrf_token': auth_csrf(c), 'subject_id': sid})
    with app.app_context():
        assert MockJAMBSyllabus.query.filter_by(subject_id=sid).first() is None
        assert MockJAMBSyllabusNode.query.filter(
            MockJAMBSyllabusNode.code.like('MATH.%')).count() == 0


def test_bundled_import_targets_its_own_subject_not_the_selected_one(app):
    """Clicking the Mathematics bundled button while another subject is selected
    must import into Mathematics, never the selected subject."""
    math_id = _subject(app, 'Mathematics')
    other_id = _subject(app, f'Accounting{next(_SEQ)}')
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    r = c.post('/mock-jamb/bank/syllabus/import',
               data={'_csrf_token': auth_csrf(c), 'subject_id': other_id, 'bundled': 'mathematics'})
    assert str(math_id) in (r.headers.get('Location') or '')     # redirected to Mathematics
    with app.app_context():
        assert MockJAMBSyllabus.query.filter_by(subject_id=math_id).first() is not None
        assert MockJAMBSyllabus.query.filter_by(subject_id=other_id).first() is None
