"""Branch scoping (Stage 2).

Decides which branch(es) the current user may see and stamps new records with
the right branch.

* Central users (Director of Studies, Exams & Standards, IT, admins) see **all**
  branches by default, and may narrow to one via the header branch picker
  (stored in ``session['view_branch_id']``).
* Branch users are locked to their own ``session['branch_id']``.

Apply it to a query with ``scope_query(Model.query, Model)`` (only models that
carry a ``branch_id`` column). Stamp a new record with ``branch_for_new()``.
"""
from flask import session

from models import Branch

# Session keys
SCOPE_KEY = 'scope'              # 'central' | 'branch'
BRANCH_KEY = 'branch_id'         # the branch a branch-user belongs to
VIEW_KEY = 'view_branch_id'      # the branch a central user is currently viewing


def is_central():
    """True if the user sees across every branch."""
    if session.get('role') in ('super_admin', 'admin'):
        return True
    return session.get(SCOPE_KEY) == 'central'


def default_branch_id():
    b = Branch.get_default()
    return b.id if b else None


def viewing_branch_id():
    """The single branch in view, or ``None`` meaning *all branches*.

    - central user: their picked branch, or ``None`` for all.
    - branch user: always their own branch (never ``None``; an unset branch
      collapses to ``-1`` so they can never see everything by accident).
    """
    if is_central():
        return session.get(VIEW_KEY)
    return session.get(BRANCH_KEY) or -1


def scope_query(query, model):
    """Filter a query to the branch(es) in scope (no-op when viewing all)."""
    bid = viewing_branch_id()
    if bid is not None:
        return query.filter(model.branch_id == bid)
    return query


def can_access_branch(branch_id):
    """May the current user open a record belonging to ``branch_id``?"""
    if is_central():
        return True
    if branch_id is None:
        return True   # unbranched legacy record
    return branch_id == session.get(BRANCH_KEY)


def branch_for_new(form_branch_id=None):
    """The branch a newly-created record should belong to.

    Branch users are forced to their own branch. Central users may choose
    (form field), otherwise the branch they are currently viewing, otherwise
    the default branch.
    """
    if not is_central():
        return session.get(BRANCH_KEY) or default_branch_id()
    return form_branch_id or session.get(VIEW_KEY) or default_branch_id()


def set_session_scope(user):
    """Record a user's branch scope in the session at login."""
    if user is None:   # legacy admin password login
        session[SCOPE_KEY] = 'central'
        session[BRANCH_KEY] = None
        return
    session[SCOPE_KEY] = 'central' if user.is_central else 'branch'
    session[BRANCH_KEY] = user.branch_id
