"""CBT scale/perf plumbing: cache layer, job queue, answer-key cache + its
auto-invalidation, hot-path index, and the Redis monitoring metric."""
from utils import cache, jobqueue


# ── cache layer (no Redis → in-process fallback) ──────────────────────────────
def test_cache_fallback_roundtrip_and_gate():
    cache.reset_for_tests()
    assert cache.enabled() is False
    cache.set_json('k', {'a': 1}, ttl=30)
    assert cache.get_json('k') == {'a': 1}
    cache.delete('k')
    assert cache.get_json('k') is None
    # Rate gate: first caller in the window wins, the next is refused.
    assert cache.should_run('g', 60) is True
    assert cache.should_run('g', 60) is False


# ── job queue (no backend → inline/dropped) ───────────────────────────────────
def test_jobqueue_inline_and_drop():
    cache.reset_for_tests()
    seen = []
    jobqueue.register('unit_probe', lambda app, payload: seen.append(payload))
    # inline_fallback=True runs immediately when there's no Redis backend.
    assert jobqueue.enqueue('unit_probe', {'x': 1}) == 'inline'
    assert seen == [{'x': 1}]
    # best-effort work is dropped (never lands on the caller) without a backend.
    assert jobqueue.enqueue('unit_probe', {'x': 2}, inline_fallback=False) == 'dropped'
    assert seen == [{'x': 1}]
    # drain is a no-op with no backend (inline jobs already ran).
    assert jobqueue.drain(None) == 0


# ── answer-key cache + automatic invalidation ─────────────────────────────────
def _make_exam(db, CBTExam, CBTQuestion, correct='A'):
    exam = CBTExam(title='cache exam', is_published=True)
    db.session.add(exam)
    db.session.flush()
    q = CBTQuestion(exam_id=exam.id, question_text='q1', option_a='a', option_b='b',
                    option_c='c', option_d='d', correct_option=correct, order=1)
    db.session.add(q)
    db.session.commit()
    return exam, q


def test_answer_key_cached_and_invalidated_on_change(app):
    from routes.cbt import _exam_answer_key
    from models import db, CBTExam, CBTQuestion
    with app.app_context():
        cache.reset_for_tests()
        exam, q = _make_exam(db, CBTExam, CBTQuestion, correct='A')
        assert _exam_answer_key(exam.id) == {q.id: 'A'}
        # Changing the correct option must invalidate the cache via the event
        # listener, so the next read reflects the new key (no stale grading).
        q.correct_option = 'C'
        db.session.commit()
        assert _exam_answer_key(exam.id) == {q.id: 'C'}
        # Adding a question also invalidates.
        q2 = CBTQuestion(exam_id=exam.id, question_text='q2', correct_option='B', order=2)
        db.session.add(q2)
        db.session.commit()
        assert _exam_answer_key(exam.id) == {q.id: 'C', q2.id: 'B'}


# ── tenant namespacing (no cross-school cache collisions) ─────────────────────
def test_answer_key_is_tenant_namespaced(app, monkeypatch):
    """Two schools with the same exam id must not share a cached answer key."""
    import routes.cbt as cbtmod
    from models import db, CBTExam, CBTQuestion
    with app.app_context():
        cache.reset_for_tests()
        exam, q = _make_exam(db, CBTExam, CBTQuestion, correct='A')

        class _T:
            def __init__(self, sub):
                self.subdomain = sub
        # Namespace resolves to the active school; different schools → different key.
        monkeypatch.setattr(cbtmod, '_tns', lambda: 'schoolA')
        assert cbtmod._exam_answer_key(exam.id) == {q.id: 'A'}
        from utils import cache as _c
        assert _c.get_json(f'cbt:schoolA:key:{exam.id}') is not None
        # A different school's namespace has no entry for the same exam id.
        assert _c.get_json(f'cbt:schoolB:key:{exam.id}') is None


def test_jobqueue_captures_no_tenant_in_single_mode(app):
    """In single-school mode a queued job carries no tenant block (drain no-op)."""
    from utils import jobqueue
    with app.app_context():
        assert jobqueue._bind_tenant(None) is None   # tolerates missing tenant


# ── hot-path index present on a fresh DB ──────────────────────────────────────
def test_cbt_questions_exam_id_indexed(app):
    from models import db
    from sqlalchemy import inspect
    with app.app_context():
        names = {i['name'] for i in inspect(db.engine).get_indexes('cbt_questions')}
        assert 'ix_cbt_question_exam' in names


# ── Redis monitoring metric degrades gracefully ───────────────────────────────
def test_redis_metric_absent_without_backend(app):
    from utils import sys_metrics
    with app.app_context():
        cache.reset_for_tests()
        snap = sys_metrics.all_metrics()
        assert 'redis' in snap
        assert snap['redis']['available'] is False
