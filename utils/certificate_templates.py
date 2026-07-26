"""Certificate & award document engine.

One engine renders the whole certificate family — Graduation, Completion,
Attendance, Character, and the award certificates (Merit, Best Graduating, Best
in Subject, Leadership, Sports, Academic Excellence, …). The *look* comes from a
design **collection** (see :mod:`utils.doc_themes`), so every one of these
document types instantly offers the full library of collections as selectable
templates.

Exposes the standard design-module interface shared with the transcript / SLC /
statement modules, so it plugs straight into :mod:`utils.graduate_docs`:
``TEMPLATES``, ``DEFAULT_TEMPLATE``, ``list_templates``, ``resolve``,
``build_flowables``, ``page_decorator``, ``is_landscape``, ``sample_ctx``.
"""
from datetime import date

from utils import doc_themes as _th
from utils import transcript_templates as _tt


def _branding():
    try:
        from utils.school import document_branding
        return document_branding()
    except Exception:
        return {}


# Templates = one per design collection (all landscape certificates).
TEMPLATES = {k: {'name': v['name'], 'landscape': True,
                 'description': f"{v['name']} collection — a distinct palette, "
                                f"typography, border art and seal."}
             for k, v in _th.COLLECTIONS.items()}
DEFAULT_TEMPLATE = _th.DEFAULT_COLLECTION


def list_templates():
    return [{'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in TEMPLATES.items()]


def resolve(key):
    return TEMPLATES.get(key) or TEMPLATES[DEFAULT_TEMPLATE]


def is_landscape(key):
    return True


def page_decorator(key):
    return _th.page_decorator(key, _branding())


def _pron(gender):
    g = (gender or '').strip().lower()
    if g.startswith('m'):
        return {'s': 'he', 'o': 'him', 'p': 'his', 'r': 'himself'}
    if g.startswith('f'):
        return {'s': 'she', 'o': 'her', 'p': 'her', 'r': 'herself'}
    return {'s': 'they', 'o': 'them', 'p': 'their', 'r': 'themselves'}


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v if v is not None else ''))


# doc_type → (title, lead, body-template(s), signatures). Body templates use
# .format(**fmt) with the resolved fields below.
_SPEC = {
    'graduation':      ('Graduation Certificate', 'This is to certify that',
                        ['has satisfied all the requirements of the Senior Secondary programme at '
                         '{school}{session} and is hereby awarded this Certificate of Graduation.'],
                        ('Principal', 'Registrar')),
    'completion':      ('Certificate of Completion', 'This is to certify that',
                        ['has successfully completed the prescribed programme of study at {school}{session}.'],
                        ('Principal', 'Registrar')),
    'attendance_cert': ('Certificate of Attendance', 'This is to certify that',
                        ['was in regular attendance at {school} during the {session_plain} academic '
                         'session and participated fully in the life of the school.'],
                        ('Principal', 'Form Master')),
    'character_cert':  ('Certificate of Good Character', 'This is to certify that',
                        ['was a student of {school} and, throughout {p} time in the school, maintained '
                         'good conduct, discipline and moral character.'],
                        ('Principal', 'Registrar')),
    'merit_award':     ('Certificate of Merit', 'This certificate is proudly presented to',
                        ['in recognition of meritorious performance, diligence and dedication '
                         'demonstrated at {school}.'],
                        ('Principal', 'Coordinator')),
    'best_graduating': ('Best Graduating Student', 'This award is proudly conferred upon',
                        ['as the Best Graduating Student of {school}{session}, in recognition of '
                         'outstanding overall academic achievement.'],
                        ('Principal', 'Registrar')),
    'best_subject':    ('Best in Subject Award', 'This award is proudly presented to',
                        ['for outstanding performance and distinction in {subject} at {school}.'],
                        ('Principal', 'Head of Department')),
    'leadership_award': ('Leadership Award', 'This award is proudly presented to',
                         ['in recognition of exemplary leadership, integrity and service to the '
                          '{school} community.'],
                         ('Principal', 'Coordinator')),
    'sports_award':    ('Sports Award', 'This award is proudly presented to',
                        ['in recognition of outstanding sportsmanship and athletic achievement at {school}.'],
                        ('Principal', 'Sports Master')),
    'excellence_award': ('Academic Excellence Award', 'This award is proudly presented to',
                         ['in recognition of exceptional academic excellence and consistent '
                          'distinction at {school}.'],
                         ('Principal', 'Registrar')),
}
DEFAULT_SPEC = ('Certificate', 'This is to certify that',
                ['was a student of {school}.'], ('Principal', 'Registrar'))


def _content(ctx):
    st = ctx['student']
    school = (ctx.get('school') or {}).get('name') or 'this school'
    dt = ctx.get('doc_type') or 'graduation'
    title, lead, body_tpls, sigs = _SPEC.get(dt, DEFAULT_SPEC)
    pron = _pron(getattr(st, 'gender', None))
    session = ctx.get('grad_session') or ctx.get('admission_session') or ''
    fmt = {
        'school': _esc(school),
        'session': f" in the {_esc(session)} academic session" if session else '',
        'session_plain': _esc(session) or 'current',
        'p': pron['p'],
        'subject': _esc(ctx.get('award_subject') or 'their subject'),
    }
    doc = ctx.get('doc')
    issued = (doc.created_at.strftime('%d %B %Y') if doc and getattr(doc, 'created_at', None)
              else date.today().strftime('%d %B %Y'))
    meta_bits = []
    if session:
        meta_bits.append(f"Session: {_esc(session)}")
    meta_bits.append(f"Issued on {issued}")
    return {
        'kicker': school,
        'title': title,
        'lead': lead,
        'recipient': _esc(st.full_name),
        'body': [b.format(**fmt) for b in body_tpls],
        'meta': '  ·  '.join(meta_bits),
        'signatures': list(sigs),
        'seal_text': (school.split()[0][:12] if school else 'SEAL'),
    }


def build_flowables(key, ctx):
    return _th.render_certificate(key, _content(ctx), branding=_branding())


def page_margins(key):
    # Landscape certificates: tight, even margins that clear the border art.
    return (14, 16, 16, 16)


def sample_ctx(school):
    ctx = _tt.sample_ctx(school)
    ctx.setdefault('doc_type', 'graduation')
    ctx.setdefault('award_subject', 'Mathematics')
    return ctx
