"""Choosable student-name format for broadsheets.

A broadsheet can show any of the name parts — surname, first name, middle
name — always in that order (the school's register order), optionally with the
middle name shortened to its initial(s), which then sits between the surname
and the first name: ``Okafor C. John``.

Query-string form (shared by the WAEC and Mock WAEC broadsheets):
    names=surname,first,middle   which parts to show (any non-empty subset)
    mid_init=1                   middle name(s) as initials

When ``names`` is absent the caller keeps its own historical default, so
existing links and prints are unchanged.
"""
from __future__ import annotations

PARTS = ('surname', 'first', 'middle')
PART_LABELS = {'surname': 'Surname', 'first': 'First name', 'middle': 'Middle name'}


def name_opts(args):
    """Parse ``names`` / ``mid_init`` from a request's args. Returns None when
    no name format was requested (use the caller's default)."""
    raw = (args.get('names') or '').strip()
    if not raw:
        return None
    parts = [p for p in (x.strip().lower() for x in raw.split(',')) if p in PARTS]
    if not parts:
        return None
    return {'parts': [p for p in PARTS if p in parts],
            'mid_init': str(args.get('mid_init') or '') in ('1', 'true', 'on', 'yes')}


def _get(st, key):
    if isinstance(st, dict):
        return st.get(key)
    return getattr(st, key, None)


def _middle(st):
    mid = _get(st, 'middle_name')
    if mid is None and isinstance(st, dict):
        # Older cached rows carry only full_name ("Surname First Middle…").
        full = (st.get('full_name') or '').split()
        known = {(st.get('surname') or '').lower(), (st.get('first_name') or '').lower()}
        rest = [w for w in full if w.lower() not in known]
        mid = ' '.join(rest) if len(full) > 2 else ''
    return (mid or '').strip()


def initials(name):
    """'Chukwuemeka Ada' → 'C. A.'; hyphenated parts keep each initial ('A.-O.')."""
    out = []
    for word in (name or '').split():
        bits = [b for b in word.split('-') if b]
        if bits:
            out.append('-'.join(b[0].upper() + '.' for b in bits))
    return ' '.join(out)


def format_name(st, opts, default=None):
    """The display name for ``st`` (a Student or a broadsheet student dict).

    ``opts`` is ``name_opts(...)``; when None, ``default(st)`` is used (or the
    full name)."""
    if not opts:
        if default is not None:
            return default(st)
        return (_get(st, 'full_name') or '').strip()
    vals = {'surname': (_get(st, 'surname') or '').strip(),
            'first': (_get(st, 'first_name') or '').strip(),
            'middle': _middle(st)}
    order = list(opts['parts'])
    if opts.get('mid_init') and vals['middle']:
        vals['middle'] = initials(vals['middle'])
        # The initial sits in the middle: "Okafor C. John".
        order = [p for p in ('surname', 'middle', 'first') if p in order]
    name = ' '.join(vals[p] for p in order if vals[p])
    return name or (_get(st, 'full_name') or '').strip()


def name_query(opts):
    """Back to query params (for links that must carry the choice)."""
    if not opts:
        return {}
    q = {'names': ','.join(opts['parts'])}
    if opts.get('mid_init'):
        q['mid_init'] = '1'
    return q
