"""HR reports — server-side builders for the reporting screen and CSV/Excel
export. Each builder returns a uniform {title, columns, rows, summary, type} so
the UI and exporter render any report the same way. All queries are branch-scoped
and honour the shared filters (branch/department/type/status/date range)."""
from __future__ import annotations

import datetime as _dt

from sqlalchemy import func

REPORTS = [
    ('directory', 'Staff Directory'),
    ('by_department', 'Staff by Department'),
    ('by_branch', 'Staff by Branch'),
    ('teaching', 'Teaching Staff'),
    ('non_teaching', 'Non-teaching Staff'),
    ('qualifications', 'Qualification Breakdown'),
    ('service_years', 'Years of Service'),
    ('birthdays', 'Upcoming Birthdays'),
    ('contracts', 'Contract Expiry'),
    ('retirement', 'Retirement Forecast'),
    ('leave', 'Leave Summary'),
    ('attendance', 'Attendance Summary'),
]
_LABELS = dict(REPORTS)

RETIREMENT_AGE = 60


def _staff_q(filters):
    from models import StaffMember
    from utils.branch_scope import scope_query
    q = scope_query(StaffMember.query.filter_by(is_active=True), StaffMember)
    if filters.get('department_id'):
        q = q.filter(StaffMember.department_id == filters['department_id'])
    if filters.get('staff_type'):
        q = q.filter(StaffMember.staff_type == filters['staff_type'])
    if filters.get('status'):
        q = q.filter(StaffMember.status == filters['status'])
    return q


def _dept_name_map():
    from models import Department
    return {d.id: d.name for d in Department.query.all()}


def _branch_name_map():
    from models import Branch
    return {b.id: b.name for b in Branch.query.all()}


def build(rtype, filters):
    fn = _BUILDERS.get(rtype) or _BUILDERS['directory']
    out = fn(filters)
    out['type'] = rtype if rtype in _LABELS else 'directory'
    out.setdefault('title', _LABELS.get(out['type'], 'Report'))
    out.setdefault('summary', [])
    return out


# ---- builders --------------------------------------------------------------

def _directory(filters):
    depts = _dept_name_map()
    rows = []
    for s in _staff_q(filters).order_by(_surname()).all():
        rows.append({'staff_id': s.staff_id or '', 'name': s.full_name,
                     'gender': s.gender or '', 'department': depts.get(s.department_id, ''),
                     'designation': s.designation or '', 'type': s.staff_type or '',
                     'status': s.status or '', 'phone': s.phone or '',
                     'employed': s.date_employed.strftime('%d %b %Y') if s.date_employed else ''})
    return {'columns': [
        {'key': 'staff_id', 'label': 'Staff ID'}, {'key': 'name', 'label': 'Name'},
        {'key': 'gender', 'label': 'Gender'}, {'key': 'department', 'label': 'Department'},
        {'key': 'designation', 'label': 'Designation'}, {'key': 'type', 'label': 'Type'},
        {'key': 'status', 'label': 'Status'}, {'key': 'phone', 'label': 'Phone'},
        {'key': 'employed', 'label': 'Employed'}],
        'rows': rows, 'summary': [{'label': 'Total staff', 'value': len(rows)}]}


