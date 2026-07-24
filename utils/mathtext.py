"""Rendering helpers for Mock JAMB question text scraped from myschool.

Two audiences:

* ``question_html`` — for the browser. It HTML-escapes the text (so it is safe to
  mark ``|safe``), turns the ``[table: a | b ; c | d]`` marker the scraper emits
  into a real ``<table>``, and leaves ``\\( … \\)`` LaTeX untouched so MathJax
  typesets it client-side.
* ``latex_to_text`` — for contexts that can't run MathJax (reportlab PDFs, CSV
  exports, plain-text). Best-effort conversion of common LaTeX to readable
  Unicode (``3x^2`` → ``3x²``, ``\\frac{a}{b}`` → ``(a)/(b)``, ``\\sqrt{x}`` → ``√(x)``).
"""
from __future__ import annotations

import re

from markupsafe import Markup, escape

# ---- [table: …] marker -> <table> ----------------------------------------
_TABLE_RE = re.compile(r"\[table:\s*(.*?)\]", re.S)


def _render_table(body):
    rows = [r.strip() for r in body.split(";") if r.strip()]
    if not rows:
        return ""
    # Wrap in a scroll container so a wide table scrolls on its own on small
    # screens instead of stretching the page (see .mjq-tablewrap styling).
    out = ['<div class="mjq-tablewrap"><table class="mjq-table">']
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row.split("|")]
        tag = "th" if i == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}>{escape(c)}</{tag}>" for c in cells) + "</tr>")
    out.append("</table></div>")
    return "".join(out)


def question_html(text):
    """Escape ``text`` for safe display, rendering any ``[table: …]`` marker as a
    real HTML table and leaving ``\\( … \\)`` maths for MathJax. Returns Markup."""
    if not text:
        return Markup("")
    s = str(text)
    out, pos = [], 0
    for m in _TABLE_RE.finditer(s):
        out.append(str(escape(s[pos:m.start()])))
        out.append(_render_table(m.group(1)))
        pos = m.end()
    out.append(str(escape(s[pos:])))
    return Markup("".join(out))


# ---- LaTeX -> readable Unicode (no MathJax) -------------------------------
_SUP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
        "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "=": "⁼",
        "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ", "x": "ˣ", "a": "ᵃ", "b": "ᵇ"}
_SUB = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
        "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋", "=": "₌",
        "(": "₍", ")": "₎", "a": "ₐ", "e": "ₑ", "x": "ₓ", "n": "ₙ"}
_SYMBOLS = [
    (r"\pi", "π"), (r"\theta", "θ"), (r"\alpha", "α"), (r"\beta", "β"),
    (r"\gamma", "γ"), (r"\Delta", "Δ"), (r"\Sigma", "Σ"), (r"\mu", "μ"),
    (r"\times", "×"), (r"\div", "÷"), (r"\pm", "±"), (r"\mp", "∓"),
    (r"\leq", "≤"), (r"\geq", "≥"), (r"\neq", "≠"), (r"\approx", "≈"),
    (r"\infty", "∞"), (r"\cdot", "·"), (r"\rightarrow", "→"), (r"\to", "→"),
    (r"\Rightarrow", "⇒"), (r"\circ", "°"), (r"\degree", "°"),
]


def _to_script(s, table):
    return "".join(table.get(ch, ch) for ch in s) if all(ch in table for ch in s) else None


def latex_to_text(text):
    """Best-effort LaTeX → readable Unicode for non-MathJax surfaces."""
    if not text:
        return text
    t = str(text)
    for d in ("\\(", "\\)", "\\[", "\\]", "\\left", "\\right", "\\,", "\\!", "\\;"):
        t = t.replace(d, "")
    t = re.sub(r"\\d?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", t).replace("\\sqrt", "√")
    for tex, sym in _SYMBOLS:
        t = t.replace(tex, sym)

    def _sup(m):
        body = m.group(1)
        return _to_script(body, _SUP) or ("^(" + body + ")")

    def _sub(m):
        body = m.group(1)
        return _to_script(body, _SUB) or ("_(" + body + ")")

    t = re.sub(r"\^\{([^{}]*)\}", _sup, t)
    t = re.sub(r"\^(\w)", lambda m: _to_script(m.group(1), _SUP) or ("^" + m.group(1)), t)
    t = re.sub(r"_\{([^{}]*)\}", _sub, t)
    t = re.sub(r"_(\w)", lambda m: _to_script(m.group(1), _SUB) or ("_" + m.group(1)), t)
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r"\\([a-zA-Z]+)", r"\1", t)          # drop unknown \commands, keep the name
    return re.sub(r"[ \t]+", " ", t).strip()
