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

Within a hall, ``seat_hall`` then lays candidates out on a seat grid so that no
two students from the same class sit in adjacent seats (front/back/side) — an
SSS1 candidate ends up between SSS2 candidates, row-wise and column-wise —
using OR-tools CP-SAT when available to minimise same-class neighbours, with a
deterministic round-robin fallback.

Public entry points: ``allocate_halls(groups, halls, balance_gender=True)`` and
``seat_hall(students, cols=5)``.
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


# --------------------------------------------------------------------------- #
# Seat layout within a hall: keep same class+arm out of adjacent seats.
# --------------------------------------------------------------------------- #

def _sk(s):
    """The key a student is separated by for seating: the CLASS. Same-class
    candidates (any arm) write the same papers, so they must not sit next to each
    other (in a row or a column); different classes may interleave — e.g. an SSS1
    candidate sits between two SSS2 candidates. Falls back to the class+arm group
    key when the class isn't carried on the record."""
    return (s.get('class_name') or s.get('_group_key') or '').strip()


def _seat_layout_cpsat(n, rows, cols, counts, time_limit):
    """CP-SAT: assign a group index to each of the first ``n`` grid cells
    (row-major) so orthogonally-adjacent cells rarely share a group. Returns a
    list of length rows*cols (group index, or None for the trailing empties), or
    None if OR-tools is unavailable or finds nothing."""
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return None
    G = len(counts)
    used = list(range(n))                       # first n cells are seats
    m = cp_model.CpModel()
    y = {(u, g): m.NewBoolVar(f'y{u}_{g}') for u in used for g in range(G)}
    for u in used:
        m.Add(sum(y[u, g] for g in range(G)) == 1)
    for g in range(G):
        m.Add(sum(y[u, g] for u in used) == counts[g])

    def cell(r, c):
        return r * cols + c

    pairs = []
    for r in range(rows):
        for c in range(cols):
            u = cell(r, c)
            if u >= n:
                continue
            if c + 1 < cols and cell(r, c + 1) < n:
                pairs.append((u, cell(r, c + 1)))
            if r + 1 < rows and cell(r + 1, c) < n:
                pairs.append((u, cell(r + 1, c)))
    same = []
    for a, b in pairs:
        z = m.NewBoolVar(f'z{a}_{b}')
        for g in range(G):
            m.Add(z >= y[a, g] + y[b, g] - 1)
        same.append(z)
    m.Minimize(sum(same))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 8
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    out = [None] * (rows * cols)
    for u in used:
        for g in range(G):
            if solver.Value(y[u, g]) == 1:
                out[u] = g
                break
    return out


def _seat_layout_roundrobin(n, rows, cols, counts):
    """Deterministic fallback: emit group indices round-robin (largest group
    first) so equal groups alternate, then drop them into cells row-major."""
    remaining = list(counts)
    order = sorted(range(len(counts)), key=lambda g: counts[g], reverse=True)
    seq = []
    while len(seq) < n:
        placed = False
        for g in order:
            if remaining[g] > 0:
                seq.append(g)
                remaining[g] -= 1
                placed = True
        if not placed:
            break
    out = [None] * (rows * cols)
    for i in range(n):
        out[i] = seq[i]
    return out


def seat_hall(students, cols=5, optimize=True, time_limit=4.0):
    """Lay a hall's ``students`` onto a seat grid (``cols`` seats per row),
    numbering seats and keeping the same class out of adjacent seats (row and
    column) where the numbers allow.

    Returns ``{'rows': [[seat|None,...],...], 'cols', 'nrows', 'count',
    'conflicts'}`` where each seat is ``{'seat': n, 'student': {...}}`` and
    ``conflicts`` counts remaining same-group orthogonal neighbours (0 is ideal).
    """
    students = list(students)
    n = len(students)
    cols = max(2, int(cols or 5))
    if n == 0:
        return {'rows': [], 'cols': cols, 'nrows': 0, 'count': 0, 'conflicts': 0}
    rows = math.ceil(n / cols)

    buckets, order = {}, []
    for s in students:
        k = _sk(s)
        if k not in buckets:
            buckets[k] = []
            order.append(k)
        buckets[k].append(s)
    counts = [len(buckets[k]) for k in order]

    layout = None
    if optimize and len(order) > 1:
        layout = _seat_layout_cpsat(n, rows, cols, counts, time_limit)
    if layout is None:
        layout = _seat_layout_roundrobin(n, rows, cols, counts)

    pools = {k: list(buckets[k]) for k in order}
    flat = []
    for idx in range(rows * cols):
        gi = layout[idx]
        flat.append(pools[order[gi]].pop(0) if gi is not None else None)

    grid, seat_no = [], 0
    for r in range(rows):
        row_cells = []
        for c in range(cols):
            st = flat[r * cols + c]
            if st is not None:
                seat_no += 1
                row_cells.append({'seat': seat_no, 'student': st})
            else:
                row_cells.append(None)
        grid.append(row_cells)

    def gk(idx):
        return _sk(flat[idx]) if flat[idx] is not None else None

    conflicts = 0
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            if flat[idx] is None:
                continue
            if c + 1 < cols and flat[idx + 1] is not None and gk(idx) == gk(idx + 1):
                conflicts += 1
            if r + 1 < rows and flat[idx + cols] is not None and gk(idx) == gk(idx + cols):
                conflicts += 1
    return {'rows': grid, 'cols': cols, 'nrows': rows, 'count': n, 'conflicts': conflicts}
