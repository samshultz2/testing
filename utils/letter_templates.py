"""Formal letter & reference document engine.

Renders the whole letters family — admission / acceptance / transfer /
withdrawal / student-confirmation letters and the recommendation & reference
letters (university, scholarship, employment, general) — from a data-driven
content spec × a design collection (see :mod:`utils.doc_themes`). Portrait,
letterhead style; every letter type therefore offers the full collection
library as selectable templates.

Standard design-module interface, so it plugs into :mod:`utils.graduate_docs`.
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


TEMPLATES = {k: {'name': v['name'], 'landscape': False,
                 'description': f"{v['name']} collection — themed letterhead, "
                                f"typography and signature style."}
             for k, v in _th.COLLECTIONS.items()}
DEFAULT_TEMPLATE = _th.DEFAULT_COLLECTION


def list_templates():
    return [{'key': k, 'name': v['name'], 'description': v['description']}
            for k, v in TEMPLATES.items()]


def resolve(key):
    return TEMPLATES.get(key) or TEMPLATES[DEFAULT_TEMPLATE]


def is_landscape(key):
    return False


def page_decorator(key):
    return _th.letter_decorator(key, _branding())


def page_margins(key):
    return (16, 18, 20, 20)


def _esc(v):
    from utils.web_exports import pdf_escape
    return pdf_escape(str(v if v is not None else ''))


def _pron(gender):
    g = (gender or '').strip().lower()
    if g.startswith('m'):
        return {'S': 'He', 's': 'he', 'o': 'him', 'p': 'his', 'r': 'himself'}
    if g.startswith('f'):
        return {'S': 'She', 's': 'she', 'o': 'her', 'p': 'her', 'r': 'herself'}
    return {'S': 'They', 's': 'they', 'o': 'them', 'p': 'their', 'r': 'themselves'}


# doc_type -> (title, salutation, [body templates], [signatures])
_SPEC = {
    'admission': ('Offer of Admission', 'Dear Parent/Guardian,',
                  ['Following a review of the application, we are pleased to offer '
                   '<b>{name}</b> provisional admission into <b>{school}</b>{intake}.',
                   'Admission is subject to the completion of enrolment formalities and '
                   'settlement of the applicable fees. We look forward to welcoming '
                   '{name} into our school community.'],
                  ('Principal', 'Registrar')),
    'acceptance': ('Acceptance of Offer', 'Dear Parent/Guardian,',
                   ['This is to confirm that the offer of admission made to <b>{name}</b> '
                    'at <b>{school}</b>{intake} has been formally accepted.',
                    'A place has accordingly been reserved and enrolment confirmed.'],
                   ('Principal', 'Registrar')),
    'confirmation': ('Confirmation of Student Status', 'To whom it may concern,',
                     ['This is to confirm that <b>{name}</b> (Admission No. {adm}) is a '
                      'bona fide student of <b>{school}</b>{klass}.',
                      'This letter is issued at the request of the parent/guardian for '
                      'whatever legitimate purpose it may serve.'],
                     ('Principal', 'Registrar')),
    'transfer': ('Transfer Certificate', 'To whom it may concern,',
                 ['This is to certify that <b>{name}</b> (Admission No. {adm}) was a '
                  'student of <b>{school}</b>{session} and is transferring to another '
                  'institution at the request of the parent/guardian.',
                  '{S} was of good conduct and left the school in good standing, with all '
                  'obligations to the school duly settled.'],
                 ('Principal', 'Registrar')),
    'withdrawal': ('Withdrawal Certificate', 'To whom it may concern,',
                   ['This is to certify that <b>{name}</b> (Admission No. {adm}) has been '
                    'formally withdrawn from <b>{school}</b>{session} at the request of '
                    'the parent/guardian.',
                    '{S} left the school in good standing.'],
                   ('Principal', 'Registrar')),
    'recommendation': ('Letter of Recommendation', 'To whom it may concern,',
                       ['I write to recommend <b>{name}</b>, a student of <b>{school}</b>{session}.',
                        'Throughout {p} time with us, {s} demonstrated dedication, integrity '
                        'and a strong work ethic{avg}. {S} related well with staff and peers '
                        'and conducted {r} in a manner worthy of emulation.',
                        'I recommend {o} without reservation.'],
                       ('Principal', 'Registrar')),
    'university_recommendation': ('University Recommendation', 'To the Admissions Committee,',
                                  ['It is my pleasure to recommend <b>{name}</b> for '
                                   'admission to your esteemed institution. {name} was a '
                                   'student of <b>{school}</b>{session}.',
                                   '{S} is intellectually capable, diligent and '
                                   'well-motivated{avg}, and possesses the character and '
                                   'discipline to excel in higher education.',
                                   'I therefore recommend {o} most highly.'],
                                  ('Principal', 'Registrar')),
    'scholarship_recommendation': ('Scholarship Recommendation', 'To the Scholarship Committee,',
                                   ['I am pleased to recommend <b>{name}</b>, a student of '
                                    '<b>{school}</b>{session}, for the award of a scholarship.',
                                    '{S} has consistently demonstrated academic promise{avg}, '
                                    'discipline and commitment, and would make excellent use '
                                    'of such support.',
                                    'I recommend {o} for your favourable consideration.'],
                                   ('Principal', 'Registrar')),
    'employment_recommendation': ('Employment Recommendation', 'To whom it may concern,',
                                  ['I write in support of <b>{name}</b>, a graduate of '
                                   '<b>{school}</b>{session}.',
                                   '{S} is reliable, hardworking and of good character{avg}, '
                                   'and I am confident {s} will be a valuable addition to '
                                   'any organisation.',
                                   'I recommend {o} without reservation.'],
                                  ('Principal', 'Registrar')),
    'reference': ('Reference Letter', 'To whom it may concern,',
                  ['This letter is issued in respect of <b>{name}</b>, who was a student '
                   'of <b>{school}</b>{session}.',
                   'During this period {s} was of good conduct and character{avg}. This '
                   'reference is provided at {p} request.'],
                  ('Principal', 'Registrar')),
}
DEFAULT_SPEC = ('Letter', 'To whom it may concern,',
                ['This letter is issued in respect of <b>{name}</b> of <b>{school}</b>.'],
                ('Principal', 'Registrar'))


def _content(ctx):
    st = ctx['student']
    school = ctx.get('school') or {}
    school_name = school.get('name') or 'this school'
    dt = ctx.get('doc_type') or 'reference'
    title, salutation, body_tpls, sigs = _SPEC.get(dt, DEFAULT_SPEC)
    pron = _pron(getattr(st, 'gender', None))
    session = ctx.get('grad_session') or ctx.get('admission_session') or ''
    klass = ctx.get('klass') or ''
    cum = (ctx.get('academic') or {}).get('cumulative')
    doc = ctx.get('doc')
    issued = (doc.created_at.strftime('%d %B %Y') if doc and getattr(doc, 'created_at', None)
              else date.today().strftime('%d %B %Y'))
    fmt = {
        'name': _esc(st.full_name),
        'adm': _esc(getattr(st, 'student_id', '') or ''),
        'school': _esc(school_name),
        'session': f" during the {_esc(session)} academic session" if session else '',
        'intake': f" for the {_esc(session)} academic session" if session else '',
        'klass': f" in {_esc(klass)}" if klass else '',
        'avg': f", maintaining a cumulative average of {cum}%" if cum is not None else '',
        'S': pron['S'], 's': pron['s'], 'o': pron['o'], 'p': pron['p'], 'r': pron['r'],
    }
    ref = (doc.document_number if doc and getattr(doc, 'document_number', None)
           else f"{school_name[:3].upper()}/DOC")
    return {
        'school': {'name': school_name, 'address': school.get('address'),
                   'phone': school.get('phone'), 'email': school.get('email'),
                   'website': school.get('website')},
        'ref': ref, 'date': issued, 'title': title, 'salutation': salutation,
        'body': [b.format(**fmt) for b in body_tpls],
        'closing': 'Yours faithfully,',
        'signatures': list(sigs),
        'seal_text': (school_name.split()[0][:12] if school_name else 'SEAL'),
    }


def build_flowables(key, ctx):
    return _th.render_letter(key, _content(ctx), branding=_branding())


def sample_ctx(school):
    ctx = _tt.sample_ctx(school)
    ctx.setdefault('doc_type', 'recommendation')
    ctx.setdefault('klass', 'SS 3')
    return ctx
