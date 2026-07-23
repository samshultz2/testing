"""
Past-questions scraper for myschool.ng  →  EduSyncra "Bulk import questions".

For most people the easiest route is the in-app button:
    Mock JAMB → Question bank → "Download questions from myschool.ng"
which fetches and saves straight to the bank. This standalone script is for
when you'd rather produce a text file and paste it yourself.

Works for ANY subject, a single year or a year range, and for JAMB / WAEC /
NECO / Post-UTME. It shares its scraping + tagging logic with the app
(``utils/myschool.py``), so run it from the project root.

    pip install requests beautifulsoup4

    # one subject, one year
    python waec_scraper.py --subject mathematics --exam jamb --year 2019
    # a range of years
    python waec_scraper.py --subject commerce --exam jamb --from 2010 --to 2022

It writes two files:
  * <subject>_<exam>.txt              — paste-ready rows for the bank
  * <subject>_<exam>_needs_review.txt — questions that rely on a diagram we
                                        couldn't fetch (add these by hand)

Each row is tab-separated in the importer's exact format, with year and an
optional figure-URL column:
    question  A  B  C  D  correct  section  topic  subtopic  year  [image URL]

Then open the .txt, copy everything, and paste it into the subject's
"Bulk import questions (paste)" box in the Mock JAMB question bank.
"""
from __future__ import annotations

import argparse
import re
import sys

try:
    from utils import myschool as ms
except Exception as exc:                       # pragma: no cover
    sys.exit("Run this from the project root (needs utils/myschool.py): " + str(exc))


def _row(q):
    """A tab-separated importer row from a parsed question dict."""
    fields = [q["stem"], q["options"][0], q["options"][1], q["options"][2],
              q["options"][3], q["correct"], q.get("section") or "",
              q.get("topic") or "", q.get("subtopic") or "", str(q.get("year") or ""),
              q.get("image_url") or ""]
    return "\t".join(ms.clean(str(c)) for c in fields)


def scrape(subject, exam, years, out, review_out, max_pages, delay):
    session = ms._session()
    seen = set()                                # de-dup by normalised stem
    rows, review, per_year = [], [], {}

    print(f"Subject: {subject}  (slug: {ms.subject_slug(subject)})   Exam: {exam.upper()}")
    print("Years: " + str(years[0]) + (f"–{years[-1]}" if len(years) > 1 else ""))
    print("-" * 60)

    for year in years:
        kept = dup = flagged = 0
        for q in ms.scrape_year(subject, exam, year, session=session,
                                max_pages=max_pages, delay=delay):
            norm = re.sub(r"\s+", " ", q["stem"].lower()).strip()
            if norm in seen:
                dup += 1
                continue
            seen.add(norm)
            if q["figure_dependent"]:           # needs a diagram → sidecar
                review.append(_row(q))
                flagged += 1
                continue
            rows.append(_row(q))
            kept += 1
        per_year[year] = kept
        print(f"{year}: {kept} kept, {dup} duplicate(s), {flagged} need a diagram")

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + ("\n" if rows else ""))
    if review:
        with open(review_out, "w", encoding="utf-8") as f:
            f.write("\n".join(review) + "\n")

    print("-" * 60)
    print(f"Saved {len(rows)} question(s) to {out}")
    if review:
        print(f"Set aside {len(review)} figure-dependent question(s) in {review_out} "
              f"— add these by hand (they need the diagram).")
    print("\nOpen the file, copy everything, and paste it into the subject's")
    print("'Bulk import questions (paste)' box in the Mock JAMB question bank.")


def main():
    ap = argparse.ArgumentParser(
        description="Scrape myschool.ng past questions into EduSyncra bulk-import rows.")
    ap.add_argument("--subject", required=True,
                    help="Subject name, e.g. mathematics, commerce, 'english language'.")
    ap.add_argument("--exam", default="jamb", help="jamb (default), waec, neco, post-utme.")
    ap.add_argument("--year", type=int, help="A single year, e.g. 2019.")
    ap.add_argument("--from", dest="from_year", type=int, help="Start year of a range.")
    ap.add_argument("--to", dest="to_year", type=int, help="End year of a range.")
    ap.add_argument("--out", help="Output file (default: <subject>_<exam>.txt).")
    ap.add_argument("--max-pages", type=int, default=60,
                    help="Safety cap on listing pages per year (default 60).")
    ap.add_argument("--delay", type=float, default=0.6,
                    help="Seconds between requests — be polite (default 0.6).")
    args = ap.parse_args()

    if args.year:
        years = [args.year]
    elif args.from_year and args.to_year:
        lo, hi = sorted((args.from_year, args.to_year))
        years = list(range(lo, hi + 1))
    else:
        ap.error("Give either --year YYYY or --from YYYY --to YYYY.")

    exam = args.exam.strip().lower()
    stem = f"{ms.subject_slug(args.subject)}_{exam}"
    out = args.out or f"{stem}.txt"
    review_out = f"{stem}_needs_review.txt"
    scrape(args.subject, exam, years, out, review_out, args.max_pages, args.delay)


if __name__ == "__main__":
    main()
