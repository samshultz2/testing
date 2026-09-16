"""HR Phase 1 — richer employment fields + the cross-module profile hub
(teaching load, attendance summary, leave balance surfaced on one profile)."""
import re
from datetime import date, timedelta

from config import Config
from models import (db, StaffMember, Department, LeaveRecord, StaffAttendance,
                    User, Teacher, TeacherSubjectAssignment, TeacherClassAssignment,
                    Subject, SchoolClass, ClassArm, ClassArmAssignment, AcademicSession, Term)
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


# --- richer fields round-trip ----------------------------------------------
def test_new_employment_fields_persist(app):
    client = _admin(app)
    tok = _ptoken(client)
    r = client.post('/hr/staff/add', headers={'X-Requested-With': 'fetch'}, data={
        'first_name': 'Tunde', 'surname': 'Bakare', 'staff_type': 'Teaching',
        'employment_type': 'Contract', 'salary': '90000',
        'confirmation_date': '2024-01-15', 'contract_start': '2023-09-01',
        'contract_end': '2026-08-31', 'prior_experience_years': '5',
        'certifications': 'TRCN', 'tax_id': 'TIN-9988', 'pension_pin': 'PEN-1234',
        'pension_provider': 'Stanbic PFA', 'blood_group': 'O+',
        'emergency_name': 'Bisi Bakare', 'emergency_phone': '08030000000',
        'medical_notes': 'Asthmatic', '_csrf_token': tok,
    }).get_json()
    assert r['ok']
    with app.app_context():
        s = StaffMember.query.filter_by(first_name='Tunde', surname='Bakare').first()
        assert s.confirmation_date == date(2024, 1, 15)
        assert s.contract_end == date(2026, 8, 31)
        assert s.prior_experience_years == 5
        assert s.certifications == 'TRCN'
        assert s.tax_id == 'TIN-9988'          # encrypted at rest, decrypts back
        assert s.pension_provider == 'Stanbic PFA'
        assert s.blood_group == 'O+'
        assert s.emergency_name == 'Bisi Bakare'
        assert s.medical_notes == 'Asthmatic'


def test_years_of_service_and_contract_days(app):
    with app.app_context():
        s = StaffMember(staff_id='SVC1', first_name='Ola', surname='Svc',
                        date_employed=date.today() - timedelta(days=800),
                        contract_end=date.today() + timedelta(days=20))
        db.session.add(s)
        db.session.commit()
        assert s.years_of_service == 2
        assert 19 <= s.contract_days_left <= 21


def test_profile_detail_exposes_hub_keys(app):
    with app.app_context():
        s = StaffMember(staff_id='HUB1', first_name='Hub', surname='Zztest',
                        staff_type='Non-teaching', status='Active', is_active=True)
        db.session.add(s)
        db.session.commit()
        sid = s.id
    client = _admin(app)
    html = client.get(f'/hr/staff/{sid}').get_data(as_text=True)
    assert '"page": "staff_detail"' in html
    for key in ('"attendance_summary"', '"leave_summary"', '"teaching_load"', '"attendance_month"'):
        assert key in html


# --- attendance + leave summaries -------------------------------------------
def test_attendance_and_leave_summary(app):
    from utils import hr as hr_utils
    with app.app_context():
        s = StaffMember(staff_id='SUM1', first_name='Sum', surname='Zzmary',
                        status='Active', is_active=True)
        db.session.add(s)
        db.session.flush()
        today = date.today()
        db.session.add_all([
            StaffAttendance(staff_id=s.id, date=today, status='Present'),
            StaffAttendance(staff_id=s.id, date=today - timedelta(days=1), status='Late',
                            deduction=50),
        ])
        db.session.add(LeaveRecord(staff_id=s.id, leave_type='Annual',
                                   start_date=date(today.year, 1, 5),
                                   end_date=date(today.year, 1, 9), days=5, status='Approved'))
        db.session.add(LeaveRecord(staff_id=s.id, leave_type='Sick',
                                   start_date=today, end_date=today, days=1, status='Pending'))
        db.session.commit()
        att = hr_utils.attendance_summary(s.id, today.year, today.month)
        # the Late row may fall in the previous month at a month boundary; assert
        # only on the same-month Present mark to stay deterministic.
        assert att['present'] >= 1
        lv = hr_utils.leave_summary(s.id, today.year)
        assert lv['total_days'] == 5 and lv['by_type']['Annual'] == 5
        assert lv['pending'] == 1


