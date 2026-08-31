"""Safe LIKE/ILIKE search helpers.

User search terms are always sent to SQLAlchemy as *bound parameters*, so they
are not a SQL-injection vector. But the ``%`` and ``_`` wildcards inside a term
are still interpreted by ``LIKE``/``ILIKE`` — a user typing ``%`` would match
every row, and a crafted term (e.g. ``%a%b%c%…``) can force an expensive scan.

These helpers escape the wildcard metacharacters (``\\`` ``%`` ``_``) and build a
``%…%`` "contains" pattern, applied with an explicit ``ESCAPE '\\'`` so the
escaped wildcards are treated as literals. Normal searches behave exactly as
before; only literal ``%``/``_`` now match themselves instead of acting as
wildcards.
"""

_ESCAPE_CHAR = '\\'


def escape_like(term):
    """Escape LIKE wildcards so the term matches literally."""
    s = term or ''
    return (s.replace('\\', '\\\\')
             .replace('%', '\\%')
             .replace('_', '\\_'))


def like_term(term):
    """A ``%…%`` contains-pattern with wildcards in ``term`` escaped."""
    return f'%{escape_like(term)}%'


def ilike_contains(column, term):
    """``column ILIKE '%term%' ESCAPE '\\'`` with wildcards escaped."""
    return column.ilike(like_term(term), escape=_ESCAPE_CHAR)


def ilike_any(term, *columns):
    """OR of :func:`ilike_contains` over several columns (the common case of
    searching a name across first/last/id columns)."""
    from models import db
    pat = like_term(term)
    return db.or_(*[c.ilike(pat, escape=_ESCAPE_CHAR) for c in columns])
