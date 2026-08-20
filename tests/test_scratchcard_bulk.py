"""Scratch-card bulk management: enable/disable many at once, delete an explicit
selection, and rule-based delete (batch + status, oldest-first, capped by limit)
that preserves the check-log audit trail (card link is nulled, log kept).
"""
from config import Config
from tests.conftest import login_token, auth_csrf


def _cards(app, n, batch='BULK-T', active=True):
    from models import db, ScratchCard
    ids = []
    with app.app_context():
        for _ in range(n):
            c = ScratchCard.generate_unique(max_uses=5, batch_label=batch)
            c.is_active = active
            db.session.add(c); db.session.flush()
            ids.append(c.id)
        db.session.commit()
    return ids


def _login(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def test_bulk_toggle_disables_selected(app):
    from models import db, ScratchCard
    ids = _cards(app, 3, batch='BULK-TOG', active=True)
    try:
        c = _login(app)
        r = c.post('/scratch-cards/bulk-toggle',
                   data={'ids': ' '.join(map(str, ids)), 'active': '0',
                         '_csrf_token': auth_csrf(c)})
        assert r.status_code in (200, 302, 303)
        with app.app_context():
            rows = ScratchCard.query.filter(ScratchCard.id.in_(ids)).all()
            assert all(not x.is_active for x in rows)
    finally:
        with app.app_context():
            ScratchCard.query.filter(ScratchCard.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


def test_bulk_delete_explicit_ids_keeps_audit(app):
    from models import db, ScratchCard, ResultCheckLog
    ids = _cards(app, 2, batch='BULK-DEL')
    with app.app_context():
        log = ResultCheckLog(card_id=ids[0], success=True, detail='t')
        db.session.add(log); db.session.commit()
        log_id = log.id
    try:
        c = _login(app)
        r = c.post('/scratch-cards/bulk-delete',
                   data={'ids': ' '.join(map(str, ids)), '_csrf_token': auth_csrf(c)})
        assert r.status_code in (200, 302, 303)
        with app.app_context():
            assert ScratchCard.query.filter(ScratchCard.id.in_(ids)).count() == 0
            # Audit log survives with its card link cleared.
            kept = db.session.get(ResultCheckLog, log_id)
            assert kept is not None and kept.card_id is None
    finally:
        with app.app_context():
            ResultCheckLog.query.filter_by(id=log_id).delete()
            ScratchCard.query.filter(ScratchCard.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


def test_rule_delete_respects_limit(app):
    from models import db, ScratchCard
    ids = _cards(app, 5, batch='BULK-RULE')
    try:
        c = _login(app)
        r = c.post('/scratch-cards/bulk-delete',
                   data={'batch': 'BULK-RULE', 'limit': '2', '_csrf_token': auth_csrf(c)})
        assert r.status_code in (200, 302, 303)
        with app.app_context():
            left = ScratchCard.query.filter_by(batch_label='BULK-RULE').count()
            assert left == 3            # only 2 of 5 deleted (oldest first)
    finally:
        with app.app_context():
            ScratchCard.query.filter_by(batch_label='BULK-RULE').delete(synchronize_session=False)
            db.session.commit()