def test_teaching_load_resolves_via_user_teacher(app):
    from utils import hr as hr_utils
    with app.app_context():
        ssn = AcademicSession.query.filter_by(is_active=True).first() or \
            AcademicSession(name='HUBSSN', is_active=True)
        db.session.add(ssn); db.session.flush()
        term = Term.query.filter_by(is_active=True).first() or \
            Term(session_id=ssn.id, term_number=1, name='T1', is_active=True)
        db.session.add(term); db.session.flush()
        cls = SchoolClass.query.filter_by(name='JSS2').first() or SchoolClass(name='JSS2', level=2)
        db.session.add(cls); db.session.flush()
        arm = ClassArm.query.first() or ClassArm(name='A', is_active=True)
        db.session.add(arm); db.session.flush()
        caa = ClassArmAssignment.query.filter_by(class_id=cls.id, term_id=term.id).first() or \
            ClassArmAssignment(class_id=cls.id, arm_id=arm.id, term_id=term.id)
        db.session.add(caa); db.session.flush()
        subj = Subject.query.filter_by(name='Basic Science').first() or Subject(name='Basic Science')
        db.session.add(subj); db.session.flush()
        u = User(username='hubteacher', full_name='Hub Teacher', role='teacher',
                 password_hash='x', is_active=True)
        db.session.add(u); db.session.flush()
        t = Teacher(user_id=u.id, employee_id='TCHHUB', is_active=True)
        db.session.add(t); db.session.flush()
        db.session.add(TeacherSubjectAssignment(teacher_id=t.id, class_arm_assignment_id=caa.id,
                                                subject_id=subj.id, is_active=True))
        db.session.add(TeacherClassAssignment(teacher_id=t.id, class_arm_assignment_id=caa.id,
                                              is_form_teacher=True, is_active=True))
        s = StaffMember(staff_id='TCHSTF1', first_name='Hub', surname='Teacher',
                        staff_type='Teaching', user_id=u.id, is_active=True)
        db.session.add(s); db.session.commit()

        load = hr_utils.teaching_load(s)
        assert load and load['is_teacher']
        assert load['subject_count'] >= 1
        assert any('Basic Science' == x['subject'] for x in load['subjects'])
        assert load['form_classes']  # is a form teacher of at least one class


def test_teaching_load_none_for_unlinked_staff(app):
    from utils import hr as hr_utils
    with app.app_context():
        s = StaffMember(staff_id='NOLNK1', first_name='No', surname='Link', is_active=True)
        db.session.add(s); db.session.commit()
        assert hr_utils.teaching_load(s) is None


# --- lateness breakdown ------------------------------------------------------
def test_late_days_breakdown_returns_day_rows_and_totals(app):
    from utils import hr as hr_utils
    with app.app_context():
        s = StaffMember(staff_id='LATE1', first_name='Late', surname='Zztest', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add_all([
            StaffAttendance(staff_id=s.id, date=date(2025, 3, 3), status='Late',
                            clock_in='07:45', minutes_late=15, deduction=150),
            StaffAttendance(staff_id=s.id, date=date(2025, 3, 10), status='Late',
                            clock_in='08:05', minutes_late=35, deduction=350),
            # a Present day and an Absent day in the same month must NOT appear
            StaffAttendance(staff_id=s.id, date=date(2025, 3, 4), status='Present'),
            StaffAttendance(staff_id=s.id, date=date(2025, 3, 5), status='Absent', deduction=500),
            # a different month must not leak in
            StaffAttendance(staff_id=s.id, date=date(2025, 4, 1), status='Late',
                            clock_in='08:00', minutes_late=30, deduction=300),
        ])
        db.session.commit()
        out = hr_utils.late_days_breakdown(s.id, 2025, 3)
        assert out['days_late'] == 2
        assert [d['date'] for d in out['days']] == ['2025-03-03', '2025-03-10']  # ordered
        assert out['days'][0] == {'date': '2025-03-03', 'date_label': 'Mon, 03 Mar',
                                  'clock_in': '07:45', 'minutes_late': 15, 'deduction': 150}
        assert out['total_minutes'] == 50
        assert out['total_deduction'] == 500.0


def test_late_days_breakdown_empty_month(app):
    from utils import hr as hr_utils
    with app.app_context():
        s = StaffMember(staff_id='LATE2', first_name='Never', surname='Late', is_active=True)
        db.session.add(s); db.session.commit()
        out = hr_utils.late_days_breakdown(s.id, 2025, 3)
        assert out == {'days': [], 'days_late': 0, 'total_minutes': 0, 'total_deduction': 0}


def test_staff_detail_lateness_defaults_to_last_month_and_honours_ym(app):
    with app.app_context():
        s = StaffMember(staff_id='LATE3', first_name='Detail', surname='Zzlate', is_active=True)
        db.session.add(s); db.session.flush()
        db.session.add(StaffAttendance(staff_id=s.id, date=date(2025, 6, 12), status='Late',
                                       clock_in='08:10', minutes_late=40, deduction=400))
        db.session.commit()
        sid = s.id
    client = _admin(app)
    # Explicit ?ym= picks that month regardless of "today".
    r = client.get(f'/hr/staff/{sid}?ym=2025-06')
    html = r.get_data(as_text=True)
    assert '"late_breakdown_ym": "2025-06"' in html
    assert '"minutes_late": 40' in html and '"deduction": 400.0' in html
    assert '"total_minutes": 40' in html

    # No ?ym= at all -> defaults to LAST month relative to real today, not
    # this month and not the month we just seeded data for.
    from utils import timeutil
    today = timeutil.today()
    last_y, last_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    expected_ym = f'{last_y:04d}-{last_m:02d}'
    r2 = client.get(f'/hr/staff/{sid}')
    assert f'"late_breakdown_ym": "{expected_ym}"' in r2.get_data(as_text=True)
