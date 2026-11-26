"""The control-plane (tenants) DB survives Postgres dropping connections, and
its schema check runs once per process rather than on every request."""
import pytest

from utils import tenancy


def test_postgres_control_plane_engine_pre_pings(monkeypatch):
    pytest.importorskip('psycopg')
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'postgresql+psycopg://u:p@127.0.0.1:1/x')
    tenancy._reset_engine()
    try:
        eng, _ = tenancy._engine_and_session()      # building the engine doesn't connect
        assert eng.pool._pre_ping is True
    finally:
        tenancy._reset_engine()


def test_schema_check_runs_once(monkeypatch, tmp_path):
    monkeypatch.setenv('CONTROL_PLANE_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'cp.db'))
    tenancy._reset_engine()
    calls = []
    real = tenancy._ensure_columns
    monkeypatch.setattr(tenancy, '_ensure_columns', lambda e: (calls.append(1), real(e)))
    try:
        for _ in range(3):
            tenancy.get_tenant('nobody')
        assert len(calls) == 1
        tenancy._reset_engine()                      # a repointed URL checks again
        tenancy.init_control_plane()
        assert len(calls) == 2
    finally:
        tenancy._reset_engine()
