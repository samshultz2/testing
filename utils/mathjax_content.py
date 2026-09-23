"""Detect whether question/option/passage text actually needs MathJax, so the
CBT and Mock JAMB sitting pages can skip loading it (a 1.17MB script, by far
the heaviest single asset on either page) for the — typical — exam that has
no LaTeX in it at all.

Two delimiter sets, matching the two loaders exactly (they're intentionally
different — see static/js/mathjax-setup.js's own comment: Mock JAMB drops the
bare $ / $$ delimiters so a currency amount like "$50" in a question stem
isn't mistaken for math; the CBT loader keeps them):
  - static/js/mathjax-setup-cbt.js (CBT):      \\( … \\) / $ … $, \\[ … \\] / $$ … $$
  - static/js/mathjax-setup.js (Mock JAMB):    \\( … \\) only,    \\[ … \\] only
"""
import re

_LATEX_ESCAPES = re.compile(r'\\\(|\\\)|\\\[|\\\]')
_DOLLAR_DELIMS = re.compile(r'\$')


def has_math_markup(*texts, dollar_delims=True):
    """True if any of the given strings contains a MathJax delimiter.

    `dollar_delims` matches whether the page's own MathJax config treats
    $ / $$ as math delimiters (CBT does; Mock JAMB deliberately doesn't).
    """
    for t in texts:
        if not t:
            continue
        if _LATEX_ESCAPES.search(t):
            return True
        if dollar_delims and _DOLLAR_DELIMS.search(t):
            return True
    return False
