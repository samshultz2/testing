"""Suggest a likely sibling's contacts for a student who has none.

Pupils who share a surname with another pupil are most often siblings, so a
student with no parent/guardian contact gets the contacts of same-surname
pupils offered for copying. A pair marked "not siblings" is never offered
again (kept as a school setting, like the duplicates page's "not the same
person" list)."""
import re

_NOT_SIB_KEY = 'students_not_siblings'


def _norm(name):
    return re.sub(r'[^a-z]', '', (name or '').lower())


def _pair(a, b):
    return '%d-%d' % (min(a, b), max(a, b))


def not_sibling_pairs():
    from models.models.settings import SchoolSettings
    try:
        return set(SchoolSettings.get(_NOT_SIB_KEY, []) or [])
    except Exception:
        return set()


def mark_not_siblings(a, b):
    from models.models.settings import SchoolSettings
    pairs = not_sibling_pairs()
    pairs.add(_pair(int(a), int(b)))
    SchoolSettings.set(_NOT_SIB_KEY, sorted(pairs), value_type='json',
                       description='Student pairs confirmed as not siblings')


def suggestions(student, limit=5):
    """Same-surname pupils (same branch, still active) who have contacts, best
    match first: same home address, then same contact surname, then name."""
    from models import Student, ParentContact
    if student.parent_contacts.count():
        return []
    key = _norm(student.surname)
    if len(key) < 2:
        return []
    q = Student.query.filter(Student.id != student.id, Student.is_active == True,  # noqa: E712
                             db_func_lower(Student.surname) == (student.surname or '').strip().lower())
    if student.branch_id is not None:
        q = q.filter(Student.branch_id == student.branch_id)
    blocked = not_sibling_pairs()
    cands = [s for s in q.limit(60).all()
             if _norm(s.surname) == key and _pair(s.id, student.id) not in blocked]
    if not cands:
        return []
    contacts = {}
    for c in ParentContact.query.filter(ParentContact.student_id.in_([s.id for s in cands])).all():
        contacts.setdefault(c.student_id, []).append(c)
    addr = _norm(student.home_address)
    out = []
    for s in cands:
        cs = contacts.get(s.id)
        if not cs:
            continue
        same_addr = bool(addr) and _norm(s.home_address) == addr
        out.append({
            'id': s.id, 'name': s.full_name, 'student_id': s.student_id,
            'same_address': same_addr,
            'contacts': [{'name': c.name, 'relationship': c.relationship,
                          'phone_number': c.phone_number, 'is_primary': bool(c.is_primary)}
                         for c in sorted(cs, key=lambda c: (not c.is_primary, c.id))],
            '_rank': (not same_addr, s.full_name.lower()),
        })
    out.sort(key=lambda r: r.pop('_rank'))
    # Siblings who already share the same numbers (e.g. copied from each
    # other) would be the same suggestion twice -- show each set once.
    seen, uniq = set(), []
    for r in out:
        key = frozenset(re.sub(r'\D', '', c['phone_number'] or '') for c in r['contacts'])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq[:limit]


def copy_contacts(src, dst):
    """Copy every contact of ``src`` onto ``dst``, skipping phone numbers dst
    already has. Returns how many were added. Caller commits."""
    from models import db, ParentContact
    have = {re.sub(r'\D', '', c.phone_number or '') for c in dst.parent_contacts.all()}
    has_primary = any(c.is_primary for c in dst.parent_contacts.all())
    added = 0
    for c in src.parent_contacts.order_by(ParentContact.is_primary.desc(), ParentContact.id).all():
        digits = re.sub(r'\D', '', c.phone_number or '')
        if not digits or digits in have:
            continue
        db.session.add(ParentContact(student_id=dst.id, phone_number=c.phone_number, email=c.email,
                                     relationship=c.relationship, name=c.name,
                                     is_primary=bool(c.is_primary) and not has_primary))
        has_primary = has_primary or bool(c.is_primary)
        have.add(digits)
        added += 1
    return added


def db_func_lower(col):
    from models import db
    return db.func.lower(db.func.trim(col))
