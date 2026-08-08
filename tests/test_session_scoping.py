"""External-exam pages follow the active / time-travelled academic session.

resolve_exam_year() is the single rule the WAEC/JAMB dashboards and analytics use
to choose which exam year to show; these tests pin its behaviour."""
import utils.helpers as H


class _S:
    def __init__(self, name):
        self.name = name
        self.start_date = None
        self.end_date = None


def test_session_exam_year_parses_second_year():
    assert H.session_exam_year(_S('2025/2026')) == 2026
    assert H.session_exam_year(_S('2023/2024')) == 2024
    assert H.session_exam_year(_S('2026')) == 2026
    assert H.session_exam_year(_S('')) is None


def test_live_session_defaults_to_its_year(monkeypatch):
    monkeypatch.setattr(H, 'view_session_override', lambda: None)
    monkeypatch.setattr(H, 'get_active_session', lambda: _S('2025/2026'))
    # no explicit year → the live session's exam year (when it has data)
    assert H.resolve_exam_year(None, [2026, 2025, 2024]) == 2026
    # an explicit ?year still wins on the live session (deliberate exploration)
    assert H.resolve_exam_year(2024, [2026, 2025, 2024]) == 2024
    # session year has no data yet → fall back to the most recent year with data
    assert H.resolve_exam_year(None, [2025, 2024]) == 2025


def test_time_travel_locks_to_viewed_session(monkeypatch):
    viewed = _S('2019/2020')
    monkeypatch.setattr(H, 'view_session_override', lambda: viewed)
    monkeypatch.setattr(H, 'get_active_session', lambda: viewed)
    # while time-travelling, the viewed session's year wins — even over ?year
    assert H.resolve_exam_year(2026, [2026, 2025]) == 2020
    assert H.resolve_exam_year(None, [2026, 2025]) == 2020


def test_no_session_falls_back_to_latest_year(monkeypatch):
    monkeypatch.setattr(H, 'view_session_override', lambda: None)
    monkeypatch.setattr(H, 'get_active_session', lambda: None)
    assert H.resolve_exam_year(None, [2026, 2025]) == 2026
    assert H.resolve_exam_year(None, []) is None
