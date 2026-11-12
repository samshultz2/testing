"""WAEC candidate (examination) numbers.

A WASSCE school candidate's examination number is 10 digits: the school's
7-digit centre number followed by a 3-digit candidate number (001, 002, …).
Schools number their candidates in alphabetical order of surname, then first
name, within each centre. Each branch can be its own centre; a school without
branches (or a branch without its own) uses the school-wide centre number.

Planning is separate from saving so the page can show every number before
anything changes. Two modes:

* ``fill``     — keep every number already given; new candidates get the next
                 free numbers after the highest one used at their centre (in
                 surname order among themselves). Safe after registration.
* ``renumber`` — number everyone again from 001 in surname order. Only for
                 before numbers have been sent to WAEC.
"""
import re

CENTRE_RE = re.compile(r'^\d{7}$')


def clean_centre(raw):
    """(centre_or_None, error_or_None). Blank is allowed (not set)."""
    c = re.sub(r'\s+', '', raw or '')
    if not c:
        return None, None
    if not CENTRE_RE.match(c):
        return None, 'A WAEC centre number is 7 digits, e.g. 4250101.'
    return c, None


def school_centre():
    from models import SchoolSettings
    return (SchoolSettings.get('waec_centre_number', '') or '').strip() or None


def set_school_centre(centre):
    from models import SchoolSettings
    SchoolSettings.set('waec_centre_number', centre or '', 'string', 'WAEC centre number (whole school)')


def centre_for(branch):
    """A branch's own centre, else the school-wide one."""
    return (getattr(branch, 'waec_centre', None) or '').strip() or school_centre()


def _sort_key(st):
    return ((st.surname or '').strip().lower(), (st.first_name or '').strip().lower(),
            (st.middle_name or '').strip().lower(), st.id)


def plan(students, mode='fill'):
    """Group ``students`` by centre and propose numbers.

    Returns {'centres': [{'centre', 'label', 'rows': [...], 'issues': [...]}],
             'missing': [students with no centre], 'counts': {...}}.
    Each row: {'student', 'current', 'proposed', 'status'} where status is
    'keep' (already has this number), 'new' (gets a number), 'change' (would
    replace a different number)."""
    from models import Branch
    branches = {b.id: b for b in Branch.query.all()}
    default = Branch.get_default() if branches else None
    groups, missing = {}, []
    for st in students:
        br = branches.get(st.branch_id) or default
        c = centre_for(br) if br else school_centre()
        if not c:
            missing.append(st)
            continue
        g = groups.setdefault(c, {'centre': c, 'names': [], 'students': []})
        name = br.name if br else 'Whole school'
        if name not in g['names']:
            g['names'].append(name)
        g['students'].append(st)

    out, counts = [], {'keep': 0, 'new': 0, 'change': 0}
    for c, g in sorted(groups.items()):
        studs = sorted(g['students'], key=_sort_key)
        rows, issues = [], []
        if mode == 'renumber':
            for i, st in enumerate(studs, 1):
                prop = f'{c}{i:03d}'
                cur = (st.waec_reg_number or '').strip()
                rows.append({'student': st, 'current': cur or None, 'proposed': prop,
                             'status': 'keep' if cur == prop else ('change' if cur else 'new')})
        else:
            used = set()
            for st in studs:
                cur = (st.waec_reg_number or '').strip()
                if cur.startswith(c) and len(cur) == 10 and cur[7:].isdigit():
                    used.add(int(cur[7:]))
            nxt = max(used) + 1 if used else 1
            for st in studs:
                cur = (st.waec_reg_number or '').strip()
                if cur.startswith(c) and len(cur) == 10 and cur[7:].isdigit():
                    rows.append({'student': st, 'current': cur, 'proposed': cur, 'status': 'keep'})
                    continue
                while nxt in used:
                    nxt += 1
                prop = f'{c}{nxt:03d}'
                used.add(nxt)
                nxt += 1
                rows.append({'student': st, 'current': cur or None, 'proposed': prop,
                             'status': 'change' if cur else 'new'})
            rows.sort(key=lambda r: r['proposed'])
        seen = {}
        for r in rows:
            seen[r['proposed']] = seen.get(r['proposed'], 0) + 1
        dups = [k for k, n in seen.items() if n > 1]
        if dups:
            issues.append(f'{len(dups)} number(s) are used twice at this centre — renumber to fix.')
        if any(int(r['proposed'][7:]) > 999 for r in rows):
            issues.append('More than 999 candidates at one centre — WAEC numbers only go to 999.')
        for r in rows:
            counts[r['status']] += 1
        out.append({'centre': c, 'label': ', '.join(sorted(g['names'])), 'rows': rows, 'issues': issues})
    return {'centres': out, 'missing': sorted(missing, key=_sort_key), 'counts': counts}


def apply(the_plan):
    """Save every proposed number that differs from the current one."""
    from models import db
    n = 0
    for g in the_plan['centres']:
        if any('999' in i for i in g['issues']):
            continue
        for r in g['rows']:
            if r['status'] != 'keep':
                r['student'].waec_reg_number = r['proposed']
                n += 1
    db.session.commit()
    return n
