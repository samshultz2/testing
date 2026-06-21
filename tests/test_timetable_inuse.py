"""Timetable 'in use' marker: one active batch per (branch, level), replaceable."""
from models import db, ActiveTimetableBatch


def test_active_timetable_batch_marker(app):
    with app.app_context():
        ActiveTimetableBatch.set_active(None, 'sss', 'B1')
        db.session.commit()
        assert ActiveTimetableBatch.active_batch_id(None, 'sss') == 'B1'

        # Setting again replaces in place (no duplicate rows for the same scope).
        ActiveTimetableBatch.set_active(None, 'sss', 'B2')
        db.session.commit()
        assert ActiveTimetableBatch.active_batch_id(None, 'sss') == 'B2'
        assert ActiveTimetableBatch.query.filter_by(branch_id=None, school_level='sss').count() == 1

        # jss is tracked independently of sss.
        ActiveTimetableBatch.set_active(None, 'jss', 'J1')
        db.session.commit()
        assert ActiveTimetableBatch.active_batch_id(None, 'jss') == 'J1'
        assert ActiveTimetableBatch.active_batch_id(None, 'sss') == 'B2'
        assert ActiveTimetableBatch.active_batch_id(None, 'ss3') is None
