"""Show what the diagram finder sees on one myschool.ng question page.

    .venv/bin/python scripts/myschool_figure_debug.py "https://myschool.ng/classroom/chemistry/31331?exam_type=jamb&exam_year=1984"

Add --browser to also read the page after JavaScript runs (needs Playwright).
Paste the output back when a diagram isn't being picked up.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def describe(html, label):
    from bs4 import BeautifulSoup
    from utils import myschool as ms
    print(f"\n===== {label}: {len(html or '')} characters of HTML =====")
    if not html:
        print("(no HTML — the page could not be fetched)")
        return
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    print("h1:", (h1.get_text(" ", strip=True)[:120] if h1 else None))
    if h1 is not None:
        chain, n = [], h1
        for _ in range(4):
            n = n.parent
            if n is None:
                break
            chain.append(f"<{n.name} class='{' '.join(n.get('class') or [])}'>")
        print("h1 parents:", " > ".join(chain))
    imgs = soup.find_all("img")
    print(f"<img> tags: {len(imgs)}")
    for im in imgs[:25]:
        attrs = {k: (v if isinstance(v, str) else " ".join(v))[:140] for k, v in im.attrs.items()}
        par = im.parent
        print("  -", attrs, "| parent:", f"<{par.name} class='{' '.join(par.get('class') or [])}'>" if par else None)
    for tag in ("svg", "canvas", "picture", "object", "embed", "iframe"):
        found = soup.find_all(tag)
        if found:
            print(f"<{tag}> tags: {len(found)}", [str(f)[:160] for f in found[:3]])
    bg = soup.find_all(style=re.compile(r"background-image", re.I))
    if bg:
        print("background-image styles:", [b.get("style")[:160] for b in bg[:5]])
    urls = sorted(set(re.findall(r"""(?:https?:)?//[^\s"'<>)]+\.(?:png|jpe?g|gif|webp|svg)|/(?:storage|_ipx)/[^\s"'<>)]+""", html)))
    print(f"image-like URLs anywhere in the HTML: {len(urls)}")
    for u in urls[:30]:
        print("  ", u[:180])
    p = ms.parse_detail(html)
    if not p:
        print("parse_detail: could not read the question (stem/options/answer)")
    else:
        print("parse_detail → image_url:", (p.get("image_url") or "")[:180] or None,
              "| svg:", bool(p.get("image_svg")), "| why:", p.get("image_debug") or "-")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return
    url = args[0]
    from utils import myschool as ms
    describe(ms.fetch(url, ms._session()), "plain download")
    if "--browser" in sys.argv:
        from app import create_app
        with create_app().app_context():
            from utils import myschool_figures as mf
            html, png = mf._browser(url, want_png=True)
            describe(html, "after JavaScript (browser)")
            print("browser screenshot of a figure:", f"{len(png)} bytes" if png else "none")


if __name__ == "__main__":
    main()
