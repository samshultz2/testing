"""Automated-communication registry.

Other modules fire notifications automatically (a parent is emailed when their
child is admitted, admins are alerted on a failed payment, …). This gives schools
one place to turn each of those automations on or off, backed by the existing
``SchoolSettings`` key-value store so it works per-tenant with no new table.

Each trigger site guards itself with ``automations.is_enabled('<key>')``; an
unknown or unset key falls back to the registry default (enabled), so existing
behaviour is unchanged until an admin flips something off.
"""
from __future__ import annotations

_PREFIX = 'auto.'

# key, label, description, category, default-enabled
REGISTRY = [
    ('admission_decision', 'Admission decision',
     "Email the parent and alert admins when an application is accepted or rejected.",
     'Admissions', True),
    ('attendance_alert', 'Attendance absence alerts',
     "Alert admins when a student crosses the consecutive-absence threshold.",
     'Attendance', True),
    ('attendance_absent_parent', 'Absent-today parent notices',
     "Let staff draft a message to the parents of students absent on a given day "
     "(reviewed before sending).",
     'Attendance', False),
    ('attendance_low_parent', 'Low-attendance parent notices',
     "Let staff draft a message to the parents of students below the attendance "
     "warning threshold for a term (reviewed before sending).",
     'Attendance', False),
    ('results_published', 'Results published',
     "Draft a parent notification when results are released for a term.",
     'Academics', True),
    ('payment_success', 'Successful payment',
     "Notify admins when a parent pays online.",
     'Finance', True),
    ('payment_failed', 'Failed payment',
     "Alert admins when an online payment can't be verified.",
     'Finance', True),
    ('student_change', 'Student record changes',
     "Post an in-app notification when a student is added, updated or removed.",
     'Students', True),
    ('library_overdue', 'Library overdue reminders',
     "Once a day, alert admins about overdue library books and draft a reminder to "
     "the borrowers' parents for review.",
     'Library', False),
    ('library_due_soon', 'Library due-soon alerts',
     "Once a day, alert admins about library books due within the next two days.",
     'Library', False),
    ('stock_low', 'Low-stock alerts',
     "Once a day, bell admins and Sales & Inventory staff about products at or "
     "below their reorder level (or out of stock).",
     'Sales', False),
    ('stock_expiry', 'Stock expiry alerts',
     "Once a day, bell admins and Sales & Inventory staff about products expiring "
     "within 30 days (or already expired).",
     'Sales', False),
]

_DEFAULTS = {k: d for k, _l, _desc, _cat, d in REGISTRY}
KEYS = [k for k, *_ in REGISTRY]


def is_enabled(key):
    """True if the automation should fire. Unknown keys are treated as enabled so
    a new automation works before anyone visits the settings screen."""
    from models import SchoolSettings
    default = _DEFAULTS.get(key, True)
    try:
        return bool(SchoolSettings.get(_PREFIX + key, default))
    except Exception:
        return default


def set_enabled(key, enabled):
    from models import db, SchoolSettings
    if key not in _DEFAULTS:
        return
    SchoolSettings.set(_PREFIX + key, bool(enabled), 'bool',
                       description='Communication automation toggle')
    db.session.commit()


def all_states():
    """Registry entries with their current enabled state — for the settings UI."""
    return [{'key': k, 'label': label, 'description': desc, 'category': cat,
             'enabled': is_enabled(k)}
            for k, label, desc, cat, _d in REGISTRY]
