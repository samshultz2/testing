"""Tolerant person-name matching.

Different parts of the app record a teacher's name in slightly different forms —
the login account's ``full_name`` ("John Doe"), the HR record ("Doe John"), the
timetable generator ("Mr. John Doe"). Matching those with a raw string compare
fails, which is why a teacher's generated timetable can look empty even though
periods exist for them.

``normalize_person_name`` reduces a name to a canonical key by dropping courtesy
titles and suffixes, stripping punctuation, folding case/accents, and sorting the
remaining tokens — so "Mr. John Doe", "Doe, John" and "john  doe" all collapse to
the same key. Compare keys, not raw strings.
"""
from __future__ import annotations

import re
import unicodedata

# Courtesy titles / honorifics and suffixes that carry no identity — dropped so
# "Mr John Doe" matches "John Doe". Compared without trailing dots.
_TITLES = {
    'mr', 'mrs', 'ms', 'miss', 'mister', 'master', 'dr', 'doctor', 'prof',
    'professor', 'rev', 'reverend', 'fr', 'father', 'sr', 'pastor', 'engr',
    'engineer', 'barr', 'barrister', 'hon', 'honourable', 'honorable', 'chief',
    'alhaji', 'alhaja', 'mallam', 'sir', 'madam', 'ma',
}
_SUFFIXES = {'jr', 'snr', 'sr', 'ii', 'iii', 'iv', 'phd', 'msc', 'bsc', 'ed'}


def _tokens(name: str):
    if not name:
        return []
    # Fold accents to ASCII, lower-case, and split on any non-letter/digit.
    n = unicodedata.normalize('NFKD', str(name))
    n = ''.join(c for c in n if not unicodedata.combining(c)).lower()
    return [t for t in re.split(r'[^a-z0-9]+', n) if t]


def normalize_person_name(name: str) -> str:
    """Canonical, order-independent key for a person's name (see module docstring).

    Drops titles/suffixes, then sorts the remaining name tokens so word order and
    formatting don't matter. Returns '' for an empty/uninformative name."""
    toks = _tokens(name)
    core = [t for t in toks if t not in _TITLES and t not in _SUFFIXES]
    core = core or toks           # if everything was a title, keep what we had
    return ' '.join(sorted(core))


def names_match(a: str, b: str) -> bool:
    """True when two names refer to the same person under normalization."""
    ka, kb = normalize_person_name(a), normalize_person_name(b)
    return bool(ka) and ka == kb


def name_key_set(*names) -> set:
    """The set of non-empty normalized keys for the given names (any may be None)."""
    return {k for k in (normalize_person_name(n) for n in names if n) if k}
