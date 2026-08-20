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
        },
        'jamb': {
            'catalog': list(WAEC_SUBJECTS),   # JAMB draws from the same subject pool
            'general': list(_JAMB_GENERAL),
            'streams': {s: list(_JAMB_STREAMS.get(s, [])) for s in STREAMS},
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
    return base


def get_config():
    """The effective per-school config (saved values overlaid on defaults)."""
    from models import SchoolSettings
    saved = SchoolSettings.get(_KEY, None)
    return _merge(_default_config(), saved)


def save_config(cfg):
    """Persist a full config dict for this school."""
    from models import SchoolSettings
    clean = _merge(_default_config(), cfg)
    SchoolSettings.set(_KEY, clean, 'json',
                       'Per-school WAEC/JAMB subject catalogue, general and per-stream compulsories')
    return clean


def stream_subjects(exam, stream):
    """The effective compulsory subject list for ``exam`` ('waec'/'jamb') and a
    given stream = general + that stream's extras. Returns ``[]`` for an unknown
    stream so callers behave like the old ``dict.get(stream)`` (falsy)."""
    if not stream or stream not in STREAMS:
        return []
    cfg = get_config().get(exam, {})
    subs = list(cfg.get('general', [])) + list(cfg.get('streams', {}).get(stream, []))
    return _dedup(subs)


def stream_waec_subjects(stream):
    """Effective compulsory WAEC subjects for a stream (per-school aware).

    Drop-in replacement for ``STREAM_WAEC_SUBJECTS.get(stream)``: returns a list
    (possibly empty) rather than ``None`` for an unknown stream.
    """
    return stream_subjects('waec', stream)


def stream_jamb_subjects(stream):
    """Effective compulsory JAMB subjects for a stream (per-school aware)."""
    return stream_subjects('jamb', stream)


def catalog(exam):
    return list(get_config().get(exam, {}).get('catalog', []))


def stream_map(exam):
    """{stream: effective compulsory subjects} for an exam — a per-school
    replacement for the STREAM_WAEC_SUBJECTS constant, used to feed the
    entry-page auto-fill JavaScript."""
    return {st: stream_subjects(exam, st) for st in STREAMS}


def stream_waec_map():
    return stream_map('waec')


def stream_jamb_map():
    return stream_map('jamb')
