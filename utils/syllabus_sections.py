"""Keep imported syllabi's topic -> paper-section mappings in step with the
bundled syllabus files, and re-section coded questions from their code.

* ``sync_mappings(subject)``: copy ``blueprint_section`` from the bundled
  data/jamb_syllabi/<subject>.json onto the subject's imported syllabus nodes
  (matched by code) where the node has none — never overwriting a mapping
  someone set.
* ``resection(subject, apply)``: for every bank question that already carries a
  syllabus code, set its paper section from that code's mapping (English: from
  the question's wording). No AI, no tokens. Novel questions never move.
"""
import json
import os
from collections import Counter


def _bundled_path(subject_name):
    from utils.myschool import norm_subject
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'jamb_syllabi')
    key = norm_subject(subject_name)
    for f in os.listdir(base):
        if not f.endswith('.json'):
            continue
        try:
            d = json.load(open(os.path.join(base, f), encoding='utf-8'))
        except Exception:
            continue
        if norm_subject(d.get('subject') or f[:-5].replace('_', ' ')) == key:
            return os.path.join(base, f)
    return None


def sync_mappings(subject, commit=True):
    """Returns the number of nodes given a mapping (``commit=False`` leaves the
    change pending, for a dry run that is rolled back afterwards)."""
    from models import db
    from utils.jamb_syllabus_import import parse_json
    from utils.mock_bank_coded_retag import coded_nodes
    by_code, _s = coded_nodes(subject.id)
    path = _bundled_path(subject.name)
    if not by_code or not path:
        return 0
    try:
        parsed = parse_json(json.load(open(path, encoding='utf-8')))
    except Exception:
        return 0
    want = {n['code']: n['blueprint_section'] for n in parsed['nodes'] if n.get('blueprint_section')}
    n = 0
    for code, node in by_code.items():
        if not (node.blueprint_section or '').strip() and want.get(code):
            node.blueprint_section = want[code]
            n += 1
    if n and commit:
        db.session.commit()
    return n


def resection(subject, apply=False, limit_samples=6):
    """Re-section coded questions from their code. Returns (moves Counter, samples)."""
    from models import db, MockJAMBQuestion
    from utils.jamb_blueprint import sections_for
    from utils.mock_bank_coded_retag import coded_nodes, place_section
    by_code, _s = coded_nodes(subject.id)
    if not by_code:
        return Counter(), {}
    by_id = {n.id: n for n in by_code.values()}
    valid = {s['section'] for s in sections_for(subject.name)}
    rows = (MockJAMBQuestion.query.filter(MockJAMBQuestion.subject_id == subject.id,
                                          MockJAMBQuestion.mock_exam_id.is_(None),
                                          MockJAMBQuestion.passage_id.is_(None),
                                          MockJAMBQuestion.syllabus_item_code.isnot(None),
                                          MockJAMBQuestion.syllabus_item_code != '')
            .order_by(MockJAMBQuestion.id).all())
    moves, samples = Counter(), {}
    for q in rows:
        node = by_code.get(q.syllabus_item_code)
        if node is None:
            continue
        before = q.section
        place_section(q, subject.name, node, by_id, valid)
        if q.section != before:
            key = '%s -> %s' % (before or '(no section)', q.section)
            moves[key] += 1
            lst = samples.setdefault(key, [])
            if len(lst) < limit_samples:
                lst.append('#%s %s | %s' % (q.id, q.syllabus_item_code, (q.question_text or '')[:80].replace('\n', ' ')))
            if not apply:
                q.section = before
    if apply:
        db.session.commit()
    else:
        db.session.rollback()
    return moves, samples


# Earlier bundled blueprints, as {section: count} changes from the current file.
# A school's stored blueprint that still equals one of these exactly was never
# edited by hand, so it is safe to bring up to date.
_PREVIOUS_BLUEPRINTS = {
    # Summary was its own 5-question passage section; JAMB sets those questions
    # on the comprehension passages, so Comprehension is now 10 and Summary 0.
    'english language': [{'comprehension': 5, 'summary': 5}],
}


def sync_blueprint(subject, commit=True):
    """Bring the subject's stored (imported) blueprint up to the bundled one when
    it still holds an earlier bundled version unchanged. Returns a list of
    ``(section, old, new)`` count changes ([] when nothing to do)."""
    from models import db, MockJAMBSyllabus
    from utils.myschool import norm_subject
    syll = MockJAMBSyllabus.query.filter_by(subject_id=subject.id).first()
    path = _bundled_path(subject.name)
    if not syll or not syll.blueprint or not path:
        return []
    try:
        stored = json.loads(syll.blueprint)
        bundled = json.load(open(path, encoding='utf-8')).get('blueprint') or []
    except Exception:
        return []
    have = {x.get('section'): int(x.get('count', 0)) for x in stored}
    new = {x.get('section'): int(x.get('count', 0)) for x in bundled}
    if not bundled or have == new:
        return []
    for diff in _PREVIOUS_BLUEPRINTS.get(norm_subject(subject.name), []):
        if have == {**new, **diff}:
            changes = [(k, have.get(k), new.get(k)) for k in new if have.get(k) != new.get(k)]
            syll.blueprint = json.dumps(bundled)
            if commit:
                db.session.commit()
            return changes
    return []
