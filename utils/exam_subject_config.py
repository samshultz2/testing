"""Per-school external-exam (WAEC / JAMB) subject configuration.

A school can tailor which subjects its candidates offer for the senior external
exams: the full catalogue, the subjects that are *General* (compulsory for every
stream), and the extra subjects compulsory for each individual stream. The
effective compulsory list for a stream is ``general + that stream's extras``.

The config is stored per-school in ``SchoolSettings`` under a single JSON key.
When a school has never configured it, sensible defaults are derived from the
long-standing hardcoded constants so every existing behaviour is preserved.
"""
from utils.helpers import (STREAMS, WAEC_SUBJECTS, WAEC_DEFAULT_SUBJECTS,
                           STREAM_WAEC_SUBJECTS)

_KEY = 'exam_subject_config'

# JAMB is a 4-subject exam with English compulsory; the other three vary by
# stream. These mirror the common UTME combinations (see utils.exam_insights).
_JAMB_GENERAL = ['English Language']
_JAMB_STREAMS = {
    'Science': ['Mathematics', 'Physics', 'Chemistry', 'Biology'],
    'Arts': ['Literature in English', 'Government', 'Christian Religious Studies', 'Economics'],
    'Commercial': ['Economics', 'Mathematics', 'Commerce', 'Government'],
}


def _dedup(seq):
    """Order-preserving de-duplication."""
    out, seen = [], set()
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _default_config():
    """Defaults derived from the historical constants, so an unconfigured school
    behaves exactly as before."""
    # WAEC per-stream extras = the stream list minus the general subjects.
    waec_streams = {}
    for s in STREAMS:
        full = STREAM_WAEC_SUBJECTS.get(s, [])
        waec_streams[s] = [x for x in full if x not in WAEC_DEFAULT_SUBJECTS]
    return {
        'waec': {
            'catalog': list(WAEC_SUBJECTS),
            'general': list(WAEC_DEFAULT_SUBJECTS),
            'streams': waec_streams,
            'years': {},
        },
        'jamb': {
            'catalog': list(WAEC_SUBJECTS),   # JAMB draws from the same subject pool
            'general': list(_JAMB_GENERAL),
            'streams': {s: list(_JAMB_STREAMS.get(s, [])) for s in STREAMS},
            'years': {},
        },
    }


def _merge(base, saved):
    """Overlay a saved (possibly partial) config on top of the defaults."""
    if not isinstance(saved, dict):
        return base
    for exam in ('waec', 'jamb'):
        sec = saved.get(exam)
        if not isinstance(sec, dict):
            continue
        if isinstance(sec.get('catalog'), list):
            base[exam]['catalog'] = _dedup([str(x).strip() for x in sec['catalog'] if str(x).strip()])
        if isinstance(sec.get('general'), list):
            base[exam]['general'] = _dedup([str(x).strip() for x in sec['general'] if str(x).strip()])
        if isinstance(sec.get('streams'), dict):
            for st in STREAMS:
                v = sec['streams'].get(st)
                if isinstance(v, list):
                    base[exam]['streams'][st] = _dedup([str(x).strip() for x in v if str(x).strip()])
        if isinstance(sec.get('years'), dict):
            years = {}
            for y, ov in sec['years'].items():
                if not (str(y).isdigit() and isinstance(ov, dict)):
                    continue
                years[str(y)] = {
                    'general': _dedup([str(x).strip() for x in ov.get('general') or [] if str(x).strip()]),
                    'streams': {st: _dedup([str(x).strip() for x in (ov.get('streams') or {}).get(st) or []
                                            if str(x).strip()]) for st in STREAMS},
                }
            base[exam]['years'] = years
    return base


def get_config():
    """The effective per-school config (saved values overlaid on defaults)."""
    from models import SchoolSettings
    saved = SchoolSettings.get(_KEY, None)
    return _merge(_default_config(), saved)


def save_config(cfg):
    """Persist a full config dict for this school. Per-session sets ('years')
    already saved are kept unless ``cfg`` carries its own."""
    from models import SchoolSettings
    current = get_config()
    cfg = {e: dict(v) for e, v in (cfg or {}).items() if isinstance(v, dict)}
    for exam in ('waec', 'jamb'):
        if exam in cfg and 'years' not in cfg[exam]:
            cfg[exam]['years'] = current[exam].get('years', {})
    clean = _merge(_default_config(), cfg)
    SchoolSettings.set(_KEY, clean, 'json',
                       'Per-school WAEC/JAMB subject catalogue, general and per-stream compulsories')
    return clean


# ---------------------------------------------------------------------------
# Per-session (sitting-year) sets. Schools often swap one or two subjects from
# one WAEC sitting to the next, so a session can carry its own General +
# per-stream lists; any session without one uses the usual set above. Keyed by
# the exam year the app already uses for external exams (2025/2026 → 2026).
# ---------------------------------------------------------------------------

