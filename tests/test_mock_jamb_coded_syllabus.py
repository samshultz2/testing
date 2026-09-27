"""The exam draw prefers a subject's imported *coded* syllabus (stable
per-question ``syllabus_item_code`` -> topic) over a flat per-section random
sample, once questions are tagged: ``_draw_balanced()`` spreads the draw
evenly across the coded topics present, backfilling from not-yet-coded
questions so a subject that is only partially retagged never serves a
smaller paper than before. With no coded map it is identical to the old
plain shuffle-and-take. ``_coded_item_topic_map()`` builds that map from a
subject's imported syllabus tree ({} if none imported yet)."""
import random
from datetime import date
from models import (db, Subject, Branch, AcademicSession, Student, MockJAMBExam,
                    MockJAMBQuestion, MockJAMBAttempt, MockJAMBSyllabus, MockJAMBSyllabusNode)
from utils.jamb_blueprint import _draw_balanced

_SEQ = [0]


class _FakeQ:
    def __init__(self, id, code=None):
        self.id = id
        self.syllabus_item_code = code


def _pool(topic_counts):
    """topic_counts: {topic_key: n} -> a pool of FakeQ, each coded to a
    per-topic item code 'TOPIC.item', plus the given number of uncoded ones
    under the 'uncoded' key."""
    pool, i = [], 0
    for topic, n in topic_counts.items():
        for _ in range(n):
            code = None if topic == 'uncoded' else f'{topic}.item'
            pool.append(_FakeQ(i, code))
            i += 1
    return pool


def test_draw_balanced_spreads_evenly_across_coded_topics():
    pool = _pool({'t1': 6, 't2': 6, 't3': 6, 't4': 6})
    item_topic_map = {'t1.item': 't1', 't2.item': 't2', 't3.item': 't3', 't4.item': 't4'}
    rng = random.Random(1)
    chosen = _draw_balanced(pool, 8, rng, item_topic_map)
    assert len(chosen) == 8
    by_topic = {}
    for q in chosen:
        by_topic[q.syllabus_item_code] = by_topic.get(q.syllabus_item_code, 0) + 1
    # every topic contributed -- round robin, not a flat random sample that
    # could (and with a flat sample of 8 from 24, quite plausibly would)
    # leave a topic at zero.
    assert len(by_topic) == 4
    assert max(by_topic.values()) <= 3


def test_draw_balanced_backfills_from_uncoded_when_undercoded():
    """Only 2 of the 4 topics are coded (3 each); the rest of the pool is
    untagged. Asking for 10 must still return 10, backfilled from uncoded."""
    pool = _pool({'t1': 3, 't2': 3, 'uncoded': 10})
    item_topic_map = {'t1.item': 't1', 't2.item': 't2'}
    rng = random.Random(2)
    chosen = _draw_balanced(pool, 10, rng, item_topic_map)
    assert len(chosen) == 10
    coded = [q for q in chosen if q.syllabus_item_code]
    uncoded = [q for q in chosen if not q.syllabus_item_code]
    assert len(coded) == 6          # all coded stock used first
    assert len(uncoded) == 4        # remainder backfilled


def test_draw_balanced_without_map_is_plain_shuffle():
    pool = _pool({'uncoded': 20})
    rng = random.Random(3)
    chosen = _draw_balanced(pool, 5, rng, {})
    assert len(chosen) == 5
    assert len(set(q.id for q in chosen)) == 5  # no duplicates, no crash


def test_draw_balanced_per_candidate_variety_preserved():
    """Different rng seeds (i.e. different students) still draw different
    subsets -- balancing must not collapse everyone onto the same paper."""
    pool = _pool({'t1': 10, 't2': 10, 't3': 10})
    item_topic_map = {'t1.item': 't1', 't2.item': 't2', 't3.item': 't3'}
    a = _draw_balanced(pool, 9, random.Random(10), item_topic_map)
    b = _draw_balanced(pool, 9, random.Random(11), item_topic_map)
    assert {q.id for q in a} != {q.id for q in b}


def test_coded_item_topic_map_builds_from_imported_syllabus(app):
    from utils.mock_jamb_sitting import _coded_item_topic_map
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject(name=f'MapSubj{_SEQ[0]}', is_active=True)
        db.session.add(subj); db.session.flush()
        syll = MockJAMBSyllabus(subject_id=subj.id, subject_name=subj.name, code='X')
        db.session.add(syll); db.session.flush()
        topic = MockJAMBSyllabusNode(syllabus_id=syll.id, parent_id=None,
                                     code='X.T1', kind='topic', name='Topic 1')
        db.session.add(topic); db.session.flush()
        item = MockJAMBSyllabusNode(syllabus_id=syll.id, parent_id=topic.id,
                                    code='X.T1.a', kind='item', name='Item a')
        other_item = MockJAMBSyllabusNode(syllabus_id=syll.id, parent_id=topic.id,
                                          code='X.T1.b', kind='item', name='Item b')
        db.session.add_all([item, other_item]); db.session.commit()

        m = _coded_item_topic_map(subj.id)
        assert m == {'X.T1.a': 'X.T1', 'X.T1.b': 'X.T1'}


