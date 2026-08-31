"""Claude-vision OCR for handwritten internal broadsheets."""
import io
import sys
import types

from flask import url_for

from models import db, ClassSubject, Student
from routes.subjects import _sheet_columns
from tests.conftest import auth_csrf
from utils import waec_ocr
from tests.test_results_workflow import _setup, _admin


def _fake_anthropic(json_text):
    """A stand-in `anthropic` module whose client returns a fixed text block."""
    mod = types.ModuleType('anthropic')

    class _Client:
        def __init__(self, **kw):
            blk = types.SimpleNamespace(type='text', text=json_text)
            msg = types.SimpleNamespace(content=[blk])
            self.messages = types.SimpleNamespace(create=lambda **k: msg)
    mod.Anthropic = _Client
    return mod


def test_vision_extract_scoresheet_parses(monkeypatch):
    payload = ('{"rows":['
               '{"student_num":"S1","name":"Ada Obi","scores":["5","-","12","99"]},'
               '{"name":"","scores":[1,2,3]},'                       # no name -> dropped
               '{"student_num":"","name":"Bob Eze","scores":[3,4]}'  # short -> padded
               ']}')
    monkeypatch.setitem(sys.modules, 'anthropic', _fake_anthropic(payload))
    monkeypatch.setattr(waec_ocr, '_vision_config', lambda: {
        'enabled': True, 'has_key': True, 'installed': True,
        'key': 'sk-ant-x', 'model': 'claude-haiku-4-5'})

    rows = waec_ocr.vision_extract_scoresheet(b'img', ['1st', '2nd', 'CBT'])   # ncol = 3
    assert rows == [
        {'student_num': 'S1', 'name': 'Ada Obi', 'cells': ['5', '', '12']},   # dash blanked, truncated
        {'student_num': '', 'name': 'Bob Eze', 'cells': ['3', '4', '']},      # padded to 3
    ]


def test_scoresheet_scan_uses_vision_when_available(app, monkeypatch):
    ids = _setup(app)
    with app.test_request_context():
        cs = db.session.get(ClassSubject, ids['cs'])
        cols = _sheet_columns(cs)
        first_at = cols[0][0].id
        scan_url = url_for('subjects.scoresheet_scan')

    # Force the vision path and return a row that matches WF1 by admission number.
    monkeypatch.setattr(waec_ocr, 'vision_available', lambda: True)
    captured = {}

    def fake_sheet(data, labels, media):
        captured['labels'] = labels
        return [{'student_num': 'WF1', 'name': 'Aa One', 'cells': ['80'] + [''] * (len(labels) - 1)}]
    monkeypatch.setattr(waec_ocr, 'vision_extract_scoresheet', fake_sheet)

    c = _admin(app)
    r = c.post(scan_url, content_type='multipart/form-data', data={
        '_csrf_token': auth_csrf(c),
        'term_id': ids['term'], 'assignment_id': ids['asg'], 'class_subject_id': ids['cs'],
        'file': (io.BytesIO(b'\xff\xd8\xff fake jpeg'), 'sheet.jpg'),
    })
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '/scores/scan/save' in body                       # rendered the review/confirm grid
    assert f'name="cell_0_{first_at}"' in body and 'value="80"' in body
    with app.app_context():
        a = db.session.get(Student, ids['a'])
        assert f'value="{a.id}" selected' in body            # matched WF1 by admission number
    # The route passed the subject's column labels to the vision reader.
    assert captured['labels'] and len(captured['labels']) == len(cols)
