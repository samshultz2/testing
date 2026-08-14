"""Platform monitoring metrics: the in-process collectors and the snapshot."""
from utils import sys_metrics


def test_request_collector_tracks_latency_and_users():
    sys_metrics._LATENCIES.clear()
    sys_metrics._ACTIVE.clear()
    for d in (10, 20, 30, 40, 200):
        sys_metrics.record_request(d)
    sys_metrics.touch_user('u:1')
    sys_metrics.touch_user('u:2')
    sys_metrics.touch_user('u:1')          # same user again → still 1 distinct
    m = sys_metrics.request_metrics()
    assert m['count'] == 5
    assert m['avg_ms'] == 60.0
    assert m['p95_ms'] >= m['p50_ms']
    assert m['concurrent_users'] == 2


def test_record_job_shows_in_snapshot():
    sys_metrics.record_job('scheduled_tick', 12.4)
    m = sys_metrics.request_metrics()
    assert 'scheduled_tick' in m['jobs']
    assert m['jobs']['scheduled_tick']['ms'] == 12


def test_all_metrics_structure(app):
    with app.app_context():
        snap = sys_metrics.all_metrics()
    assert set(snap) >= {'system', 'postgres', 'requests', 'at'}
    assert 'available' in snap['system']            # psutil present or gracefully False
    assert 'available' in snap['postgres']          # SQLite in tests → not PostgreSQL
    assert snap['postgres']['available'] is False   # test DB is SQLite
