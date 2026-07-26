"""Mock-JAMB online sitting load test — the full student flow against the real
routes we hardened for a mass start:

    login (/exam/login) -> open sitting (/exam/mock-jamb/<id>, draws + caches the
    paper) -> loop: batched answer autosave (/save-batch) -> occasional submit.

Setup once (against staging):  N=1000 python loadtest/seed_mock_jamb.py
Then:                          EXAM_ID=<id> locust -f loadtest/locustfile_mock_jamb.py \
                               --host https://<staging-url>

Open http://localhost:8089, set users (e.g. 1000) + spawn rate (e.g. 40/s), and
watch failure % and p95. Run on the actual VPS, not a laptop.
"""
import csv
import itertools
import os
import random
import re
import threading

from locust import HttpUser, task, between, events

EXAM_ID = os.environ.get('EXAM_ID')
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
        raise SystemExit('Set EXAM_ID (see loadtest/seed_mock_jamb.py output).')
    _creds = itertools.cycle(_load_creds())


def _next():
    with _lock:
        return next(_creds)


class MockJambStudent(HttpUser):
    wait_time = between(3, 9)          # students think between actions

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
        # open the sitting: this draws + caches the paper and renders the page
        sit = self.client.get(f'/exam/mock-jamb/{EXAM_ID}', name='/exam/mock-jamb/[id] (open)')
        m = _CSRF_META.search(sit.text)
        self.csrf = m.group(1) if m else ''
        self.qids = list(dict.fromkeys(_QID.findall(sit.text)))
        self.started = bool(self.qids)

    @task(12)
    def autosave(self):
        if not self.started:
            return
        picks = random.sample(self.qids, min(5, len(self.qids)))
        answers = ','.join(f'{q}:{random.choice("ABCD")}' for q in picks)
        self.client.post(f'/exam/mock-jamb/{EXAM_ID}/save-batch',
                         data={'answers': answers, '_csrf_token': self.csrf},
                         headers={'X-CSRFToken': self.csrf},
                         name='/exam/mock-jamb/[id]/save-batch')

    @task(3)
    def reload(self):
        # a resume/refresh — should be cheap (paper served from the cache)
        if not self.started:
            return
        self.client.get(f'/exam/mock-jamb/{EXAM_ID}', name='/exam/mock-jamb/[id] (reload)')

    @task(1)
    def submit(self):
        if not self.started:
            return
        self.client.post(f'/exam/mock-jamb/{EXAM_ID}/submit',
                         data={'_csrf_token': self.csrf},
                         headers={'X-CSRFToken': self.csrf},
                         name='/exam/mock-jamb/[id]/submit')
        self.started = False
        self.on_start()               # re-enter for continued load
