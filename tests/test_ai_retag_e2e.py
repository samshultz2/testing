"""End to end: the AI retag (inline and batch) gives each question its syllabus
code and files it in its JAMB-part section. Anthropic is faked -- no tokens."""
import json
import uuid
from types import SimpleNamespace as NS

import pytest

from models import db, Subject, MockJAMBSyllabus, MockJAMBSyllabusNode, MockJAMBQuestion


def _setup(subject_name, fname, stale_section):
    from utils.jamb_syllabus_import import import_syllabus
    s = Subject(name=subject_name, is_active=False); db.session.add(s); db.session.commit()
    import_syllabus(s, open('data/jamb_syllabi/%s.json' % fname).read(), fmt='json')
    y = MockJAMBSyllabus.query.filter_by(subject_id=s.id).first()
    # an untagged bank question still filed under an old section
    q = MockJAMBQuestion(mock_exam_id=None, subject_id=s.id, section=stale_section, exam_year='2019',
                         question_text='Question ' + uuid.uuid4().hex[:6], option_a='a', option_b='b',
                         option_c='c', option_d='d', correct_option='A', marks=1)
    db.session.add(q); db.session.commit()
    return s, y, q


def _cleanup(s, y):
    MockJAMBQuestion.query.filter_by(subject_id=s.id).delete()
    MockJAMBSyllabusNode.query.filter_by(syllabus_id=y.id).delete()
    db.session.delete(y); db.session.delete(s); db.session.commit()


def _leaf(y, part_code):
    nodes = MockJAMBSyllabusNode.query.filter_by(syllabus_id=y.id).all()
    return next(n.code for n in sorted(nodes, key=lambda n: n.code) if ('.%s.' % part_code) in n.code + '.'
                and not any(m.parent_id == n.id for m in nodes))


class _FakeMessages:
    def __init__(self, answer):
        self.answer = answer
        self.batches = self

    def create(self, **kw):            # inline: answer every question in the prompt with one code
        import re
        ids = re.findall(r'"id": (\d+)', kw['messages'][0]['content'])
        text = json.dumps([{'id': int(i), 'primary': self.answer, 'secondary': []} for i in ids])
        return NS(content=[NS(type='thinking', thinking=''), NS(type='text', text=text)])

    def results(self, batch_id):       # batch: one succeeded result per question
        return [NS(custom_id='q%d' % qid, result=NS(type='succeeded', message=NS(content=[
            NS(type='text', text=json.dumps({'primary': self.answer, 'secondary': []}))])))
            for qid in self.qids]


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key-not-real')
    import utils.waec_ocr as w
    real = w._vision_config

    def cfg():
        c = real(); c.update(installed=True, has_key=True, key='test-key-not-real'); return c
    monkeypatch.setattr(w, '_vision_config', cfg)


@pytest.mark.parametrize('subject_name,fname,stale,part,expect', [
    ('Economics', 'economics', 'micro', 'DEM', 'dem'),
    ('Physics', 'physics', 'mechanics', 'MOT', 'mot'),
])
def test_inline_retag_codes_and_sections(app, monkeypatch, fake_key, subject_name, fname, stale, part, expect):
    import anthropic
    from utils.mock_bank_coded_retag import coded_retag
    with app.app_context():
        s, y, q = _setup(subject_name, fname, stale)
        try:
            code = _leaf(y, part)
            fake = _FakeMessages(code)
            monkeypatch.setattr(anthropic, 'Anthropic', lambda **kw: NS(messages=fake))
            r = coded_retag(s, mode='untagged', model='claude-haiku-5-5')
            assert r['error'] is None and r['tagged'] == 1
            got = db.session.get(MockJAMBQuestion, q.id)
            assert got.syllabus_item_code == code and got.section == expect
        finally:
            _cleanup(s, y)


def test_batch_retag_applies_codes_and_sections(app, fake_key):
    from utils import mock_bank_batch_retag as batch
    from utils.mock_bank_coded_retag import coded_nodes
    from utils.jamb_blueprint import sections_for
    with app.app_context():
        s, y, q = _setup('Economics', 'economics', 'macro', )
        try:
            code = _leaf(y, 'NAT')
            # requests are built for the untagged question, with the model's settings
            reqs = batch.build_requests(s.name, 'SYL', [q], 'claude-haiku-5-5')
            assert reqs[0]['custom_id'] == 'q%d' % q.id and reqs[0]['params']['output_config']
            fake = _FakeMessages(code); fake.qids = [q.id]
            by_code, _ = coded_nodes(s.id)
            out = batch.apply_results(NS(messages=fake), 'b1', s, by_code, {n.id: n for n in by_code.values()})
            assert out['tagged'] == 1
            got = db.session.get(MockJAMBQuestion, q.id)
            assert got.syllabus_item_code == code and got.section == 'nat'
            assert 'nat' in {x['section'] for x in sections_for(s.name)}
        finally:
            _cleanup(s, y)


def test_batch_progress_counts():
    from utils.mock_bank_batch_retag import batch_progress
    b = NS(processing_status='in_progress',
           request_counts=NS(processing=600, succeeded=1170, errored=10, canceled=0, expired=0))
    client = NS(messages=NS(batches=NS(retrieve=lambda bid: b)))
    assert batch_progress(client, 'x') == ('in_progress', 1180, 1780)


def test_syllabus_page_shows_batch_progress(app, auth_client):
    from models import BackgroundJob
    with app.app_context():
        s, y, q = _setup('Economics', 'economics', 'micro')
        sid = s.id
        done = BackgroundJob(kind='bank_batch_retag', status='done', params=json.dumps({'subject_id': sid}),
                             message='Claude is tagging — 1,180 of 1,780 done', progress=1180, total=1780)
        waiting = BackgroundJob(kind='bank_batch_retag', status='queued', params=json.dumps({'subject_id': sid}))
        db.session.add_all([done, waiting]); db.session.commit()
        try:
            html = auth_client.get('/mock-jamb/bank/syllabus?subject_id=%d' % sid).get_data(as_text=True)
            assert 'id="batchJobPill"' in html and '66%' in html and 'Claude is tagging' in html
            d = auth_client.get('/mock-jamb/bank/syllabus/batch-status?subject_id=%d' % sid).get_json()
            # the newest row is a queued check: still in progress, showing the last numbers
            assert d['in_progress'] and d['stage'] == 'tagging' and d['progress'] == 1180 and d['total'] == 1780
        finally:
            BackgroundJob.query.filter(BackgroundJob.id.in_([done.id, waiting.id])).delete(synchronize_session=False)
            db.session.commit()
            _cleanup(s, y)
