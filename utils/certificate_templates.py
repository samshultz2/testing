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
from utils import cert_layouts as _cl
from utils import transcript_templates as _tt


def _branding():
    try:
        from utils.school import document_branding
        return document_branding()
    except Exception:
        return {}


def _school_name():
    try:
        from utils.school import school_profile
        return school_profile().get('name') or ''
    except Exception:
        return ''


# Templates = one per LAYOUT ARCHETYPE (distinct structure + distinct palette).
_DESC = {
    'imperial': 'Gold centred crest, hero name and a three-column detail grid.',
    'sovereign': 'Left navy seal panel with the content set to the right.',
    'laureate': 'Full-width reversed-out title band over a boxed detail grid.',
    'regalia': 'Split diploma header (name beside crest) with three signatories.',
    'meridian': 'Right medallion column of seal, stamp and barcode.',
    'estate': 'Heritage frame with a large certifying passage and centred detail box.',
    'platinum': 'Minimalist, wide-spaced platinum layout.',
    'verdant': 'Award-ribbon header with a starred accent.',
    'oxford': 'Two-column body — certifying text beside a candidate-details panel.',
    'crown': 'Ornate luxury layout led by a gold medallion.',
    'chancellor': 'Executive layout with a right-hand signature & seal stack.',
}
TEMPLATES = {k: {'name': v['name'], 'landscape': True,
                 'description': _DESC.get(k, f"{v['name']} — a distinct certificate layout.")}
             for k, v in _cl.LAYOUTS.items()}
DEFAULT_TEMPLATE = 'imperial'


def list_templates():
    return [{'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in TEMPLATES.items()]


def resolve(key):
    return TEMPLATES.get(key) or TEMPLATES[DEFAULT_TEMPLATE]


def is_landscape(key):
    return True


def page_decorator(key):
    sn = _school_name()
    micro = (f"{sn}  ·  OFFICIAL DOCUMENT  ·  " if sn else 'OFFICIAL DOCUMENT  ·  ')
    return _th.page_decorator(_cl.theme_key(key), _branding(), microtext=micro, watermark_text=sn)


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
    'fee_clearance':   ('Fee Clearance Certificate', 'This is to certify that',
                        ['has fully settled all financial obligations to {school}{session} '
                         'and is hereby granted full fee clearance.'],
                        ('Bursar', 'Principal')),
    'graduation_clearance': ('Graduation Clearance Certificate', 'This is to certify that',
                             ['has met all academic and administrative requirements and is '
                              'hereby cleared for graduation from {school}{session}.'],
                             ('Registrar', 'Principal')),
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
    serial = (doc.document_number if doc and getattr(doc, 'document_number', None)
              else f"{(school.split()[0][:3].upper() if school else 'DOC')}/CERT/0001")
    bio = ctx.get('bio') or {}
    fields = [('Admission No.', getattr(st, 'student_id', '') or ''),
              ('Gender', getattr(st, 'gender', '') or ''),
              ('Date of Birth', bio.get('date_of_birth')),
              ('Academic Session', session),
              ('Graduation Year', ctx.get('grad_when') or ''),
              ('Class / Stream', ctx.get('klass') or ''),
              ('Certificate No.', serial),
              ('Date of Issue', issued)]
    return {
        'kicker': school,
        'motto': (ctx.get('school') or {}).get('motto') or '',
        'title': title,
        'lead': lead,
        'recipient': _esc(st.full_name),
        'body': [b.format(**fmt) for b in body_tpls],
        'fields': [(k, v) for k, v in fields if v],
        'meta': f"Issued on {issued}",
        'signatures': list(sigs),
        'seal_text': (school.split()[0][:12] if school else 'SEAL'),
        'serial': serial,
    }


def build_flowables(key, ctx):
    content = _content(ctx)
    content['_branding'] = _branding()
    return _cl.render(key, content)


def page_margins(key):
    # Landscape certificates: tight, even margins that clear the border art.
    return (14, 16, 16, 16)


def sample_ctx(school):
    ctx = _tt.sample_ctx(school)
    ctx.setdefault('doc_type', 'graduation')
    ctx.setdefault('award_subject', 'Mathematics')
    return ctx
