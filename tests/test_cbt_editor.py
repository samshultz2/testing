"""CBT question editor: subject-specific symbol palettes, the live preview, the
drag-and-drop uploads and the exam-level import template."""
import io
import uuid

from config import Config
from tests.conftest import login_token, auth_csrf
from utils.cbt_symbols import PALETTES, CARET, kind_for_subject, editor_config


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _exam(app, subject_name):
    from models import db, CBTExam, Subject
    with app.app_context():
        subj = Subject(name=f'{subject_name} {uuid.uuid4().hex[:4]}', is_active=True)
        db.session.add(subj); db.session.flush()
        e = CBTExam(title=f'{subject_name} test', subject_id=subj.id)
        db.session.add(e); db.session.commit()
        return e.id


def test_subject_names_pick_the_right_palette():
    assert kind_for_subject('Mathematics') == 'maths'
    assert kind_for_subject('General Mathematics') == 'maths'
    assert kind_for_subject('Further Mathematics') == 'further_maths'
    assert kind_for_subject('Further Maths') == 'further_maths'
    assert kind_for_subject('Physics') == 'physics'
    assert kind_for_subject('Chemistry') == 'chemistry'
    assert kind_for_subject('English Language') == 'general'
    assert kind_for_subject(None) == 'general'


def test_palettes_are_well_formed():
    tab_names = {k: [g['label'] for g in groups] for k, groups in PALETTES.items()}
    assert 'Calculus' in tab_names['further_maths'] and 'Matrices & vectors' in tab_names['further_maths']
    assert 'Units' in tab_names['physics'] and 'Nuclear' in tab_names['physics']
    assert 'Reactions' in tab_names['chemistry'] and 'States & units' in tab_names['chemistry']
    assert 'Geometry & trig' in tab_names['maths'] and 'Statistics' in tab_names['maths']
    for kind, groups in PALETTES.items():
        keys = [g['key'] for g in groups]
        assert len(keys) == len(set(keys)), kind
        for g in groups:
            assert g['items'], (kind, g['key'])
            for it in g['items']:
                assert it['type'] in ('tex', 'sym') and it['insert'] and it['label']
                assert it['insert'].count(CARET) <= 1
                if it['type'] == 'tex':
                    # Balanced braces, and no package that would need a download.
                    body = it['insert'].replace(CARET, '')
                    assert body.count('{') == body.count('}'), it
                    assert '\\ce' not in body and '\\pu' not in body


def test_exam_page_shows_subject_palette_preview_and_uploads(app):
    eid = _exam(app, 'Chemistry')
    c = _admin(app)
    html = c.get(f'/cbt/exams/{eid}').get_data(as_text=True)
    assert 'data-mx-kind="chemistry"' in html
    assert 'Rightleftharpoons' not in html and 'rightleftharpoons' in html    # palette data
    assert 'class="mxp"' in html and 'Student view' in html                  # live preview
    assert 'data-fd' in html and 'name="image"' in html                      # figure drop zone
    assert 'id="importPanel"' in html and f'/cbt/exams/{eid}/import-template' in html
    assert html.count('type="radio" name="correct_option"') == 4                        # A–D radios
    assert html.count('data-math-target=') == 4


def test_further_maths_and_physics_exams_get_their_own_sets(app):
    c = _admin(app)
    assert 'data-mx-kind="further_maths"' in c.get(f'/cbt/exams/{_exam(app, "Further Mathematics")}').get_data(as_text=True)
    assert 'data-mx-kind="physics"' in c.get(f'/cbt/exams/{_exam(app, "Physics")}').get_data(as_text=True)


def test_add_question_with_radio_answer_and_latex(app):
    from models import db, CBTExam
    eid = _exam(app, 'Physics')
    c = _admin(app)
    r = c.post(f'/cbt/exams/{eid}/questions/add', data={
        '_csrf_token': auth_csrf(c),
        'question_text': r'A body accelerates at \(2\,\mathrm{m\,s^{-2}}\) for 5 s from rest. Find v.',
        'option_a': r'\(10\,\mathrm{m\,s^{-1}}\)', 'option_b': '5', 'option_c': '7', 'option_d': '2.5',
        'correct_option': 'A', 'marks': '1'})
    assert r.status_code == 302
    with app.app_context():
        q = db.session.get(CBTExam, eid).questions.first()
        assert q.correct_option == 'A' and '\\mathrm{m\\,s^{-2}}' in q.question_text


def test_exam_import_template_has_subject_samples(app):
    from openpyxl import load_workbook
    eid = _exam(app, 'Chemistry')
    c = _admin(app)
    r = c.get(f'/cbt/exams/{eid}/import-template')
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.data))
    rows = list(wb['Questions'].iter_rows(values_only=True))
    assert rows[0][:6] == ('Question', 'A', 'B', 'C', 'D', 'Correct')
    assert any('\\mathrm' in (row[0] or '') for row in rows[1:])
    assert 'How to write formulas' in wb.sheetnames
    # And the importer reads its own template back.
    from utils import cbt_import
    assert len(cbt_import.parse_file(r.data, 'cbt_question_template.xlsx')) == 2


def test_bank_page_follows_subject_select(app):
    from models import db, Subject
    with app.app_context():
        s = Subject(name=f'Physics {uuid.uuid4().hex[:4]}', is_active=True)
        db.session.add(s); db.session.commit()
        sid = s.id
    c = _admin(app)
    html = c.get('/cbt/bank').get_data(as_text=True)
    assert 'data-math-kind-source' in html and f'value="{sid}" data-kind="physics"' in html
    assert 'data-fd' in html and 'class="mxp"' in html
    assert 'data-mx-kind="physics"' in c.get(f'/cbt/bank?subject_id={sid}').get_data(as_text=True)


def test_editor_config_shape():
    cfg = editor_config('Further Mathematics')
    assert cfg['kind'] == 'further_maths' and cfg['caret'] == CARET
    assert [k for k, _ in cfg['kinds']] == ['maths', 'further_maths', 'physics', 'chemistry', 'general']
