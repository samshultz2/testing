"""Resolve which timetable entries belong to a logged-in user.

A published class timetable stores the teacher as a free-text ``teacher_name``
(copied from the generator's ``GenTeacher.name``). A user's login ``full_name``
often differs slightly, so an exact match misses their periods. This module
returns the set of normalized name keys a user's timetable could appear under:

  * the user's own ``full_name`` and ``username``;
  * the name of any ``GenTeacher`` explicitly linked to the user (``user_id``);
  * the name of any ``GenTeacher`` whose email matches the user's (a safe
    auto-link signal).

Matching on this key set (via :func:`utils.name_match.normalize_person_name`)
tolerates title/order/formatting differences without guessing across people.
"""
from __future__ import annotations

from utils.name_match import name_key_set, normalize_person_name


def linked_gen_teachers(user):
    """GenTeacher rows tied to ``user`` — by explicit link, else by matching
    email (exact, case-insensitive). Empty list when none / no user."""
    if not user:
        return []
    from models import db
    from models.models.generator import GenTeacher
    from sqlalchemy import func
    rows = GenTeacher.query.filter_by(user_id=user.id).all()
    if rows:
        return rows
    if user.email:
        rows = GenTeacher.query.filter(
            func.lower(GenTeacher.email) == user.email.strip().lower()).all()
    return rows


def timetable_name_keys(user):
    """The normalized name keys a user's published periods may be recorded under."""
    if not user:
        return set()
    keys = name_key_set(getattr(user, 'full_name', None), getattr(user, 'username', None))
    for gt in linked_gen_teachers(user):
        k = normalize_person_name(gt.name)
        if k:
            keys.add(k)
    return keys
