"""Single source of truth for resolving a subject's double-period requirement.

Both timetable engines (the fast global one and the OR-tools one) call this so
they always agree. The most specific layer that actually asks for a double wins,
and its own count travels with it:

    class-stream  >  stream  >  per-class  >  global

"Asks for a double" means that layer's ``needs_double_period`` is truthy. The
stream layer stores it as True/NULL (NULL = "defer to a broader layer"), so a
layer that hasn't set a double is simply skipped and the next one is consulted.
If no layer asks for one, the subject gets no double period.
"""
from __future__ import annotations


def resolve_double(class_stream_cfg=None, stream_subj=None, class_cfg=None, global_cfg=None):
    """Return ``(needs_double, double_count)`` for a subject.

    Pass whichever of the four config layers exist for this subject (any may be
    ``None``); they are consulted most-specific first. The winning layer's
    ``double_period_count`` is used, defaulting to 1 when it enabled a double but
    left the count blank.
    """
    for layer in (class_stream_cfg, stream_subj, class_cfg, global_cfg):
        if layer is not None and getattr(layer, 'needs_double_period', None):
            return True, (getattr(layer, 'double_period_count', None) or 1)
    return False, 0
