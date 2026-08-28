"""Import a JAMB subject syllabus into the coded syllabus tables.

The syllabi are DATA, never hard-coded application logic: an admin pastes/uploads
one (JSON preferred for hierarchy, CSV also supported) and this module parses it
into a normalized form and reconciles it against what's already stored for the
subject — matching on each item's stable ``code`` (e.g. ``MATH.NUM.1.A``), never
on its name:

* codes present in the paste but not the DB  -> added
* codes present in both                      -> renamed (name/order/counts updated)
* codes present in the DB but not the paste  -> removed

JSON shape (hierarchical, relative codes; the subject ``prefix`` is prepended to
form the stable code)::

    {
      "subject": "Mathematics", "code": "JAMB-MATH",
      "prefix": "MATH", "version": "2026", "total": 40,
      "blueprint": [{"section": "number", "label": "Number & Numeration",
                     "count": 10, "passage": false, "per_passage": 5}, ...],
      "sections": [
        {"code": "NUM", "name": "Number and Numeration", "topics": [
           {"code": "NUM.1", "name": "Number bases", "items": [
              {"code": "NUM.1.A", "name": "Operations in bases 2-10"}]}]}]
    }

CSV shape (flat; codes are already full/stable)::

    code,kind,name,parent,count,passage,per_passage
    MATH.NUM,section,Number and Numeration,,10,,
    MATH.NUM.1,topic,Number bases,MATH.NUM,,,
    MATH.NUM.1.A,item,Operations in bases 2-10,MATH.NUM.1,,,
"""
from __future__ import annotations

import csv
import io
import json
import re

_KINDS = ('section', 'topic', 'item')


class SyllabusImportError(ValueError):
    """Raised for malformed syllabus input (bad JSON/CSV, missing codes, etc.)."""


def _derive_prefix(data):
    """A stable code prefix like 'MATH' from explicit prefix, else the code
    ('JAMB-MATH' -> 'MATH'), else the subject name initials."""
    pref = (data.get('prefix') or '').strip()
    if pref:
        return re.sub(r'[^A-Z0-9]', '', pref.upper())
    code = (data.get('code') or '').strip()
    if code:
        tail = code.split('-')[-1]
        return re.sub(r'[^A-Z0-9]', '', tail.upper())
    name = (data.get('subject') or '').strip()
    return re.sub(r'[^A-Z0-9]', '', name.upper())[:6] or 'SUBJ'


def _clean_code(raw):
    """Normalize a relative code fragment: uppercase, keep alnum and dots."""
    return re.sub(r'[^A-Z0-9.]', '', (raw or '').strip().upper()).strip('.')


def parse_json(text_or_obj):
    """Parse the hierarchical JSON form into the normalized structure."""
    if isinstance(text_or_obj, (dict, list)):
        data = text_or_obj
    else:
        try:
            data = json.loads(text_or_obj)
        except (ValueError, TypeError) as e:
            raise SyllabusImportError(f'Invalid JSON: {e}')
    if not isinstance(data, dict):
        raise SyllabusImportError('Syllabus JSON must be an object.')

    prefix = _derive_prefix(data)
    nodes = []

    def full(rel):
        rel = _clean_code(rel)
        if not rel:
            raise SyllabusImportError('Every section/topic/item needs a "code".')
        return f'{prefix}.{rel}'

    for si, sec in enumerate(data.get('sections') or []):
        sec_code = full(sec.get('code'))
        nodes.append({'code': sec_code, 'kind': 'section', 'name': (sec.get('name') or '').strip(),
                      'parent': None, 'order': si,
                      'question_count': sec.get('count'), 'passage': bool(sec.get('passage')),
                      'per_passage': sec.get('per_passage')})
        for ti, top in enumerate(sec.get('topics') or []):
            top_code = full(top.get('code'))
            nodes.append({'code': top_code, 'kind': 'topic', 'name': (top.get('name') or '').strip(),
                          'parent': sec_code, 'order': ti,
                          'question_count': None, 'passage': False, 'per_passage': None})
            for ii, item in enumerate(top.get('items') or []):
                nodes.append({'code': full(item.get('code')), 'kind': 'item',
                              'name': (item.get('name') or '').strip(),
                              'parent': top_code, 'order': ii,
                              'question_count': None, 'passage': False, 'per_passage': None})

    blueprint = _clean_blueprint(data.get('blueprint'))
    return {
        'subject': (data.get('subject') or '').strip(),
        'code': (data.get('code') or '').strip() or None,
        'prefix': prefix,
        'version': (str(data.get('version')).strip() if data.get('version') else None),
        'total': data.get('total'),
        'blueprint': blueprint,
        'nodes': nodes,
    }


def _clean_blueprint(bp):
    if not bp:
        return None
    out = []
    for s in bp:
        sec = (s.get('section') or '').strip()
        if not sec:
            continue
        out.append({
            'section': sec,
            'label': (s.get('label') or sec.replace('_', ' ').title()).strip(),
            'count': int(s.get('count') or 0),
            'passage': bool(s.get('passage')),
            'per_passage': int(s['per_passage']) if s.get('per_passage') else 5,
        })
    return out or None


