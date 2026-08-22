"""Exam hall allocator.

Distributes exam candidates across halls to reduce malpractice from
over-familiarisation: students from the same class + arm are spread across as
many halls as possible, halls are filled in proportion to their capacity (so a
big "Main" hall holds proportionally more), and — where possible — each hall's
intake is gender-balanced.

The algorithm is a deterministic, capacity-weighted proportional spread rather
than a constraint solver: for the stated objective (spread each group across
halls in proportion to capacity, interleave genders) this construction is
optimal, instant and reproducible, with no solver time or tuning to babysit.

Public entry point: ``allocate_halls(groups, halls, balance_gender=True)``.
"""
import math


def _largest_remainder(n, weights):
    """Split ``n`` items across buckets in proportion to ``weights`` using the
    largest-remainder method, so the parts are integers that sum to exactly n."""
    total = sum(weights)
    if n <= 0 or total <= 0:
        return [0] * len(weights)
    exact = [n * w / total for w in weights]
    floors = [int(math.floor(e)) for e in exact]
    rem = n - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: exact[i] - floors[i], reverse=True)
    for k in range(rem):
        floors[order[k % len(order)]] += 1
    return floors


def _gender_bucket(g):
    g = (g or '').strip().lower()
    if g.startswith('f'):
        return 'F'
    if g.startswith('m'):
        return 'M'
    return 'O'


def allocate_halls(groups, halls, balance_gender=True):
    """Allocate candidates to halls.

    ``groups``: list of ``{'key': 'SSS1 Rose', 'students': [ {id, name, gender,
    class_name, arm, student_id}, ... ]}``. Each group is one class+arm.
    ``halls``: list of ``{'name': str, 'capacity': int, 'is_main': bool}``.

    Returns a dict describing the filled halls plus per-hall and per-group stats.
    Raises ``ValueError`` if there are no halls/capacity or capacity < candidates.
    """
    halls = [dict(h) for h in halls]
    n_h = len(halls)
    caps = [max(0, int(h.get('capacity') or 0)) for h in halls]
    total_cap = sum(caps)
    total_students = sum(len(g['students']) for g in groups)

    if n_h == 0 or total_cap <= 0:
        raise ValueError('Add at least one hall with a capacity.')
    if total_students == 0:
        raise ValueError('No students found for the selected classes/arms.')
    if total_students > total_cap:
        raise ValueError(
            f'Not enough seats: {total_students} candidates but only {total_cap} '
            f'seats across {n_h} hall(s). Add halls or increase capacity.')

    assigned = [[] for _ in range(n_h)]
    remaining = caps[:]
    # Fixed hall order for dealing (biggest first); the per-group start offset
    # rotates within this order so groups don't all pile onto the same hall.
    base_order = sorted(range(n_h), key=lambda i: caps[i], reverse=True)

    for gi, g in enumerate(groups):
        students = g['students']
        if not students:
            continue
        for s in students:
            s['_group_key'] = g['key']       # for per-hall group breakdown stats

        # Quota per hall ∝ capacity, then repaired to fit remaining seats. This
        # is what spreads a group across every hall in proportion to capacity.
        quota = _largest_remainder(len(students), caps)
        quota = [min(quota[h], remaining[h]) for h in range(n_h)]
        deficit = len(students) - sum(quota)
        # Push any overflow (from rounding/caps) onto halls that still have slack.
        slack_order = sorted(range(n_h), key=lambda i: remaining[i] - quota[i], reverse=True)
        h_ptr = 0
        while deficit > 0:
            h = slack_order[h_ptr % n_h]
            if remaining[h] - quota[h] > 0:
                quota[h] += 1
                deficit -= 1
            h_ptr += 1
            if h_ptr > n_h * (max(remaining) + 2):
                break  # safety; should never trigger given the capacity check

        if balance_gender:
            # Fill each hall's quota with a gender mix proportional to the group's
            # overall mix, so no hall skews heavily one way. Females first, then
            # males into the leftover seats, then any 'other'.
            fem = [s for s in students if _gender_bucket(s.get('gender')) == 'F']
            mal = [s for s in students if _gender_bucket(s.get('gender')) == 'M']
            oth = [s for s in students if _gender_bucket(s.get('gender')) == 'O']
            f_h = _largest_remainder(len(fem), quota)
            leftover = [quota[h] - f_h[h] for h in range(n_h)]
            m_h = _largest_remainder(len(mal), leftover)
            for h in range(n_h):
                take = fem[:f_h[h]]; del fem[:f_h[h]]
                take += mal[:m_h[h]]; del mal[:m_h[h]]
                need = quota[h] - len(take)
                take += oth[:need]; del oth[:need]
                for student in take:
                    assigned[h].append(student)
                    remaining[h] -= 1
        else:
            # Rotate the fill order per group so groups don't all start on Main.
            order = base_order[gi % n_h:] + base_order[:gi % n_h]
            idx = 0
            for h in order:
                for _ in range(quota[h]):
                    assigned[h].append(students[idx]); idx += 1
                    remaining[h] -= 1

    # ---- Build result + stats -------------------------------------------------
    out_halls = []
    for h in range(n_h):
        studs = assigned[h]
        genders = {'Male': 0, 'Female': 0, 'Other': 0}
        by_group = {}
        for s in studs:
            b = _gender_bucket(s.get('gender'))
            genders['Female' if b == 'F' else 'Male' if b == 'M' else 'Other'] += 1
            key = s.get('_group_key', '')
            by_group[key] = by_group.get(key, 0) + 1
        out_halls.append({
            'name': halls[h].get('name') or f'Hall {h + 1}',
            'capacity': caps[h],
            'is_main': bool(halls[h].get('is_main')),
            'students': studs,
            'count': len(studs),
            'gender': genders,
            'by_group': by_group,
        })

    group_stats = []
    for g in groups:
        key = g['key']
        per_hall = [hh['by_group'].get(key, 0) for hh in out_halls]
        used = sum(1 for c in per_hall if c > 0)
        group_stats.append({
            'key': key,
            'size': len(g['students']),
            'halls_used': used,
            'max_in_hall': max(per_hall) if per_hall else 0,
            'per_hall': per_hall,
        })

    return {
        'halls': out_halls,
        'groups': group_stats,
        'total_students': total_students,
        'total_capacity': total_cap,
        'balanced_by_gender': balance_gender,
    }