def test_coded_item_topic_map_empty_without_syllabus(app):
    from utils.mock_jamb_sitting import _coded_item_topic_map
    with app.app_context():
        _SEQ[0] += 1
        subj = Subject(name=f'NoSyllabus{_SEQ[0]}', is_active=True)
        db.session.add(subj); db.session.commit()
        assert _coded_item_topic_map(subj.id) == {}


def _bank_coded_subject(app, coded_fraction, n_per_topic=6, n_topics=4):
    """A bank (mock_exam_id NULL) for a made-up subject, all tagged
    section='algebra', with a coded syllabus of ``n_topics`` topics (one leaf
    item each). ``coded_fraction`` of the questions carry that topic's item
    code; the rest are untagged. Uses a made-up subject name (never a real
    JAMB_BLUEPRINT subject) so it can't collide with other tests sharing the
    session-scoped test database."""
    with app.app_context():
        _SEQ[0] += 1
        bid = Branch.get_default().id
        subj = Subject(name=f'CodedSubj{_SEQ[0]}', is_active=True)
        db.session.add(subj); db.session.flush()

        syll = MockJAMBSyllabus(subject_id=subj.id, subject_name=subj.name, code='X')
        db.session.add(syll); db.session.flush()
        topic_item_codes = []
        for t in range(n_topics):
            topic = MockJAMBSyllabusNode(syllabus_id=syll.id, parent_id=None,
                                         code=f'X.T{t}', kind='topic', name=f'Topic {t}')
            db.session.add(topic); db.session.flush()
            item = MockJAMBSyllabusNode(syllabus_id=syll.id, parent_id=topic.id,
                                        code=f'X.T{t}.a', kind='item', name=f'Item {t}a')
            db.session.add(item); db.session.flush()
            topic_item_codes.append(item.code)

        total = n_topics * n_per_topic
        n_coded = int(round(total * coded_fraction))
        made = 0
        for t in range(n_topics):
            item_code = topic_item_codes[t]
            for i in range(n_per_topic):
                coded = made < n_coded
                db.session.add(MockJAMBQuestion(
                    mock_exam_id=None, subject_id=subj.id, section='algebra',
                    syllabus_item_code=item_code if coded else None,
                    question_text=f'T{t} Q{i}', option_a='a', option_b='b',
                    option_c='c', option_d='d', correct_option='A', marks=1, order=i))
                made += 1
        db.session.commit()

        sess = AcademicSession(name=f'CODEDSESS-{_SEQ[0]}'); db.session.add(sess); db.session.flush()
        # No blueprint at all for this made-up subject -> _draw_subject_items()
        # takes the legacy per-subject cap path (norm_subject(subj_name) is
        # never in JAMB_BLUEPRINT for a made-up name); questions_per_subject
        # pins the cap so the test doesn't depend on blueprint_for()'s default.
        ex = MockJAMBExam(name=f'Coded Mock {_SEQ[0]}', exam_number=1, session_id=sess.id,
                          exam_date=date(2025, 3, 1), branch_id=bid, is_published=True,
                          duration_minutes=90, questions_per_subject=n_topics * 2)
        db.session.add(ex); db.session.flush()
        st = Student(student_id=f'CDS{_SEQ[0]:03d}', first_name='C', surname='S',
                     gender='Male', is_active=True, branch_id=bid, jamb_subjects=subj.name)
        db.session.add(st); db.session.commit()
        return ex.id, st.id, subj.id, n_topics


def test_subject_items_partial_coding_reaches_full_cap(app):
    """End-to-end through subject_items(): half the pool coded, half not --
    the served count must still hit the exam's questions_per_subject cap."""
    from utils.mock_jamb_sitting import subject_items
    eid, sid, subj_id, n_topics = _bank_coded_subject(app, coded_fraction=0.5)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        items, served = subject_items(exam, subj_id, att)
        assert len(served) == n_topics * 2


def test_subject_items_fully_coded_spreads_across_topics(app):
    from utils.mock_jamb_sitting import subject_items
    eid, sid, subj_id, n_topics = _bank_coded_subject(app, coded_fraction=1.0)
    with app.app_context():
        exam = db.session.get(MockJAMBExam, eid)
        att = MockJAMBAttempt(mock_exam_id=eid, student_id=sid); db.session.add(att); db.session.flush()
        items, served = subject_items(exam, subj_id, att)
        assert len(served) == n_topics * 2
        qs = MockJAMBQuestion.query.filter(MockJAMBQuestion.id.in_(served)).all()
        topics = {q.syllabus_item_code for q in qs}
        assert len(topics) == n_topics  # every topic represented