def parse_csv(text, subject=None, version=None):
    """Parse the flat CSV form. Codes are already full/stable; ``parent`` is the
    parent's full code. Section rows may carry a ``count`` for the draw blueprint.
    """
    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        raise SyllabusImportError(f'Invalid CSV: {e}')
    if not reader.fieldnames or 'code' not in [f.strip().lower() for f in reader.fieldnames]:
        raise SyllabusImportError('CSV needs a header row with at least: code,kind,name')

    def col(row, *names):
        for n in names:
            for k, v in row.items():
                if (k or '').strip().lower() == n:
                    return (v or '').strip()
        return ''

    nodes, blueprint = [], []
    for i, row in enumerate(reader):
        code = _clean_code(col(row, 'code'))
        if not code:
            continue
        kind = (col(row, 'kind') or 'item').lower()
        if kind not in _KINDS:
            kind = 'item'
        cnt = col(row, 'count', 'question_count', 'questions')
        node = {
            'code': code, 'kind': kind, 'name': col(row, 'name', 'title'),
            'parent': _clean_code(col(row, 'parent', 'parent_code')) or None,
            'order': i,
            'question_count': int(cnt) if cnt.isdigit() else None,
            'passage': col(row, 'passage').lower() in ('1', 'true', 'yes', 'y'),
            'per_passage': int(col(row, 'per_passage')) if col(row, 'per_passage').isdigit() else None,
        }
        nodes.append(node)
        if kind == 'section' and node['question_count']:
            blueprint.append({'section': code.split('.')[-1].lower(), 'label': node['name'],
                              'count': node['question_count'], 'passage': node['passage'],
                              'per_passage': node['per_passage'] or 5})
    if not nodes:
        raise SyllabusImportError('CSV contained no syllabus rows.')
    prefix = _clean_code(nodes[0]['code'].split('.')[0])
    return {
        'subject': (subject or '').strip(), 'code': None, 'prefix': prefix,
        'version': (str(version).strip() if version else None), 'total': None,
        'blueprint': blueprint or None, 'nodes': nodes,
    }


def parse(text, fmt='auto', subject=None, version=None):
    """Parse pasted/uploaded syllabus text into the normalized structure."""
    fmt = (fmt or 'auto').lower()
    if fmt == 'json' or (fmt == 'auto' and (text or '').lstrip()[:1] in '{['):
        return parse_json(text)
    return parse_csv(text, subject=subject, version=version)


def reconcile_syllabus(subject, data):
    """Upsert the parsed syllabus for ``subject`` (a Subject row), matching nodes
    by stable code. Returns a diff summary ``{added, renamed, removed, counts}``.
    """
    from models import db, MockJAMBSyllabus, MockJAMBSyllabusNode

    incoming = {n['code']: n for n in data['nodes']}
    if not incoming:
        raise SyllabusImportError('The syllabus has no items.')

    syll = MockJAMBSyllabus.query.filter_by(subject_id=subject.id).first()
    if syll is None:
        syll = MockJAMBSyllabus(subject_id=subject.id)
        db.session.add(syll)
    syll.subject_name = data.get('subject') or subject.name
    syll.code = data.get('code')
    syll.prefix = data.get('prefix')
    syll.version = data.get('version')
    syll.total_questions = data.get('total')
    syll.blueprint = json.dumps(data['blueprint']) if data.get('blueprint') else None
    db.session.flush()

    existing = {n.code: n for n in syll.nodes.all()}
    added, renamed, removed = [], [], []
    by_code = {}

    for code, nd in incoming.items():
        row = existing.get(code)
        if row is None:
            row = MockJAMBSyllabusNode(syllabus_id=syll.id, code=code)
            db.session.add(row)
            added.append(code)
        elif (row.name or '') != (nd.get('name') or ''):
            renamed.append({'code': code, 'from': row.name, 'to': nd.get('name')})
        row.kind = nd.get('kind')
        row.name = nd.get('name')
        row.sort_order = nd.get('order') or 0
        row.question_count = nd.get('question_count')
        row.passage = bool(nd.get('passage'))
        row.per_passage = nd.get('per_passage')
        by_code[code] = row
    db.session.flush()

    for code, nd in incoming.items():
        p = nd.get('parent')
        by_code[code].parent_id = by_code[p].id if p and p in by_code else None

    for code, row in existing.items():
        if code not in incoming:
            removed.append(code)
            db.session.delete(row)

    db.session.commit()
    return {
        'added': added, 'renamed': renamed, 'removed': removed,
        'sections': sum(1 for n in incoming.values() if n['kind'] == 'section'),
        'topics': sum(1 for n in incoming.values() if n['kind'] == 'topic'),
        'items': sum(1 for n in incoming.values() if n['kind'] == 'item'),
    }


def import_syllabus(subject, text, fmt='auto', version=None):
    """Parse and reconcile in one call. Returns the diff summary."""
    data = parse(text, fmt=fmt, subject=subject.name, version=version)
    return reconcile_syllabus(subject, data)
