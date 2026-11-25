"""Check how one myschool.ng question page is read (novel note, book, stem).

    .venv/bin/python scripts/myschool_novel_check.py "https://myschool.ng/classroom/english-language/71625?exam_type=jamb&exam_year=2025"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from utils import myschool as ms
    url = sys.argv[1] if len(sys.argv) > 1 else ''
    if not url:
        print(__doc__); return
    html = ms.fetch(url, ms._session())
    if not html:
        print('Could not load the page (network / DNS?).'); return
    p = ms.parse_detail(html) or {}
    print('stem       :', (p.get('stem') or '')[:120])
    print('is_novel   :', p.get('is_novel'))
    print('novel_title:', p.get('novel_title'))
    print('note       :', (p.get('instruction') or '')[:160])
    if not p.get('is_novel'):
        low = html.lower()
        i = low.find('from the novel')
        print('\n"from the novel" in raw HTML:', i >= 0)
        if i >= 0:
            print(html[max(0, i - 300):i + 200])


if __name__ == '__main__':
    main()
