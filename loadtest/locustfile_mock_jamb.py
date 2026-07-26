"""Mock-JAMB online sitting load test — REALISTIC single-cohort model.

Models a real exam, not a stampede:
  * students are SEATED gradually (locust spawn-rate = cohort / seating-window),
  * each opens the paper once (draws + caches it), then answers at a human pace
    (batched autosave + the occasional reload),
  * near their personal deadline each submits ONCE and leaves (StopUser), so the
    submits cluster at the end the way a real timer expiry does.

The run ends naturally when the last student submits. Drive it from the runner
(loadtest/run_mock_jamb.sh), which computes the spawn-rate + duration for you, or
directly:

    EXAM_ID=<id> EXAM_MINUTES=10 locust -f loadtest/locustfile_mock_jamb.py \
        --host https://<url> --headless -u 100 -r 0.8 -t 12m --csv out
"""
import csv
import itertools
import os
import random
import re
import threading
import time

from locust import HttpUser, task, between, events
from locust.exception import StopUser

EXAM_ID = os.environ.get('EXAM_ID')
EXAM_MINUTES = float(os.environ.get('EXAM_MINUTES', '10'))   # per-student exam length
_CSRF_META = re.compile(r'name="csrf-token" content="([0-9a-f]+)"')
_CSRF_INPUT = re.compile(r'name="_csrf_token" value="([0-9a-f]+)"')
_QID = re.compile(r'data-qid="(\d+)"')

_lock = threading.Lock()
_creds = None


def _load_creds():
    path = os.path.join(os.path.dirname(__file__), 'students.csv')
    with open(path) as fh:
        return [(r['student_id'], r['password']) for r in csv.DictReader(fh)]


@events.test_start.add_listener
def _on_start(environment, **kw):
    global _creds
    if not EXAM_ID:
        raise SystemExit('Set EXAM_ID (see loadtest/seed_mock_jamb.py / tenant_ctl.py).')
    _creds = itertools.cycle(_load_creds())


def _next():
    with _lock:
        return next(_creds)


class MockJambStudent(HttpUser):
    # think time between answering actions (a human reading + choosing)
    wait_time = between(4, 12)

    def on_start(self):
        self.qids = []
        self.started = False
        sid, pw = _next()
        page = self.client.get('/exam/login')
        m = _CSRF_INPUT.search(page.text) or _CSRF_META.search(page.text)
        tok = m.group(1) if m else ''
        self.client.post('/exam/login',
                         data={'student_id': sid, 'password': pw, '_csrf_token': tok},
                         name='/exam/login')
        sit = self.client.get(f'/exam/mock-jamb/{EXAM_ID}',
                              name='/exam/mock-jamb/[id] (open)')
        m = _CSRF_META.search(sit.text)
        self.csrf = m.group(1) if m else ''
        self.qids = list(dict.fromkeys(_QID.findall(sit.text)))
        self.started = bool(self.qids)
        # personal deadline: finish somewhere in the last ~15% of the window, so
        # submits cluster near the end (like a real timer) instead of all at once.
        self.deadline = time.time() + EXAM_MINUTES * 60 * random.uniform(0.85, 1.0)

    def _finish_if_due(self):
        if time.time() >= self.deadline:
            self.client.post(f'/exam/mock-jamb/{EXAM_ID}/submit',
                             data={'_csrf_token': self.csrf},
                             headers={'X-CSRFToken': self.csrf},
                             name='/exam/mock-jamb/[id]/submit')
            raise StopUser()          # done — this student leaves the hall

    @task(12)
    def autosave(self):
        if not self.started:
            raise StopUser()
        self._finish_if_due()
        picks = random.sample(self.qids, min(5, len(self.qids)))
        answers = ','.join(f'{q}:{random.choice("ABCD")}' for q in picks)
        self.client.post(f'/exam/mock-jamb/{EXAM_ID}/save-batch',
                         data={'answers': answers, '_csrf_token': self.csrf},
                         headers={'X-CSRFToken': self.csrf},
                         name='/exam/mock-jamb/[id]/save-batch')

    @task(2)
    def reload(self):
        if not self.started:
            raise StopUser()
        self._finish_if_due()
        self.client.get(f'/exam/mock-jamb/{EXAM_ID}',
                        name='/exam/mock-jamb/[id] (reload)')
