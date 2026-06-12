"""
CBT load test — simulates the full exam flow for many concurrent students:
login -> start -> take -> batched answer autosave -> heartbeat -> submit.

Setup once (against staging):  python loadtest/seed_loadtest.py
Then:                          EXAM_ID=<id> ACCESS_PASSWORD=<pw> \
                               locust -f loadtest/locustfile.py --host https://your-url

Open http://localhost:8089, set users (e.g. 800) and spawn rate, and watch
failure rate / response times. Validate on the actual VPS, not your laptop.
"""
import csv
import itertools
import os
import random
import re
import threading

from locust import HttpUser, task, between, events

EXAM_ID = os.environ.get('EXAM_ID')
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'exam123')
_CSRF_RE = re.compile(r'name="csrf-token" content="([0-9a-f]+)"')
_CSRF_INPUT_RE = re.compile(r'name="_csrf_token" value="([0-9a-f]+)"')
_QID_RE = re.compile(r'name="q_(\d+)"')

# Round-robin over the seeded credentials so each simulated user is a real login.
_lock = threading.Lock()
_creds_cycle = None


def _load_creds():
    path = os.path.join(os.path.dirname(__file__), 'students.csv')
    with open(path) as fh:
        return [(r['student_id'], r['password']) for r in csv.DictReader(fh)]


@events.test_start.add_listener
def _on_start(environment, **kw):
    global _creds_cycle
    if not EXAM_ID:
        raise SystemExit('Set EXAM_ID (see loadtest/seed_loadtest.py output).')
    _creds_cycle = itertools.cycle(_load_creds())


def _next_cred():
    with _lock:
        return next(_creds_cycle)


class Student(HttpUser):
    wait_time = between(3, 8)   # students think between actions

    def on_start(self):
        self.qids = []
        self.started = False
        sid, pw = _next_cred()
        # login
        page = self.client.get('/exam/login')
        m = _CSRF_INPUT_RE.search(page.text) or _CSRF_RE.search(page.text)
        tok = m.group(1) if m else ''
        self.client.post('/exam/login',
                         data={'student_id': sid, 'password': pw, '_csrf_token': tok},
                         name='/exam/login')
        # start the exam (access password gate)
        sp = self.client.get(f'/exam/{EXAM_ID}/start')
        m = _CSRF_RE.search(sp.text) or _CSRF_INPUT_RE.search(sp.text)
        tok = m.group(1) if m else ''
        self.client.post(f'/exam/{EXAM_ID}/start',
                         data={'access_password': ACCESS_PASSWORD, '_csrf_token': tok},
                         name='/exam/[id]/start')
        # load the take page; grab CSRF + question ids
        take = self.client.get(f'/exam/{EXAM_ID}/take', name='/exam/[id]/take')
        m = _CSRF_RE.search(take.text)
        self.csrf = m.group(1) if m else ''
        self.qids = list(dict.fromkeys(_QID_RE.findall(take.text)))
        self.started = bool(self.qids)

    def _post(self, path, data, name):
        data = dict(data); data['_csrf_token'] = self.csrf
        return self.client.post(path, data=data, name=name,
                                headers={'X-CSRFToken': self.csrf})

    @task(10)
    def answer_batch(self):
        if not self.started:
            return
        # answer a handful of questions in one batched request
        picks = random.sample(self.qids, min(5, len(self.qids)))
        data = {f'q_{q}': random.choice('ABCD') for q in picks}
        self._post(f'/exam/{EXAM_ID}/answers', data, '/exam/[id]/answers')

    @task(4)
    def heartbeat(self):
        if not self.started:
            return
        self._post(f'/exam/{EXAM_ID}/ping', {}, '/exam/[id]/ping')

    @task(1)
    def submit(self):
        if not self.started:
            return
        data = {f'q_{q}': random.choice('ABCD') for q in self.qids}
        self._post(f'/exam/{EXAM_ID}/submit', data, '/exam/[id]/submit')
        self.started = False
        # re-enter for continued load
        self.on_start()
