"""Local (offline) embedding tagger for the Mock-JAMB bank. The sentence
model is faked so the tests need neither torch nor a download; they exercise
candidate building, topic+sub-topic assignment, the confidence threshold, the
untagged/year scoping, and the background-job handler's guards.
"""
import hashlib

import numpy as np

from models import db, Subject, MockJAMBQuestion
import utils.mock_bank_local_tag as lt


class _FakeModel:
    """Deterministic 16-dim embeddings from a text hash — enough for a stable
    argmax without any real model."""
    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=64):
        out = []
        for t in texts:
            v = np.frombuffer(hashlib.md5(t.encode()).digest(), dtype=np.uint8).astype('float32')
            out.append(v / (np.linalg.norm(v) or 1.0))
        return np.array(out, dtype='float32')


def test_candidates_cover_topics_and_subtopics():
    cands = lt._candidates('Mathematics')
    assert cands
    topics = {c[1] for c in cands}
    assert len(topics) >= 5
    # at least one candidate carries a sub-topic, and every sub-topic names its parent
    assert any(c[2] for c in cands)
    from utils.syllabus_data import FULL_SYLLABUS
    valid = {t for t, _ in FULL_SYLLABUS['mathematics']}
    assert topics <= valid


def _q(subj_id, year='2019', text='q', topic=None):
    return MockJAMBQuestion(subject_id=subj_id, exam_year=year, question_text=text,
                            option_a='a', option_b='b', option_c='c', option_d='d',
                            correct_option='A', topic=topic)


def test_local_tag_assigns_real_syllabus_topics(app, monkeypatch):
    from utils.syllabus_data import FULL_SYLLABUS
    valid_topics = {t for t, _ in FULL_SYLLABUS['mathematics']}
    valid_subs = {s for _t, subs in FULL_SYLLABUS['mathematics'] for s in (subs or [])}
    monkeypatch.setattr(lt, '_model', lambda: _FakeModel())
    with app.app_context():
        subj = Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.flush()
        rows = [_q(subj.id, text=f'question number {i} about algebra') for i in range(6)]
        db.session.add_all(rows); db.session.commit()
        ids = [subj.id] + [r.id for r in rows]
        try:
            res = lt.local_tag(subj, mode='untagged', threshold=0.0)  # accept every argmax
            assert res['scanned'] == 6 and res['topic_set'] == 6
            db.session.expire_all()
            for qid in ids[1:]:
                q = db.session.get(MockJAMBQuestion, qid)
                assert q.topic in valid_topics                 # never invented
                if q.subtopic:
                    assert q.subtopic in valid_subs
        finally:
            for qid in ids[1:]:
                o = db.session.get(MockJAMBQuestion, qid); o and db.session.delete(o)
            db.session.delete(db.session.get(Subject, ids[0])); db.session.commit()


def test_threshold_and_untagged_year_scoping(app, monkeypatch):
    monkeypatch.setattr(lt, '_model', lambda: _FakeModel())
    with app.app_context():
        subj = Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.flush()
        already = _q(subj.id, year='2019', text='pre-tagged', topic='Algebra')
        blank19 = _q(subj.id, year='2019', text='fresh 2019')
        blank20 = _q(subj.id, year='2020', text='fresh 2020')
        db.session.add_all([already, blank19, blank20]); db.session.commit()
        ids = [subj.id, already.id, blank19.id, blank20.id]
        try:
            # impossible threshold → nothing tagged, but the right rows are scanned
            res = lt.local_tag(subj, mode='untagged', year='2019', threshold=2.0)
            assert res['scanned'] == 1 and res['topic_set'] == 0   # only the blank 2019 row
            db.session.expire_all()
            assert db.session.get(MockJAMBQuestion, ids[1]).topic == 'Algebra'  # pre-tag untouched
            assert (db.session.get(MockJAMBQuestion, ids[3]).topic or '') == ''  # 2020 out of scope
        finally:
            for qid in ids[1:]:
                o = db.session.get(MockJAMBQuestion, qid); o and db.session.delete(o)
            db.session.delete(db.session.get(Subject, ids[0])); db.session.commit()


def test_job_handler_reports_not_installed(app, monkeypatch):
    from utils import jobs
    monkeypatch.setattr(lt, 'available', lambda: False)
    with app.app_context():
        subj = Subject(name='Mathematics', is_active=True)
        db.session.add(subj); db.session.commit()
        sid = subj.id
        try:
            class _J:                 # a minimal job stand-in
                message = None
            out = jobs._HANDLERS['bank_local_tag'](_J(), subject_id=sid)
            assert out == {'error': 'not_installed'}
        finally:
            db.session.delete(db.session.get(Subject, sid)); db.session.commit()
