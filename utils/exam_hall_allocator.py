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
two students from the same class sit in adjacent seats — front, back, side OR
diagonal — an SSS1 candidate ends up surrounded by SSS2 candidates on every
side, using OR-tools CP-SAT when available to minimise same-class neighbours,
with a deterministic fallback. Diagonal seats matter as much as orthogonal
ones for copying/passing answers, so "adjacent" means any of the 8 cells
touching a seat (the king-move/Moore neighbourhood), not just the 4 sharing an
edge with it.

Public entry points: ``allocate_halls(groups, halls, balance_gender=True)`` and
``seat_hall(students, cols=5)``.
"""
import math
import random


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


def allocate_halls(groups, halls, balance_gender=True, seed=None):
    """Allocate candidates to halls.

    ``groups``: list of ``{'key': 'SSS1 Rose', 'students': [ {id, name, gender,
    class_name, arm, student_id}, ... ]}``. Each group is one class+arm.
    ``halls``: list of ``{'name': str, 'capacity': int, 'is_main': bool}``.
    ``seed``: shuffles which candidates land in which hall so each run gives a
    fresh (but still rule-abiding) arrangement; pass a fixed value to reproduce.

    Returns a dict describing the filled halls plus per-hall and per-group stats.
    Raises ``ValueError`` if there are no halls/capacity or capacity < candidates.
    """
    rng = random.Random(seed)
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
        students = list(g['students'])
        if not students:
            continue
        rng.shuffle(students)                # different candidates per hall each run
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
    candidates (any arm) write the same papers, so they must not sit next to
    each other in any direction — row, column or diagonal; different classes
    may interleave — e.g. an SSS1 candidate sits between two SSS2 candidates.
    Falls back to the class+arm group key when the class isn't carried on the
    record."""
    return (s.get('class_name') or s.get('_group_key') or '').strip()


def _pairs(n, rows, cols):
    """Neighbour cell-index pairs among the first n row-major cells, under the
    full 8-direction (Moore) neighbourhood — orthogonal (row/column) AND
    diagonal. A diagonal seatmate can see or pass a paper just as easily as a
    direct side neighbour, so both count as "adjacent" here.

    Walking 4 of the 8 directions from every cell (right, down, down-right,
    down-left) touches each unordered neighbour pair exactly once — the other
    4 directions are the same pairs seen from the other cell."""
    def cell(r, c):
        return r * cols + c
    out = []
    for r in range(rows):
        for c in range(cols):
            u = cell(r, c)
            if u >= n:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                r2, c2 = r + dr, c + dc
                if 0 <= r2 < rows and 0 <= c2 < cols:
                    v = cell(r2, c2)
                    if v < n:
                        out.append((u, v))
    return out


def _roundrobin_seq(n, counts, group_class):
    """A sequence of group indices that spreads CLASSES first: round-robin across
    classes (largest class first), and within a class round-robin across its
    arms. So consecutive items are different classes wherever possible."""
    from collections import defaultdict
    by_class = defaultdict(list)
    for g in range(len(counts)):
        by_class[group_class[g]].append(g)
    remaining = list(counts)
    class_order = sorted(by_class, key=lambda c: sum(remaining[g] for g in by_class[c]),
                         reverse=True)
    seq = []
    while len(seq) < n:
        progressed = False
        for c in class_order:
            gs = [g for g in by_class[c] if remaining[g] > 0]
            if not gs:
                continue
            g = max(gs, key=lambda g: remaining[g])   # fullest arm of this class
            seq.append(g); remaining[g] -= 1; progressed = True
        if not progressed:
            break
    return seq


def _seat_layout_moore(n, rows, cols, counts, group_class):
    """Deterministic, count-preserving layout that concentrates each CLASS on
    one colour of a 2x2 tile pattern (row-parity x column-parity — 4 colours).
    Two cells of the same colour always differ by an even number of rows AND
    an even number of columns, so the closest they can ever be is a Chebyshev
    distance of 2 — never orthogonally OR diagonally adjacent. (A plain 2-colour
    checkerboard only guarantees that for orthogonal neighbours; its diagonal
    neighbours are always the SAME colour, which is exactly backwards for this
    use.) Up to 4 classes can each claim one whole colour and end up with zero
    neighbours of their own class in any direction; a class bigger than one
    colour (or a 5th+ class) spills into whichever colour still has the most
    room — the best achievable at that density, since no independent set in
    this 8-neighbour adjacency can exceed 1/4 of a fully-packed grid. Also a
    warm start for CP-SAT. Arms of a class are then round-robined across that
    class's seats."""
    from collections import defaultdict
    used = list(range(n))                                      # first n cells, row-major
    free = {0: [], 1: [], 2: [], 3: []}
    for i in used:
        r, c = divmod(i, cols)
        free[(r % 2) * 2 + (c % 2)].append(i)

    classes = sorted(set(group_class),
                     key=lambda c: sum(counts[g] for g in range(len(counts))
                                       if group_class[g] == c), reverse=True)
    cell_class = [None] * (rows * cols)
    for c in classes:
        need = sum(counts[g] for g in range(len(counts)) if group_class[g] == c)
        # Claim whichever colour still has the most free seats, repeatedly,
        # until this class is fully seated — biggest classes get first pick
        # (processed largest-first above) and whole colours where possible.
        while need > 0:
            color = max(free, key=lambda k: len(free[k]))
            if not free[color]:
                break   # grid exhausted (shouldn't happen: sum(counts) == n)
            take = min(need, len(free[color]))
            for _ in range(take):
                cell_class[free[color].pop()] = c
            need -= take

    # Within each class's seats, spread its arms round-robin.
    cells_by_class = defaultdict(list)
    for i in used:
        cells_by_class[cell_class[i]].append(i)
    out = [None] * (rows * cols)
    for c, cells in cells_by_class.items():
        gs = [g for g in range(len(counts)) if group_class[g] == c]
        rem = {g: counts[g] for g in gs}
        seq = []
        while len(seq) < len(cells):
            progressed = False
            for g in sorted(gs, key=lambda g: rem[g], reverse=True):
                if rem[g] > 0:
                    seq.append(g); rem[g] -= 1; progressed = True
            if not progressed:
                break
        for cell, g in zip(cells, seq):
            out[cell] = g
    return out


