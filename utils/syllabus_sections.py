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
    try:
        valid = {x.get('section') for x in json.load(open(path, encoding='utf-8')).get('blueprint') or []}
    except Exception:
        valid = set()
    n = 0
    for code, node in by_code.items():
        cur = (node.blueprint_section or '').strip()
        if not cur and want.get(code):
            node.blueprint_section = want[code]
            n += 1
        elif cur and valid and cur not in valid and cur != 'novel':
            # stale: points at a section the paper blueprint no longer has
            node.blueprint_section = want.get(code)
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


# Earlier bundled blueprints as full {section: count} maps: a stored blueprint
# equal to one of these came from the app, not from someone's own edits.
# (Subjects keyed by the bundled file's "subject" name, lower-cased.)
_PREVIOUS_FULL = {
    "agricultural science": [{"general_agric": 7, "agronomy": 13, "animal": 7, "agric_econ": 7, "agric_tech": 6}],
    "biology": [{"cell": 6, "nutrition": 5, "transport_respiration": 6, "excretion_regulation": 4, "support_movement": 3, "reproduction": 5, "ecology": 6, "genetics_evolution": 5}],
    "chemistry": [{"separation": 2, "atomic_bonding": 6, "stoichiometry": 6, "states_gas": 4, "energetics_rates": 5, "acids_bases_salts": 5, "redox_electro": 4, "periodic_metals": 4, "organic": 4}],
    "christian religious studies": [{"ot_creation": 9, "ot_prophets": 7, "gospels_acts": 16, "epistles": 8}],
    "commerce": [{"trade": 18, "business": 15, "finance": 7}],
    "computer studies": [{"foundations": 8, "applications": 11, "ict": 8, "programming": 10, "ethics": 3}],
    "economics": [{"micro": 18, "macro": 9, "development": 9, "international": 4}],
    "geography": [{"practical": 6, "physical": 16, "human": 9, "regional": 9}],
    "government": [{"concepts": 14, "nigeria": 10, "constitution": 8, "international": 8}],
    "history": [{"nig_pre1800": 5, "nig_1800_1900": 9, "nig_1900_1960": 7, "nig_since_1960": 8, "africa": 11}],
    "islamic studies": [{"quran_hadith": 14, "tawhid_fiqh": 16, "islamic_history": 10}],
    "mathematics": [{"number": 10, "algebra": 12, "geometry": 10, "calculus": 4, "statistics": 4}],
    "physics": [{"measurement": 2, "mechanics": 12, "thermal": 6, "waves_optics": 8, "electromagnetism": 10, "modern": 2}],
    "principles of accounts": [{"principles": 20, "final": 6, "specialised": 14}],
}


def sync_blueprint(subject, commit=True):
    """Bring the subject's stored (imported) blueprint up to the bundled one when
    it still holds an earlier bundled version unchanged. Returns a list of
    ``(section, old, new)`` count changes ([] when nothing to do)."""
    from models import db, MockJAMBSyllabus
    from utils.myschool import norm_subject
    syll = MockJAMBSyllabus.query.filter_by(subject_id=subject.id).first()
    path = _bundled_path(subject.name)
    if not syll or not path:
        return []
    try:
        stored = json.loads(syll.blueprint) if syll.blueprint else []
        data = json.load(open(path, encoding='utf-8'))
        bundled = data.get('blueprint') or []
    except Exception:
        return []
    if not stored and bundled:
        # imported before the file had a blueprint: adopt it (nothing to overwrite)
        syll.blueprint = json.dumps(bundled)
        if data.get('total') and not syll.total_questions:
            syll.total_questions = int(data['total'])
        if commit:
            db.session.commit()
        return [(x.get('section'), None, int(x.get('count', 0))) for x in bundled]
    have = {x.get('section'): int(x.get('count', 0)) for x in stored}
    new = {x.get('section'): int(x.get('count', 0)) for x in bundled}
    if not bundled or have == new:
        return []
    olds = [{**new, **diff} for diff in _PREVIOUS_BLUEPRINTS.get(norm_subject(subject.name), [])]
    olds += [m for k, ms in _PREVIOUS_FULL.items() if norm_subject(k) == norm_subject(subject.name) for m in ms]
    for prev in olds:
        if have == prev:
            changes = [(k, have.get(k), new.get(k)) for k in new if have.get(k) != new.get(k)]
            syll.blueprint = json.dumps(bundled)
            if commit:
                db.session.commit()
            return changes
    return []
