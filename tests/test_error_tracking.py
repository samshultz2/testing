"""Error tracking: persists across restarts and alerts on server errors."""
import os

import utils.error_tracking as et


def _use_tmp_log(monkeypatch, tmp_path):
    from config import Config
    path = str(tmp_path / 'errors.jsonl')
    monkeypatch.setattr(Config, 'ERROR_LOG_FILE', path, raising=False)
    et._writes_since_trim = 0
    et._last_alert_ts = 0.0
    return path


def test_errors_persist_to_file(app, monkeypatch, tmp_path):
    path = _use_tmp_log(monkeypatch, tmp_path)
    et.record_error('server', 'boom', where='GET /x', user='admin', detail='trace')
    assert os.path.exists(path)
    rows = et.recent_errors(50)
    assert rows and rows[0]['message'] == 'boom' and rows[0]['where'] == 'GET /x'


def test_recent_errors_survive_buffer_loss(app, monkeypatch, tmp_path):
    """recent_errors reads the file, so a fresh process (empty buffer) still
    sees history written before a restart."""
    _use_tmp_log(monkeypatch, tmp_path)
    et.record_error('server', 'persisted-1')
    et._recent.clear()                       # simulate a restart (memory gone)
    rows = et.recent_errors(50)
    assert any(r['message'] == 'persisted-1' for r in rows)


def test_file_trim_caps_size(app, monkeypatch, tmp_path):
    path = _use_tmp_log(monkeypatch, tmp_path)
    from config import Config
    monkeypatch.setattr(Config, 'ERROR_LOG_MAX', 50, raising=False)
    # Trimming runs every 200 writes, so the file stays bounded by cap + the
    # trim interval rather than growing without limit.
    for i in range(460):
        et.record_error('client', f'e{i}')
    with open(path) as f:
        assert len(f.readlines()) <= 50 + 200


def test_server_error_emails_alert_throttled(app, monkeypatch, tmp_path):
    _use_tmp_log(monkeypatch, tmp_path)
    from config import Config
    monkeypatch.setattr(Config, 'ALERT_EMAIL', 'ops@test', raising=False)
    monkeypatch.setattr(Config, 'ERROR_ALERT_MIN_INTERVAL', 900, raising=False)
    from utils import mailer
    sent = []
    monkeypatch.setattr(mailer, 'is_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send_email_async',
                        lambda to, s, b, html=None: sent.append((to, s)))
    et.record_error('server', 'first error')
    et.record_error('server', 'second error')   # within throttle window
    assert len(sent) == 1                        # only one alert sent
    assert sent[0][0] == ['ops@test']


def test_client_errors_do_not_alert(app, monkeypatch, tmp_path):
    _use_tmp_log(monkeypatch, tmp_path)
    from config import Config
    monkeypatch.setattr(Config, 'ALERT_EMAIL', 'ops@test', raising=False)
    from utils import mailer
    sent = []
    monkeypatch.setattr(mailer, 'is_configured', lambda: True)
    monkeypatch.setattr(mailer, 'send_email_async',
                        lambda *a, **k: sent.append(a))
    et.record_error('client', 'js blew up')
    assert sent == []