def _seat_layout_cpsat(n, rows, cols, counts, group_class, time_limit, hint, rand_seed=0):
    """CP-SAT: assign a group to each of the first ``n`` cells minimising, in
    priority order, same-CLASS neighbours (any of the 8 surrounding seats) then
    same-arm (same group) neighbours. So classes are separated first and, when
    a hall is one class, arms are separated. Warm-started from ``hint``.
    Returns a per-cell group list (None for trailing empties) or None if
    OR-tools is unavailable / finds none."""
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return None
    G = len(counts)
    classes = sorted(set(group_class))
    cls_idx = {c: i for i, c in enumerate(classes)}
    used = list(range(n))
    m = cp_model.CpModel()
    y = {(u, g): m.NewBoolVar(f'y{u}_{g}') for u in used for g in range(G)}
    for u in used:
        m.Add(sum(y[u, g] for g in range(G)) == 1)
    for g in range(G):
        m.Add(sum(y[u, g] for u in used) == counts[g])
    # Per-cell class indicator (derived from the chosen group).
    yc = {}
    for u in used:
        for c in classes:
            gs = [g for g in range(G) if group_class[g] == c]
            var = m.NewBoolVar(f'yc{u}_{cls_idx[c]}')
            m.Add(var == sum(y[u, g] for g in gs))
            yc[u, c] = var

    pairs = _pairs(n, rows, cols)
    same_class, same_group = [], []
    for a, b in pairs:
        zc = m.NewBoolVar(f'zc{a}_{b}')
        for c in classes:
            m.Add(zc >= yc[a, c] + yc[b, c] - 1)
        same_class.append(zc)
        zg = m.NewBoolVar(f'zg{a}_{b}')
        for g in range(G):
            m.Add(zg >= y[a, g] + y[b, g] - 1)
        same_group.append(zg)
    # Class separation dominates; arm separation breaks ties (matters most when a
    # hall is a single class, where every same_class term is unavoidable).
    big = len(pairs) + 1
    m.Minimize(big * sum(same_class) + sum(same_group))

    if hint:
        for u in used:
            g = hint[u]
            if g is not None:
                m.AddHint(y[u, g], 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = int(rand_seed) & 0x7fffffff
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


def seat_hall(students, cols=5, optimize=True, time_limit=4.0, seed=None):
    """Lay a hall's ``students`` onto a seat grid (``cols`` seats per row),
    numbering seats and keeping the same class out of adjacent seats — row,
    column OR diagonal — where the numbers allow. ``seed`` varies which
    candidate takes which seat so each run differs while still obeying the
    rules.

    Returns ``{'rows': [[seat|None,...],...], 'cols', 'nrows', 'count',
    'conflicts'}`` where each seat is ``{'seat': n, 'student': {...}}`` and
    ``conflicts`` counts remaining same-class neighbours in any of the 8
    surrounding seats (0 is ideal, though at high occupancy a few are
    unavoidable — see ``_seat_layout_moore``).
    """
    rng = random.Random(seed)
    students = list(students)
    n = len(students)
    cols = max(2, int(cols or 5))
    if n == 0:
        return {'rows': [], 'cols': cols, 'nrows': 0, 'count': 0, 'conflicts': 0}
    rows = math.ceil(n / cols)

    # Fine groups = class + arm; each carries its class so the layout can
    # separate classes first and arms second.
    buckets, order, group_class = {}, [], []
    for s in students:
        cls = _sk(s)                                   # the class (separation key)
        arm = (s.get('arm') or '').strip()
        k = (cls, arm)
        if k not in buckets:
            buckets[k] = []
            order.append(k)
            group_class.append(cls)
        buckets[k].append(s)
    counts = [len(buckets[k]) for k in order]

    # Bigger halls get more solver time; warm-start from the deterministic fallback.
    tl = time_limit if n <= 60 else min(20.0, time_limit + n / 20.0)
    hint = _seat_layout_moore(n, rows, cols, counts, group_class)
    layout = None
    if optimize:
        layout = _seat_layout_cpsat(n, rows, cols, counts, group_class, tl, hint,
                                    rand_seed=rng.randrange(1 << 31))
    if layout is None:
        layout = hint

    # Shuffle each group's members so which candidate takes which of that
    # group's seats varies per run (the layout/rules are unchanged).
    pools = {k: list(buckets[k]) for k in order}
    for k in pools:
        rng.shuffle(pools[k])
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

    # Reuse the exact same adjacency definition the optimizer minimises
    # (_pairs, the 8-direction Moore neighbourhood) so this count can never
    # drift from what CP-SAT was actually scoring.
    conflicts = sum(
        1 for u, v in _pairs(rows * cols, rows, cols)
        if flat[u] is not None and flat[v] is not None and gk(u) == gk(v)
    )
    return {'rows': grid, 'cols': cols, 'nrows': rows, 'count': n, 'conflicts': conflicts}
