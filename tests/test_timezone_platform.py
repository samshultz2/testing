"""Platform time follows the configured school timezone.

Two guarantees:
  1. Functional — timeutil.now()/today() and the models' local_now() helper both
     track the SchoolSettings 'timezone' value (changing it moves the clock).
  2. Regression guard — application code does not read the server wall clock
     directly (date.today() / datetime.now()); every "now"/"today" must go
     through timeutil (or local_now in models), so a school in any zone gets
     its own local dates. A small allow-list covers the timeutil source itself
     and ops/diagnostics that intentionally use server/UTC time.
"""
import os
import re
import pytest
from models import db, SchoolSettings
from utils import timeutil


@pytest.fixture()
def _restore_tz(app):
    yield
    with app.app_context():
        SchoolSettings.set('timezone', 'Africa/Lagos', 'string', 'Site-wide timezone')
        timeutil.clear_cache()


def test_today_follows_configured_timezone(app, _restore_tz):
    """Kiritimati (UTC+14) and Pago Pago (UTC-11) are 25h apart, so their local
    calendar date always differs — proving today() reads the setting."""
    with app.app_context():
        SchoolSettings.set('timezone', 'Pacific/Kiritimati', 'string', 'tz')
        timeutil.clear_cache()
        far_ahead = timeutil.today()

        SchoolSettings.set('timezone', 'Pacific/Pago_Pago', 'string', 'tz')
        timeutil.clear_cache()
        far_behind = timeutil.today()

        assert far_ahead > far_behind          # 25h apart → later calendar date


def test_models_local_now_follows_configured_timezone(app, _restore_tz):
    """The models' local_now() helper (which the model date properties now use
    instead of date.today()) also tracks the setting."""
    from models import local_now
    with app.app_context():
        SchoolSettings.set('timezone', 'Pacific/Kiritimati', 'string', 'tz')
        timeutil.clear_cache()
        assert local_now().date() == timeutil.today()


# --- Regression guard: no raw server-clock reads in application code ---------

_RAW = re.compile(r'(?<![.\w])(date\.today|datetime\.now)\(\)')

# Intentional server/UTC time, or the timezone source itself.
_ALLOW = {
    os.path.join('utils', 'timeutil.py'),          # defines now()/today()
    os.path.join('utils', 'perf_logging.py'),      # ops diagnostics timestamps
    os.path.join('utils', 'backup.py'),            # backup filenames (stable clock)
    os.path.join('models', 'models', '__init__.py'),  # local_now() fallback only
}


def _iter_py(root):
    for base, _dirs, files in os.walk(root):
        if '__pycache__' in base:
            continue
        for name in files:
            if name.endswith('.py'):
                yield os.path.join(base, name)


def test_no_raw_server_clock_in_app_code():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    for root in ('routes', 'utils', 'models'):
        for path in _iter_py(os.path.join(repo, root)):
            rel = os.path.relpath(path, repo)
            if rel in _ALLOW:
                continue
            for i, line in enumerate(open(path, encoding='utf-8'), 1):
                if _RAW.search(line):
                    offenders.append(f'{rel}:{i}: {line.strip()}')
    assert not offenders, (
        "Use timeutil.today()/now() (or local_now() in models) so time follows "
        "the school timezone. Raw server-clock reads found:\n" + '\n'.join(offenders))
