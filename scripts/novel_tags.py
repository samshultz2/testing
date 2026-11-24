"""List how the question bank's English Novel questions are tagged, and which
novel card each tag counts toward.

    cd /opt/edusyncra && .venv/bin/python scripts/novel_tags.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        from models import db, MockJAMBQuestion, Subject
        from utils.myschool import novel_catalogue, same_novel, is_generic_novel_tag
        cards = novel_catalogue()
        rows = (db.session.query(MockJAMBQuestion.subject_id, MockJAMBQuestion.section, MockJAMBQuestion.topic,
                                 db.func.count(MockJAMBQuestion.id))
                .filter(MockJAMBQuestion.mock_exam_id.is_(None))
                .group_by(MockJAMBQuestion.subject_id, MockJAMBQuestion.section, MockJAMBQuestion.topic).all())
        names = {s.id: s.name for s in Subject.query.all()}
        print('Novel-section bank questions, by tag:')
        totals = defaultdict(int)
        any_novel = False
        for sid, sec, topic, n in sorted(rows, key=lambda r: -r[3]):
            if sec != 'novel':
                continue
            any_novel = True
            t = (topic or '').strip()
            if not t or is_generic_novel_tag(t):
                card = '-- NO TITLE (no mock can use these until tagged)'
            else:
                hit = next((c['title'] for c in cards if same_novel(c['value'], t)), None)
                card = hit or '-- its own card (not in the JAMB list)'
            totals[card] += n
            print(f'  {n:5}  {names.get(sid, sid)!s:20}  {t!r:55} -> {card}')
        if not any_novel:
            print('  (none - no bank question is in the Novel section)')
        print('\nTotals per card:')
        for card, n in sorted(totals.items(), key=lambda x: -x[1]):
            print(f'  {n:5}  {card}')
        lekki = [(names.get(sid, sid), sec, topic, n) for sid, sec, topic, n in rows
                 if sec != 'novel' and 'lekki' in (topic or '').lower()]
        if lekki:
            print('\nTagged "Lekki" but NOT in the Novel section (a mock will not draw these):')
            for sub, sec, topic, n in lekki:
                print(f'  {n:5}  {sub!s:20}  section={sec!r:22} {topic!r}')


if __name__ == '__main__':
    main()