def current_exam_year():
    """The WAEC/JAMB sitting year of the active session, or None."""
    try:
        from utils.helpers import session_exam_year
        return session_exam_year()
    except Exception:
        return None


def sitting(exam, year=None):
    """{'general', 'streams', 'year', 'custom'} for a sitting year (default: the
    active session's). Falls back to the usual set when the year has none."""
    cfg = get_config().get(exam, {})
    y = str(year if year is not None else (current_exam_year() or ''))
    ov = cfg.get('years', {}).get(y)
    if ov:
        return {'general': list(ov['general']), 'streams': {st: list(ov['streams'].get(st, [])) for st in STREAMS},
                'year': y, 'custom': True}
    return {'general': list(cfg.get('general', [])),
            'streams': {st: list(cfg.get('streams', {}).get(st, [])) for st in STREAMS},
            'year': y or None, 'custom': False}


def set_sitting(exam, year, general, streams):
    """Give one sitting year its own set (or clear it with general=None)."""
    from models import SchoolSettings
    cfg = get_config()
    years = dict(cfg[exam].get('years', {}))
    if general is None:
        years.pop(str(year), None)
    else:
        years[str(year)] = {'general': list(general), 'streams': {st: list(streams.get(st, [])) for st in STREAMS}}
    cfg[exam]['years'] = years
    clean = _merge(_default_config(), cfg)
    SchoolSettings.set(_KEY, clean, 'json',
                       'Per-school WAEC/JAMB subject catalogue, general and per-stream compulsories')
    return clean


def sitting_changes(exam, year):
    """What a sitting year changes from the usual set, per stream's effective
    list: [{'stream', 'added', 'removed'}] (only streams that differ)."""
    cfg = get_config().get(exam, {})
    if str(year) not in cfg.get('years', {}):
        return []
    out = []
    for st in STREAMS:
        base = _dedup(list(cfg.get('general', [])) + list(cfg.get('streams', {}).get(st, [])))
        now = stream_subjects(exam, st, year)
        add = [x for x in now if x not in base]
        rem = [x for x in base if x not in now]
        if add or rem:
            out.append({'stream': st, 'added': add, 'removed': rem})
    return out


def stream_subjects(exam, stream, year=None):
    """The effective compulsory subject list for ``exam`` ('waec'/'jamb') and a
    given stream = general + that stream's extras, for a sitting year (default:
    the active session's). Returns ``[]`` for an unknown stream so callers behave
    like the old ``dict.get(stream)`` (falsy)."""
    if not stream or stream not in STREAMS:
        return []
    sec = sitting(exam, year)
    return _dedup(list(sec['general']) + list(sec['streams'].get(stream, [])))


def student_exam_year(student):
    """The sitting year a student will write WAEC/JAMB in: this session's for an
    SSS3 student, next session's for an SSS2 student (otherwise this session's)."""
    import re
    year = current_exam_year()
    if not year or student is None:
        return year
    try:
        from models import StudentEnrollment, ClassArmAssignment, SchoolClass
        from utils.helpers import get_active_term
        t = get_active_term()
        if t:
            row = (StudentEnrollment.query.join(ClassArmAssignment,
                                                StudentEnrollment.class_arm_assignment_id == ClassArmAssignment.id)
                   .join(SchoolClass, ClassArmAssignment.class_id == SchoolClass.id)
                   .filter(StudentEnrollment.student_id == student.id, ClassArmAssignment.term_id == t.id)
                   .with_entities(SchoolClass.name).first())
            if row and re.sub(r'[^a-z0-9]', '', (row[0] or '').lower()) in ('sss2', 'ss2', 'seniorsecondary2'):
                return year + 1
    except Exception:
        pass
    return year


def stream_waec_subjects(stream, year=None):
    """Effective compulsory WAEC subjects for a stream (per-school aware).

    Drop-in replacement for ``STREAM_WAEC_SUBJECTS.get(stream)``: returns a list
    (possibly empty) rather than ``None`` for an unknown stream.
    """
    return stream_subjects('waec', stream, year)


def stream_jamb_subjects(stream, year=None):
    """Effective compulsory JAMB subjects for a stream (per-school aware)."""
    return stream_subjects('jamb', stream, year)


def catalog(exam):
    return list(get_config().get(exam, {}).get('catalog', []))


def stream_map(exam, year=None):
    """{stream: effective compulsory subjects} for an exam — a per-school
    replacement for the STREAM_WAEC_SUBJECTS constant, used to feed the
    entry-page auto-fill JavaScript."""
    return {st: stream_subjects(exam, st, year) for st in STREAMS}


def stream_waec_map(year=None):
    return stream_map('waec', year)


def stream_jamb_map(year=None):
    return stream_map('jamb', year)