def _grouped_count(filters, key_fn, label):
    counts = {}
    for s in _staff_q(filters).all():
        k = key_fn(s) or '—'
        counts[k] = counts.get(k, 0) + 1
    rows = [{'group': k, 'count': v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    return {'columns': [{'key': 'group', 'label': label}, {'key': 'count', 'label': 'Staff', 'align': 'right'}],
            'rows': rows, 'summary': [{'label': 'Groups', 'value': len(rows)},
                                      {'label': 'Total staff', 'value': sum(r['count'] for r in rows)}]}


def _by_department(filters):
    depts = _dept_name_map()
    out = _grouped_count(filters, lambda s: depts.get(s.department_id, 'Unassigned'), 'Department')
    out['title'] = 'Staff by Department'
    return out


def _by_branch(filters):
    branches = _branch_name_map()
    out = _grouped_count(filters, lambda s: branches.get(s.branch_id, 'Unassigned'), 'Branch')
    out['title'] = 'Staff by Branch'
    return out


def _teaching(filters):
    f = dict(filters, staff_type='Teaching')
    out = _directory(f)
    out['title'] = 'Teaching Staff'
    return out


def _non_teaching(filters):
    f = dict(filters, staff_type='Non-teaching')
    out = _directory(f)
    out['title'] = 'Non-teaching Staff'
    return out


def _qualifications(filters):
    out = _grouped_count(filters, lambda s: (s.qualification or 'Not recorded'), 'Qualification')
    out['title'] = 'Qualification Breakdown'
    return out


def _service_years(filters):
    depts = _dept_name_map()
    rows = []
    for s in _staff_q(filters).all():
        rows.append({'name': s.full_name, 'department': depts.get(s.department_id, ''),
                     'employed': s.date_employed.strftime('%d %b %Y') if s.date_employed else '',
                     'years': s.years_of_service, 'total_experience': s.total_experience_years})
    rows.sort(key=lambda r: -r['years'])
    avg = round(sum(r['years'] for r in rows) / len(rows), 1) if rows else 0
    return {'title': 'Years of Service', 'columns': [
        {'key': 'name', 'label': 'Name'}, {'key': 'department', 'label': 'Department'},
        {'key': 'employed', 'label': 'Employed'}, {'key': 'years', 'label': 'Years here', 'align': 'right'},
        {'key': 'total_experience', 'label': 'Total exp.', 'align': 'right'}],
        'rows': rows, 'summary': [{'label': 'Staff', 'value': len(rows)},
                                  {'label': 'Avg years of service', 'value': avg}]}


def _birthdays(filters):
    """Staff with a birthday in the next N days (default 30, or the from/to range)."""
    today = _dt.date.today()
    start = filters.get('from') or today
    end = filters.get('to') or (today + _dt.timedelta(days=30))
    window = max((end - start).days, 0)
    rows = []
    for s in _staff_q(filters).all():
        if not s.date_of_birth:
            continue
        # next occurrence of the birthday on/after start
        try:
            nxt = s.date_of_birth.replace(year=start.year)
        except ValueError:      # 29 Feb
            nxt = s.date_of_birth.replace(year=start.year, day=28)
        if nxt < start:
            try:
                nxt = s.date_of_birth.replace(year=start.year + 1)
            except ValueError:
                nxt = s.date_of_birth.replace(year=start.year + 1, day=28)
        if start <= nxt <= start + _dt.timedelta(days=window):
            rows.append({'name': s.full_name, 'date': nxt.strftime('%d %b'),
                         'turning': (nxt.year - s.date_of_birth.year),
                         'phone': s.phone or '', '_sort': nxt})
    rows.sort(key=lambda r: r['_sort'])
    for r in rows:
        r.pop('_sort', None)
    return {'title': 'Upcoming Birthdays', 'columns': [
        {'key': 'name', 'label': 'Name'}, {'key': 'date', 'label': 'Birthday'},
        {'key': 'turning', 'label': 'Turning', 'align': 'right'}, {'key': 'phone', 'label': 'Phone'}],
        'rows': rows, 'summary': [{'label': 'Birthdays in window', 'value': len(rows)}]}


def _contracts(filters):
    """Contract staff whose contract ends (or has ended) within the window."""
    today = _dt.date.today()
    horizon = filters.get('to') or (today + _dt.timedelta(days=90))
    rows = []
    for s in _staff_q(filters).all():
        if not s.contract_end:
            continue
        if s.contract_end <= horizon:
            rows.append({'name': s.full_name, 'type': s.employment_type or '',
                         'ends': s.contract_end.strftime('%d %b %Y'),
                         'days_left': (s.contract_end - today).days, '_sort': s.contract_end})
    rows.sort(key=lambda r: r['_sort'])
    for r in rows:
        r.pop('_sort', None)
    return {'title': 'Contract Expiry', 'columns': [
        {'key': 'name', 'label': 'Name'}, {'key': 'type', 'label': 'Employment'},
        {'key': 'ends', 'label': 'Contract ends'}, {'key': 'days_left', 'label': 'Days left', 'align': 'right'}],
        'rows': rows, 'summary': [{'label': 'Contracts ending', 'value': len(rows)}]}


def _retirement(filters):
    """Forecast of staff reaching the retirement age within ~5 years."""
    today = _dt.date.today()
    rows = []
    for s in _staff_q(filters).all():
        if not s.date_of_birth:
            continue
        retire_year = s.date_of_birth.year + RETIREMENT_AGE
        years_to = retire_year - today.year
        if years_to <= 5:
            rows.append({'name': s.full_name, 'age': s.age,
                         'retires': str(retire_year), 'years_to': years_to, '_sort': years_to})
    rows.sort(key=lambda r: r['_sort'])
    for r in rows:
        r.pop('_sort', None)
    return {'title': 'Retirement Forecast', 'columns': [
        {'key': 'name', 'label': 'Name'}, {'key': 'age', 'label': 'Age', 'align': 'right'},
        {'key': 'retires', 'label': 'Retires (yr)'}, {'key': 'years_to', 'label': 'Years to', 'align': 'right'}],
        'rows': rows, 'summary': [{'label': 'Within 5 years', 'value': len(rows)}]}


def _leave(filters):
    from models import LeaveRecord, StaffMember
    from utils.branch_scope import scope_by_staff
    from sqlalchemy import extract
    year = _dt.date.today().year
    q = scope_by_staff(LeaveRecord.query.filter(LeaveRecord.status == 'Approved',
                       extract('year', LeaveRecord.start_date) == year), LeaveRecord)
    agg = {}
    for lv in q.all():
        s = lv.staff
        if filters.get('department_id') and (not s or s.department_id != filters['department_id']):
            continue
        key = lv.staff_id
        d = agg.setdefault(key, {'name': s.full_name if s else '—', 'days': 0, 'requests': 0})
        d['days'] += (lv.days or 0)
        d['requests'] += 1
    rows = sorted(agg.values(), key=lambda r: -r['days'])
    return {'title': f'Leave Summary ({year})', 'columns': [
        {'key': 'name', 'label': 'Name'}, {'key': 'requests', 'label': 'Requests', 'align': 'right'},
        {'key': 'days', 'label': 'Days taken', 'align': 'right'}],
        'rows': rows, 'summary': [{'label': 'Staff on leave', 'value': len(rows)},
                                  {'label': 'Total days', 'value': sum(r['days'] for r in rows)}]}


def _attendance(filters):
    from models import StaffAttendance, StaffMember
    from utils.branch_scope import scope_by_staff
    start = filters.get('from') or _dt.date.today().replace(day=1)
    end = filters.get('to') or _dt.date.today()
    q = scope_by_staff(StaffAttendance.query.filter(
        StaffAttendance.date >= start, StaffAttendance.date <= end), StaffAttendance)
    agg = {}
    for a in q.all():
        s = a.staff
        if filters.get('department_id') and (not s or s.department_id != filters['department_id']):
            continue
        d = agg.setdefault(a.staff_id, {'name': s.full_name if s else '—',
                                        'present': 0, 'late': 0, 'absent': 0, 'deduction': 0.0})
        key = (a.status or 'Present').lower()
        if key in d:
            d[key] += 1
        d['deduction'] += (a.deduction or 0)
    rows = sorted(agg.values(), key=lambda r: (-r['absent'], -r['late']))
    for r in rows:
        r['deduction'] = round(r['deduction'], 2)
    return {'title': 'Attendance Summary', 'columns': [
        {'key': 'name', 'label': 'Name'}, {'key': 'present', 'label': 'Present', 'align': 'right'},
        {'key': 'late', 'label': 'Late', 'align': 'right'}, {'key': 'absent', 'label': 'Absent', 'align': 'right'},
        {'key': 'deduction', 'label': 'Deductions', 'align': 'right', 'money': True}],
        'rows': rows, 'summary': [{'label': 'Staff', 'value': len(rows)},
                                  {'label': 'Total deductions', 'value': round(sum(r['deduction'] for r in rows), 2)}]}


def _surname():
    from models import StaffMember
    return StaffMember.surname


_BUILDERS = {
    'directory': _directory, 'by_department': _by_department, 'by_branch': _by_branch,
    'teaching': _teaching, 'non_teaching': _non_teaching, 'qualifications': _qualifications,
    'service_years': _service_years, 'birthdays': _birthdays, 'contracts': _contracts,
    'retirement': _retirement, 'leave': _leave, 'attendance': _attendance,
}
