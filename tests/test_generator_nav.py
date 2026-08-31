"""The timetable-generator level dashboard should surface every settings page —
so nothing is reachable only by typing a URL. Locks in the discoverability of
the generation rules, per-class subjects/periods, clash & combined rules, rooms,
periods & times, print/header details, reports and the setup checklist.
"""
from config import Config
from tests.conftest import login_token


def _admin(app):
    c = app.test_client()
    c.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': login_token(c)})
    return c


def _links(app, level):
    c = _admin(app)
    r = c.get(f'/generator/level/{level}')
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


EXPECTED = [
    '/generator/rules',            # generation rules
    '/generator/class-subjects',   # per-class subjects & periods
    '/generator/clash-rules',      # clash & combined-class rules
    '/generator/rooms',            # rooms / venues
    '/generator/settings',         # print / header details
    '/generator/reports',          # reports & validation
    '/generator/setup',            # setup checklist / guide
]


def test_sss_dashboard_surfaces_every_setting(app):
    body = _links(app, 'sss')
    for href in EXPECTED + ['/generator/streams']:
        assert href in body, f'SSS dashboard missing link to {href}'


def test_jss_dashboard_surfaces_every_setting(app):
    body = _links(app, 'jss')
    for href in EXPECTED:
        assert href in body, f'JSS dashboard missing link to {href}'
