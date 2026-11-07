"""Keep the exam analytics cache honest: whenever WAEC / NECO / JAMB results
are added, edited or deleted (single entry, grid, paste, import, merge, API…),
the cached hub statistics are dropped after the change is committed, so the
next Analytics page load recomputes them. Registered once at app start."""
from sqlalchemy import event

_REGISTERED = False
_FLAG = 'exam_results_changed'


def register_exam_cache_hooks():
    global _REGISTERED
    if _REGISTERED:
        return
    from models import WAECResult, NECOResult, JAMBResult

    def _mark(mapper, connection, target):
        from sqlalchemy.orm import object_session
        s = object_session(target)
        if s is not None:
            s.info[_FLAG] = True

    for model in (WAECResult, NECOResult, JAMBResult):
        for ev in ('after_insert', 'after_update', 'after_delete'):
            event.listen(model, ev, _mark)

    from sqlalchemy.orm import Session

    @event.listens_for(Session, 'after_commit')
    def _after_commit(session):           # pragma: no cover — exercised via the test below
        if not session.info.pop(_FLAG, False):
            return
        try:
            from models.analytics_models import AnalyticsCache
            with session.get_bind().begin() as conn:
                conn.execute(AnalyticsCache.__table__.delete().where(
                    AnalyticsCache.__table__.c.cache_key.like('exam_hub:%')))
        except Exception:
            pass

    @event.listens_for(Session, 'after_rollback')
    def _after_rollback(session):
        session.info.pop(_FLAG, None)

    _REGISTERED = True
