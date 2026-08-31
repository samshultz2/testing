"""HR Phase 2 — lifecycle events (promote / transfer / confirm / note) and the
merged employment timeline."""
import re
from datetime import date, timedelta

from config import Config
from models import db, StaffMember, StaffEvent, SalaryHistory, LeaveRecord, Branch
from tests.conftest import login_token


def _admin(app):
    client = app.test_client()
    token = login_token(client)
    client.post('/login', data={'password': Config.ADMIN_PASSWORD, '_csrf_token': token})
    return client


def _ptoken(client):
    html = client.get('/students').get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([0-9a-f]+)"', html)
    return m.group(1) if m else None


def _staff(app, tag, **kw):
    with app.app_context():
        s = StaffMember(staff_id=f'TL{tag}', first_name='Time', surname=f'Zz{tag}',
                        staff_type='Teaching', status='Active', is_active=True, **kw)
        db.session.add(s)
        db.session.commit()
        return s.id


def test_promote_updates_title_and_records_event(app):
    sid = _staff(app, 'PRO1', designation='Teacher', salary=80000)
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/hr/staff/{sid}/promote', headers={'X-Requested-With': 'fetch'},
                    data={'designation': 'Head of Department', 'new_salary': '120000',
                          'effective_date': date.today().isoformat(), '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        s = db.session.get(StaffMember, sid)
        assert s.designation == 'Head of Department'
        assert s.salary == 120000
        ev = StaffEvent.query.filter_by(staff_id=sid, kind='promotion').first()
        assert ev is not None and 'Head of Department' in ev.title
        # salary bump also captured in salary history
        assert SalaryHistory.query.filter_by(staff_id=sid).count() == 1


def test_promote_requires_title(app):
    sid = _staff(app, 'PRO2')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/hr/staff/{sid}/promote', headers={'X-Requested-With': 'fetch'},
                    data={'designation': '', '_csrf_token': tok})
    assert r.status_code == 400


def test_confirm_sets_date(app):
    sid = _staff(app, 'CNF1')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/hr/staff/{sid}/confirm', headers={'X-Requested-With': 'fetch'},
                    data={'effective_date': '2025-03-01', '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        assert db.session.get(StaffMember, sid).confirmation_date == date(2025, 3, 1)


def test_transfer_moves_branch_and_logs(app):
    with app.app_context():
        b1 = Branch.query.filter_by(name='TL Branch A').first() or Branch(name='TL Branch A', is_active=True)
        b2 = Branch.query.filter_by(name='TL Branch B').first() or Branch(name='TL Branch B', is_active=True)
        db.session.add_all([b1, b2])
        db.session.flush()
        s = StaffMember(staff_id='TLTRF1', first_name='Trans', surname='Zzfer',
                        branch_id=b1.id, is_active=True)
        db.session.add(s)
        db.session.commit()
        sid, dest = s.id, b2.id
    client = _admin(app)   # legacy admin login is central
    tok = _ptoken(client)
    r = client.post(f'/hr/staff/{sid}/transfer', headers={'X-Requested-With': 'fetch'},
                    data={'branch_id': dest, '_csrf_token': tok}).get_json()
    assert r['ok']
    with app.app_context():
        s = db.session.get(StaffMember, sid)
        assert s.branch_id == dest
        assert StaffEvent.query.filter_by(staff_id=sid, kind='transfer').count() == 1


def test_note_appears_on_timeline(app):
    sid = _staff(app, 'NOTE1')
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post(f'/hr/staff/{sid}/note', headers={'X-Requested-With': 'fetch'},
                    data={'title': 'Received Teacher of the Year',
                          'effective_date': date.today().isoformat(), '_csrf_token': tok}).get_json()
    assert r['ok']
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    assert '"timeline"' in html and 'Teacher of the Year' in html


def test_build_timeline_merges_sources(app):
    from utils import hr as hr_utils
    with app.app_context():
        s = StaffMember(staff_id='TLMRG1', first_name='Merge', surname='Zzsrc',
                        date_employed=date(2020, 9, 1), confirmation_date=date(2021, 9, 1),
                        is_active=True)
        db.session.add(s)
        db.session.flush()
        db.session.add(SalaryHistory(staff_id=s.id, previous_salary=50000, new_salary=70000,
                                     effective_date=date(2022, 1, 1), reason='Increment'))
        db.session.add(LeaveRecord(staff_id=s.id, leave_type='Annual',
                                   start_date=date(2023, 6, 1), end_date=date(2023, 6, 10),
                                   days=10, status='Approved'))
        db.session.add(StaffEvent(staff_id=s.id, kind='promotion', title='Promoted to VP',
                                  effective_date=date(2024, 1, 1)))
        db.session.commit()
        tl = hr_utils.build_timeline(s)
        kinds = [t['kind'] for t in tl]
        assert {'employment', 'confirmation', 'salary', 'leave', 'promotion'} <= set(kinds)
        # reverse chronological: newest first
        labels = [t['date_label'] for t in tl]
        assert labels[0].endswith('2024')
        assert all('date' not in t for t in tl)   # raw date stripped, label only
