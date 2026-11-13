"""Short medical flags for rosters (Students list, class roster, registers).

Only the plain, non-encrypted fields are read (conditions, allergies,
medication, disabilities, genotype) so building a roster never decrypts the
confidential notes. Callers must check ``can_view_medical()`` first; these
helpers return the text unconditionally.
"""

_NONE = {'', 'none', 'nil', 'n/a', 'na', 'no', '-', 'nill', 'nothing'}


def _val(v):
    v = (v or '').strip()
    return '' if v.lower() in _NONE else v


def medical_summary(student):
    """One line such as 'Asthma · Allergy: Penicillin · On medication' or ''."""
    bits = []
    cond = _val(getattr(student, 'medical_conditions', None))
    if cond:
        bits.append(cond)
    g = (getattr(student, 'genotype', None) or '').strip().upper()
    if g in ('SS', 'SC') and 'sickle' not in cond.lower():
        bits.append('Genotype ' + g)
    al = _val(getattr(student, 'allergies', None))
    if al:
        bits.append('Allergy: ' + al)
    med = _val(getattr(student, 'medications', None))
    if med:
        bits.append('Medication: ' + med)
    dis = _val(getattr(student, 'disabilities', None))
    if dis:
        bits.append(dis)
    return ' · '.join(bits)


def medical_map(students):
    """{student_id: summary} for the students that have something to flag."""
    out = {}
    for s in students:
        t = medical_summary(s)
        if t:
            out[s.id] = t[:240]
    return out
