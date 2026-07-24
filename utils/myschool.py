"""Shared myschool.ng past-questions scraper — used by both the standalone
``waec_scraper.py`` CLI and the in-app one-click harvest.

Everything here is pure/importable (no Flask or DB dependency): it fetches a
question's detail page, parses the stem / four options / correct answer, detects
figure-dependent and table questions, captures a stem image URL when one is
actually present, and keyword-maps each question to the app's own
section / topic / sub-topic taxonomy (the seeded syllabus + a topic→blueprint
section map).

The taxonomy is imported from ``utils.syllabus_data`` so there is a single
source of truth; the section map and keyword boosts live here.
"""
from __future__ import annotations

import html as _html
import re
import time

try:
    from utils.syllabus_data import FULL_SYLLABUS
except Exception:                       # pragma: no cover - detached use
    FULL_SYLLABUS = {}


BASE = "https://myschool.ng/classroom"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# --- subject name -> myschool slug ----------------------------------------
SUBJECT_SLUGS = {
    "mathematics": "mathematics", "maths": "mathematics", "math": "mathematics",
    "english": "english-language", "english language": "english-language",
    "use of english": "english-language",
    "physics": "physics", "chemistry": "chemistry", "biology": "biology",
    "economics": "economics", "commerce": "commerce", "government": "government",
    # myschool spells these with the subject abbreviation in the slug.
    "accounting": "accounts-principles-of-accounts",
    "principles of accounts": "accounts-principles-of-accounts",
    "financial accounting": "accounts-principles-of-accounts",
    "literature": "literature-in-english", "literature in english": "literature-in-english",
    "geography": "geography", "agricultural science": "agricultural-science",
    "agriculture": "agricultural-science", "agric": "agricultural-science",
    "christian religious studies": "christian-religious-knowledge-crk",
    "christian religious knowledge": "christian-religious-knowledge-crk",
    "crs": "christian-religious-knowledge-crk", "crk": "christian-religious-knowledge-crk",
    "islamic studies": "islamic-religious-knowledge-irk",
    "islamic religious studies": "islamic-religious-knowledge-irk",
    "islamic religious knowledge": "islamic-religious-knowledge-irk",
    "irs": "islamic-religious-knowledge-irk", "irk": "islamic-religious-knowledge-irk",
    "civic education": "civic-education", "civics": "civic-education",
    "further mathematics": "further-mathematics",
    "computer studies": "computer-studies", "computer science": "computer-studies",
    "data processing": "data-processing", "history": "history",
    "fine art": "fine-arts", "fine arts": "fine-arts",
    "home economics": "home-economics", "physical education": "physical-education",
    "marketing": "marketing", "insurance": "insurance",
    "book keeping": "book-keeping", "office practice": "office-practice",
}


def subject_slug(name):
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    if key in SUBJECT_SLUGS:
        return SUBJECT_SLUGS[key]
    return re.sub(r"[^a-z0-9]+", "-", key).strip("-")


# Subjects myschool actually carries under JAMB/UTME (normalised names), verified
# against the live site. Used to flag subjects that would download nothing under
# JAMB — Civic Education, Further Maths, Data Processing and the trade subjects
# (Insurance, Book-keeping, Office Practice, Marketing, …) are WAEC-only on
# myschool, or not there at all.
JAMB_SUBJECTS = {
    "english language", "mathematics", "physics", "chemistry", "biology",
    "agricultural science", "economics", "commerce", "government", "geography",
    "literature in english", "history",
    "accounting", "principles of accounts",
    "christian religious studies", "christian religious knowledge",
    "islamic religious studies", "islamic studies", "islamic religious knowledge",
    "computer studies", "home economics", "physical education", "fine art",
    "music", "french", "hausa", "igbo", "yoruba",
}


def on_jamb(subject_name):
    """Whether myschool offers this subject under JAMB (best-effort, by name)."""
    return norm_subject(subject_name) in JAMB_SUBJECTS


# JAMB's recommended English novel rotates by year. myschool DOES label the text
# on each year's listing page (a badge — see ``scrape_novel_title``), which is the
# authoritative source; this table is only a fallback for years whose badge is
# absent (e.g. older papers). (title — author, matching the blueprint editor's
# suggestions.) Edit/extend as JAMB announces new texts.
JAMB_ENGLISH_NOVELS = [
    ((2016, 2020), "The Last Days at Forcados High School — A.H. Mohammed"),
    ((2021, 2024), "The Life Changer — Khadija Abubakar Jalli"),
    ((2025, 2025), "The Lekki Headmaster"),
]


def novel_for_year(year):
    """The JAMB-recommended English novel for a UTME year, or None if unknown."""
    try:
        y = int(str(year)[:4])
    except (TypeError, ValueError):
        return None
    for (lo, hi), title in JAMB_ENGLISH_NOVELS:
        if lo <= y <= hi:
            return title
    return None


# myschool renders a per-question instruction block (a ``div.prevent-copy``) above
# the stem: for a Novel question it reads "…based on <author>'s novel, <title>";
# for Comprehension/Cloze it holds the shared reading passage. Both let us tag and
# group English questions faithfully, server-side.
_NOVEL_NOTE = re.compile(r"based on .*\bnovel\b|from the novel|recommended (?:novel|text)", re.I)
_CLOZE_GAP = re.compile(r"_{3,}|\(\s*\d{1,2}\s*\)")


def _novel_title_from_note(text):
    """Pull the book title out of a novel instruction note, preferring the quoted
    title (``…novel, "The Life Changer"``)."""
    m = re.search(r'[\"“”]([^\"“”]{2,140}?)[\"“”]', text or "")
    if m:
        return clean(m.group(1))
    m = re.search(r"novel[,;:]?\s+(.{2,80})$", text or "", re.I)
    return clean(m.group(1)) if m else None


def passage_kind(passage_text, stem=""):
    """Classify a reading stimulus as a JAMB ``cloze`` passage (gaps to fill) or
    ordinary ``comprehension``. A cloze question's stem is itself a sentence with
    a blank, so a blank in the stem is the surest per-question signal; a passage
    body dense with numbered gaps counts too."""
    if re.search(r"_{3,}|\.\.\.\.+", stem or ""):
        return "cloze"
    gaps = len(_CLOZE_GAP.findall(passage_text or ""))
    return "cloze" if gaps >= 3 else "comprehension"


_PASSAGE_LEADIN = re.compile(
    r"^\s*(?:use the (?:passage|following)[^:]*?below\b[:.]?\s*"
    r"|read the (?:passage|following)[^:]*?follows?\b[:.]?\s*)", re.I)


def _clean_passage(text):
    """Drop the repeated instructional lead-in ("Use the passage… Read the passage
    carefully and answer the questions that follow:") so the stored passage is the
    text itself and dedupes cleanly."""
    t = clean(text or "")
    for _ in range(3):
        new = _PASSAGE_LEADIN.sub("", t)
        if new == t:
            break
        t = new.strip()
    return t


def _novel_from_listing_html(html):
    """The JAMB recommended-novel name off a myschool listing page: it renders the
    year's set text in a badge — ``<div class="… bg-primary_accent …"><strong>Title
    </strong></div>``. Returns the title, or None when the badge isn't present
    (e.g. older years, or a non-English subject)."""
    if not html:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for div in soup.select("div.bg-primary_accent"):
        strong = div.find("strong")
        if strong:
            txt = clean(strong.get_text(" ", strip=True))
            if txt:
                return txt
    return None


def scrape_novel_title(subject, exam, year, session=None):
    """Read the recommended-novel badge off the English listing page for a year,
    so novel-section questions can be tagged with the actual set text even when
    the hardcoded ``JAMB_ENGLISH_NOVELS`` map is stale (e.g. 2025 → "The Lekki
    Headmaster"). Only meaningful for English; returns None for other subjects or
    when the badge is absent."""
    if norm_subject(subject) != "english language":
        return None
    sess = session or _session()
    slug = subject_slug(subject)
    html = fetch(f"{BASE}/{slug}?exam_type={exam}&exam_year={year}&page=1", sess)
    return _novel_from_listing_html(html)


def norm_subject(name):
    """Casefold + de-alias to the taxonomy keys (mirror of
    utils.jamb_blueprint.norm_subject, duplicated so this stays importable
    without the app)."""
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    aliases = {
        "maths": "mathematics", "math": "mathematics",
        "english": "english language", "useofenglish": "english language",
        "englishlanguage": "english language",
        "bio": "biology", "chem": "chemistry", "phy": "physics", "physic": "physics",
        "econs": "economics", "econ": "economics", "govt": "government", "gov": "government",
        "lit": "literature in english", "literature": "literature in english",
        "literatureinenglish": "literature in english",
        "crs": "christian religious studies", "crk": "christian religious studies",
        "geo": "geography", "accounts": "accounting", "principlesofaccounts": "accounting",
        "financialaccounting": "accounting", "agric": "agricultural science",
        "agriculture": "agricultural science", "civic": "civic education",
        "civics": "civic education", "furthermaths": "further mathematics",
    }
    if key in aliases:
        return aliases[key]
    return " ".join(re.findall(r"[a-z]+|[0-9]+", (name or "").lower())).strip()


# topic -> blueprint section key, per subject.
TOPIC_SECTION = {
    "mathematics": {
        "Number and Numeration": "number", "Algebra": "algebra",
        "Geometry and Trigonometry": "geometry", "Calculus": "calculus",
        "Statistics": "statistics",
    },
    "physics": {
        "Measurement and Units": "measurement", "Scalars and Vectors": "mechanics",
        "Motion": "mechanics", "Work, Energy and Power": "mechanics",
        "Momentum & Gravitation": "mechanics", "Fields, Fluids & Elasticity": "mechanics",
        "Heat and Thermal Physics": "thermal", "Waves": "waves_optics",
        "Optics (Light)": "waves_optics", "Electricity and Magnetism": "electromagnetism",
        "Modern Physics & Electronics": "modern",
    },
    "chemistry": {
        "Separation of Mixtures & Purification": "separation",
        "Chemical Combination & Stoichiometry": "stoichiometry",
        "States of Matter & Gas Laws": "states_gas",
        "Atomic Structure & Bonding": "atomic_bonding",
        "Air, Water & Solubility": "states_gas",
        "Acids, Bases and Salts": "acids_bases_salts",
        "Oxidation-Reduction & Electrochemistry": "redox_electro",
        "Energetics, Rates & Equilibrium": "energetics_rates",
        "Non-metals and Their Compounds": "periodic_metals",
        "Metals and Their Compounds": "periodic_metals",
        "Organic Chemistry": "organic", "Chemistry and Industry": "periodic_metals",
    },
    "biology": {
        "Living Organisms & Cells": "cell", "Nutrition": "nutrition",
        "Transport": "transport_respiration", "Respiration": "transport_respiration",
        "Excretion": "excretion_regulation", "Support and Movement": "support_movement",
        "Coordination and Regulation": "excretion_regulation",
        "Reproduction, Growth & Development": "reproduction", "Ecology": "ecology",
        "Heredity and Evolution": "genetics_evolution",
        "Micro-organisms & Diseases": "ecology",
    },
    "english language": {
        "Comprehension": "comprehension", "Summary": "summary",
        "Lexis and Structure": "lexis_structure",
        "Oral English (Test of Orals)": "oral", "Registers": "registers",
        "Recommended Novel": "novel",
    },
    "economics": {
        "Basic Economic Concepts": "micro", "Production": "micro",
        "Demand, Supply & Price": "micro", "Market Structures": "micro",
        "Money and Finance": "macro", "Public Finance": "development",
        "National Income": "macro",
        "Development & International Economics": "international",
    },
    "government": {
        "Basic Concepts": "concepts", "Political Ideas & Systems": "concepts",
        "Structures of Government": "constitution", "Political Processes": "constitution",
        "Nigerian Government & Politics": "nigeria",
        "International Relations": "international",
    },
    "commerce": {
        "Introduction to Commerce": "trade", "Trade": "trade", "Aids to Trade": "trade",
        "Business Organisations": "business",
        "Business Finance & Institutions": "finance",
        "Business Environment": "business",
    },
    "accounting": {
        "Nature & Principles of Accounting": "principles",
        "Double Entry & Books of Account": "principles",
        "Final Accounts": "final", "Adjustments & Corrections": "final",
        "Specialised Accounts": "specialised", "Interpretation & Public Sector": "specialised",
    },
    "geography": {
        "Practical Geography": "practical", "Physical Geography": "physical",
        "Human Geography": "human", "Regional Geography of Nigeria": "regional",
    },
}

ENGLISH_SUBTOPIC_SECTION = {
    "Synonyms": "synonyms", "Antonyms": "antonyms",
    "Sentence interpretation / nearest in meaning": "sentence_interpretation",
}

KEYWORD_BOOSTS = {
    "mathematics": {
        "Number bases: conversion & operations in different bases":
            ["base", "binary", "octal", "denary", "convert to base", "in base"],
        "Indices, logarithms & standard form": ["log", "antilog", "index", "exponent", "standard form"],
        "Sets: notation, operations, Venn diagrams & applications":
            ["set", "venn", "union", "intersection", "subset", "complement", "universal set"],
        "Surds (radicals)": ["surd", "rationalize", "rationalise", "sqrt", "root of"],
        "Binary operations": ["binary operation", "defined by", "otimes", "oplus", "ast"],
        "Fractions, decimals, approximations & percentages":
            ["percentage", "percent", "fraction", "decimal", "ratio of"],
        "Quadratic equations & expressions": ["quadratic", "roots", "x^2", "completing the square"],
        "Progressions: arithmetic (AP) & geometric (GP)":
            ["arithmetic progression", "geometric progression", "common difference", "common ratio", "nth term"],
        "Matrices & determinants": ["matrix", "matrices", "determinant"],
        "Circle theorems": ["circle", "chord", "tangent", "cyclic", "arc", "sector"],
        "Mensuration: perimeter, area & volume": ["area", "volume", "perimeter", "surface area", "cylinder", "cone", "sphere"],
        "Coordinate geometry of straight lines": ["gradient", "midpoint", "coordinate", "straight line", "slope"],
        "Trigonometric ratios & identities": ["sin", "cos", "tan", "trig", "angle"],
        "Bearings": ["bearing", "due north", "due east"],
        "Sine & cosine rules": ["sine rule", "cosine rule"],
        "Measures of central tendency (mean, median, mode)": ["mean", "median", "mode", "average"],
        "Measures of dispersion (range, variance, standard deviation)":
            ["variance", "standard deviation", "range", "mean deviation"],
        "Permutations & combinations": ["permutation", "combination", "arrange", "nPr", "nCr"],
        "Probability: single & combined events": ["probability", "dice", "coin", "at random", "chance"],
        "Differentiation of algebraic & trigonometric functions": ["differentiate", "derivative", "dy/dx"],
        "Integration of algebraic & trigonometric functions": ["integrate", "integral"],
    },
    "physics": {
        "Newton's laws of motion": ["newton", "force", "acceleration", "f = ma"],
        "Projectile motion": ["projectile", "range", "trajectory"],
        "Simple harmonic motion": ["harmonic", "oscillation", "amplitude", "period", "pendulum"],
        "Gas laws & the ideal gas equation": ["boyle", "charles", "pressure", "gas law", "volume of gas"],
        "Current, potential difference & Ohm's law": ["ohm", "resistance", "current", "voltage", "e.m.f", "resistor"],
        "Radioactivity": ["radioactive", "half-life", "decay", "alpha", "beta", "gamma"],
        "Reflection at plane & curved mirrors": ["mirror", "reflection", "image"],
        "Refraction through media & prisms": ["refraction", "refractive index", "prism"],
        "Lenses & optical instruments": ["lens", "focal length", "magnification"],
        "Latent heat & change of state": ["latent heat", "melting", "boiling", "fusion", "vaporisation"],
        "Quantity of heat: heat capacity & specific heat": ["specific heat", "heat capacity", "calorimeter"],
    },
    "chemistry": {
        "Mole concept & Avogadro's number": ["mole", "avogadro", "molar mass", "moles"],
        "Electrolysis & Faraday's laws": ["electrolysis", "faraday", "cathode", "anode", "electrode"],
        "pH, indicators & neutralisation": ["ph", "indicator", "litmus", "neutralise"],
        "Titration & acid-base calculations": ["titration", "titre", "burette", "pipette"],
        "The periodic table & periodicity": ["periodic table", "group", "period", "periodicity"],
        "Chemical bonding: ionic, covalent & metallic": ["ionic", "covalent", "metallic bond", "bonding"],
        "Alkanes, alkenes & alkynes": ["alkane", "alkene", "alkyne", "hydrocarbon", "saturated", "unsaturated"],
        "Alkanols (alcohols) & alkanoic acids": ["alcohol", "alkanol", "ethanol", "carboxylic", "alkanoic"],
        "Rates of chemical reaction & factors": ["rate of reaction", "catalyst", "collision"],
    },
    "biology": {
        "Autotrophic nutrition & photosynthesis": ["photosynthesis", "chlorophyll", "chloroplast"],
        "Mendelian genetics & inheritance": ["gene", "allele", "genotype", "phenotype", "dominant", "recessive", "mendel"],
        "The kidney & osmoregulation": ["kidney", "nephron", "osmoregulation", "urine"],
        "Circulatory system & blood": ["blood", "heart", "artery", "vein", "circulation"],
        "Energy flow & food chains/webs": ["food chain", "food web", "trophic", "producer", "consumer"],
        "Classification of living organisms": ["classification", "kingdom", "phylum", "taxonomy", "species"],
    },
    "commerce": {
        "Banking & finance": ["bank", "cheque", "overdraft", "central bank", "loan"],
        "Insurance": ["insurance", "premium", "policy", "indemnity", "underwriter"],
        "Advertising & sales promotion": ["advert", "advertising", "sales promotion", "publicity"],
        "Warehousing": ["warehouse", "warehousing", "storage"],
        "Transportation": ["transport", "haulage", "carrier", "freight"],
        "Communication": ["communication", "postal", "telecommunication"],
        "Stock exchange": ["stock exchange", "shares", "stockbroker", "securities"],
    },
    "economics": {
        "Elasticity of demand & supply": ["elasticity", "elastic", "inelastic"],
        "Theory of demand & supply": ["demand", "supply", "demand curve"],
        "Money: functions & value": ["money", "medium of exchange", "legal tender"],
        "Inflation & deflation": ["inflation", "deflation"],
        "Government revenue & taxation": ["tax", "taxation", "revenue", "tariff"],
    },
}


_STOP = set("""a an the of and or to in for with without by on at from into as is are be was
were being been this that these those it its their his her our your my not no nor etc within
different single combined simple types type kind nature basic concept concepts meaning scope
application applications their they them use uses using various value values general which
what when where who whom whose why how find given following above below shown show table figure
diagram evaluate simplify solve calculate correct nearest whole number numbers answer result
expression equation equations term terms set sets real means mean nil none each every all both
one two three four five six seven eight nine ten first second third last next figure fig
statement statements true false option options if then than more most less least many much
some any other others another such same only also just even still very more question if
""".split())


def _strip_latex(text):
    return re.sub(r"[{}\\^_$]", " ", text or "")


def _stem(word):
    for suf in ("ies", "es", "s"):
        if len(word) > 4 and word.endswith(suf):
            return word[: -len(suf)] + ("y" if suf == "ies" else "")
    return word


def _tokens(text):
    out = []
    for w in re.findall(r"[a-z]+", _strip_latex(text).lower()):
        if len(w) > 2 and w not in _STOP:
            out.append(_stem(w))
    return out


def _build_index(subject):
    key = norm_subject(subject)
    syl = FULL_SYLLABUS.get(key)
    if not syl:
        return []
    tsec = TOPIC_SECTION.get(key, {})
    boosts = KEYWORD_BOOSTS.get(key, {})
    index = []
    for topic, subs in syl:
        for sub in subs:
            section = tsec.get(topic)
            if key == "english language":
                section = ENGLISH_SUBTOPIC_SECTION.get(sub, section)
            kws = set(_tokens(sub)) | set(_tokens(topic))
            for phrase in boosts.get(sub, []):
                kws.add(phrase.lower())
                kws.update(_tokens(phrase))
            index.append((section, topic, sub, kws))
    return index


def classify(subject, text, year=None, novel_title=None):
    """Keyword-match a question to (section, topic, subtopic).

    For English, a question confidently classified into the Novel section has its
    ``topic`` set to the JAMB-recommended novel, so it lines up with a mock that
    names that novel — the app serves Novel questions whose topic matches the
    mock's ``novel_title``. The novel is taken from ``novel_title`` when supplied
    (the name scraped off the listing page, authoritative), else from the
    hardcoded ``year`` map."""
    index = _build_index(subject)
    if not index:
        return (None, None, None)
    low = (text or "").lower()
    toks = set(_tokens(text))
    best, best_score = None, 0
    for section, topic, sub, kws in index:
        score = 0
        for kw in kws:
            if " " in kw:
                if kw in low:
                    score += 3
            elif kw in toks:
                score += 1
        if score > best_score:
            best_score, best = score, (section, topic, sub)
    if best and best_score > 0:
        section, topic, sub = best
        # tag the actual novel (only on a genuine novel match): prefer the name
        # scraped off the listing page, fall back to the year map.
        if section == "novel" and topic == "Recommended Novel":
            nv = (novel_title or "").strip() or novel_for_year(year)
            if nv:
                topic = nv
        return (section, topic, sub)
    sections = []
    for section, _t, _s, _k in index:
        if section and section not in sections:
            sections.append(section)
    if not sections:
        return (None, None, None)
    return (sections[sum(ord(c) for c in (text or "")) % len(sections)], None, None)


# ===========================================================================
# HTTP + parsing
# ===========================================================================
def _session():
    import requests
    return requests.Session()


def fetch(url, session, retries=3):
    import requests
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return None


def clean(text):
    t = _html.unescape(text or "")
    t = t.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", t).strip()


# figure-reference words: a stem that leans on a picture we couldn't capture.
_FIGURE_WORDS = re.compile(
    r"\b(diagram|figure|fig\.?|graph|the (?:sketch|drawing|circuit|structure)|"
    r"shown (?:above|below)|in the (?:figure|diagram|graph)|from the graph|"
    r"the (?:map|chart) (?:above|below))\b", re.I)


_IMG_REJECT = ("placeholder", "emojione", "emoji", "/members/", "/comments/",
               "avatar", "logo", "/icons/", "sprite", "gravatar", "flag")


def _real_image_src(src):
    """True for a genuine question figure, not an avatar / placeholder / emoji /
    comment attachment / logo."""
    s = (src or "").strip().lower()
    if not s or s.startswith("data:"):
        return False
    if any(bad in s for bad in _IMG_REJECT):
        return False
    # a myschool question figure lives under /storage/… (but not the rejected
    # sub-folders above); otherwise accept any real image URL.
    base = s.split("?", 1)[0].split(" ", 1)[0]
    return base.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))


def _img_candidates(im):
    """Every URL an <img> exposes — eager/lazy attributes plus each srcset entry —
    so a real hosted figure can be preferred over a base64 placeholder that a
    NuxtImg often carries in ``src`` while the real image sits in ``srcset``."""
    out = []
    for attr in ("src", "data-src", "data-original", "data-lazy", "data-echo",
                 "data-lazy-src", "data-image"):
        v = (im.get(attr) or "").strip()
        if v:
            out.append(v)
    for key in ("srcset", "data-srcset"):
        ss = (im.get(key) or "").strip()
        if ss:
            for part in ss.split(","):
                u = part.strip().split(" ")[0]
                if u:
                    out.append(u)
    return out


def _img_src(im):
    """The best single URL from an <img> (compat shim over _img_candidates)."""
    cands = _img_candidates(im)
    return cands[0] if cands else ""


def _real_data_uri(src):
    """True for an inline base64 raster that is an actual figure — myschool embeds
    some diagrams straight into the HTML as ``data:image/…;base64,…``. Tiny blur /
    LQIP placeholders and 1×1 spacers are excluded by payload size."""
    s = (src or "").strip()
    if not s.lower().startswith("data:image/"):
        return False
    payload = s.split(",", 1)[1] if "," in s else ""
    return len(payload) > 3000                # ~2KB+ decoded → a genuine figure


def _serialize_table(table):
    """Render a myschool <table> as readable text: rows joined by ' | ',
    rows separated by ' ; ' — keeps the data legible in a plain-text stem."""
    rows = []
    for tr in table.select("tr"):
        cells = [clean(td.get_text(" ", strip=True)) for td in tr.select("th,td")]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return " ; ".join(rows)


def parse_detail(html):
    """Parse a question detail page into a dict:

    ``{stem, options[4], correct, image_url, has_table, needs_review, flags}``
    or ``None`` if the essentials (stem / 4 options / correct) can't be read.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    options = {}
    for sp in soup.select("span.uppercase"):
        letter = sp.get_text(strip=True).lower()
        if letter in ("a", "b", "c", "d") and letter not in options:
            p = sp.find_next("p")
            if p:
                options[letter] = clean(p.get_text(" ", strip=True))
    if len(options) < 2:
        return None

    # locate the stem <h1> and its container (so we can inspect it for a figure
    # image or a data table).
    stem, container = "", None
    first_opt = next((sp for sp in soup.select("span.uppercase")
                      if sp.get_text(strip=True).lower() == "a"), None)
    h1 = None
    if first_opt:
        block = first_opt
        for _ in range(6):
            block = block.find_parent() if block else None
            if not block:
                break
            cand = block.find_previous("h1")
            if cand and cand.get_text(strip=True):
                h1 = cand
                break
    if h1 is None:
        h1 = soup.find("h1")
    if h1 is not None:
        stem = clean(h1.get_text(" ", strip=True))
        container = h1.parent

    # a data table inside the stem → serialise it, remove it from the stem (so its
    # cells don't leak in as flattened run-on text), and append a structured
    # ``[table: …]`` marker the UI renders as a real table.
    has_table = False
    if container is not None:
        table = container.find("table")
        if table is not None:
            has_table = True
            table_text = _serialize_table(table)
            table.extract()                                  # drop the table node…
            if h1 is not None:                               # …then re-read a clean stem
                stem = clean(h1.get_text(" ", strip=True))
            if table_text:
                stem = (stem + " [table: " + table_text + "]").strip()
    if not stem:
        return None

    # a genuine figure image in the stem, if any. myschool server-renders these as
    # a NuxtImg (``<img data-nuxt-img srcset/src>``) pointing at /storage/classroom/…,
    # or embeds the diagram inline as a base64 data URI. Prefer a real hosted URL;
    # fall back to a substantial inline image (re-hosted at save time).
    image_url, data_uri = None, None
    if container is not None:
        for im in container.find_all("img"):
            for cand in _img_candidates(im):
                if cand.startswith("data:"):
                    if data_uri is None and _real_data_uri(cand):
                        data_uri = cand
                elif _real_image_src(cand):
                    image_url = cand
                    break
            if image_url:
                break
    if image_url and image_url.startswith("/"):        # absolutise site-relative
        image_url = "https://myschool.ng" + image_url
    if not image_url:                                  # inline base64 figure
        image_url = data_uri

    # correct answer badge.
    correct = ""
    node = soup.find(string=re.compile(r"Correct Option", re.I))
    if node:
        el = node.parent
        for _ in range(5):
            if el is None:
                break
            sp = el.select_one("span.uppercase") if hasattr(el, "select_one") else None
            if sp and sp.get_text(strip=True).lower() in ("a", "b", "c", "d"):
                correct = sp.get_text(strip=True).upper()
                break
            el = el.parent
    if correct not in ("A", "B", "C", "D"):
        return None

    ordered = [options.get(k, "") for k in ("a", "b", "c", "d")]
    if any(not o for o in ordered):
        return None

    # instruction / reading passage / recommended-novel note — the shared stimulus
    # myschool renders in a ``prevent-copy`` block (never the stem or an option row).
    instruction, passage_text, novel_title, is_novel = "", "", None, False
    for d in soup.select("div.prevent-copy"):
        if d.select_one("span.uppercase"):       # an option row → not an instruction
            continue
        t = clean(d.get_text(" ", strip=True))
        if not t or t == stem:
            continue
        if _NOVEL_NOTE.search(t):
            is_novel = True
            instruction = instruction or t
            novel_title = novel_title or _novel_title_from_note(t)
        elif len(t) > len(passage_text):
            passage_text = t                     # keep the longest = the passage
    if len(passage_text) < 120:                  # too short to be a real passage
        passage_text = ""
    else:
        passage_text = _clean_passage(passage_text)
    instruction = instruction or passage_text

    flags = []
    if has_table:
        flags.append("table")
    # figure-dependent but we captured no image → needs a human to add the figure.
    figure_dependent = bool(_FIGURE_WORDS.search(stem)) and not image_url
    if figure_dependent:
        flags.append("figure")
    if image_url:
        flags.append("image")
    if is_novel:
        flags.append("novel")
    if passage_text:
        flags.append("passage")

    return {
        "stem": stem, "options": ordered, "correct": correct,
        "image_url": image_url, "has_table": has_table,
        "figure_dependent": figure_dependent,
        "needs_review": figure_dependent, "flags": flags,
        "instruction": instruction, "passage_text": passage_text,
        "is_novel": is_novel, "novel_title": novel_title,
    }


def list_question_ids(slug, exam, year, session, max_pages=60, delay=0.6):
    """Every question detail-page id for one subject/exam/year (paginated)."""
    ids, seen = [], set()
    for page in range(1, max_pages + 1):
        html = fetch(f"{BASE}/{slug}?exam_type={exam}&exam_year={year}&page={page}", session)
        if not html:
            break
        found = re.findall(rf"/classroom/{re.escape(slug)}/(\d+)\?exam_type={exam}", html)
        new = [i for i in found if i not in seen]
        if not new:
            break
        for i in new:
            seen.add(i)
            ids.append(i)
        time.sleep(delay)
    return ids


def question_url(slug, exam, year, qid):
    return f"{BASE}/{slug}/{qid}?exam_type={exam}&exam_year={year}"


def scrape_year(subject, exam, year, session=None, max_pages=60, delay=0.6,
                detail_fetch=None):
    """Yield parsed question dicts for one subject/exam/year, each augmented with
    ``subject``, ``year`` and the classified ``section/topic/subtopic``. Skips
    unparseable pages. The caller de-duplicates and decides what to store.

    ``detail_fetch(url) -> html`` overrides how detail pages are fetched (e.g. a
    Playwright renderer that also exposes JS-injected figure images)."""
    sess = session or _session()
    slug = subject_slug(subject)
    novel_title = scrape_novel_title(subject, exam, year, sess)   # English only
    for qid in list_question_ids(slug, exam, year, sess, max_pages, delay):
        html = (detail_fetch(question_url(slug, exam, year, qid)) if detail_fetch
                else fetch(question_url(slug, exam, year, qid), sess))
        if not html:
            continue
        parsed = parse_detail(html)
        time.sleep(delay)
        if not parsed:
            continue
        # trust myschool's own instruction block (novel note / reading passage)
        # over keyword classification, exactly as the in-app harvest does.
        if parsed.get("is_novel"):
            section, topic, subtopic = "novel", (
                parsed.get("novel_title") or novel_title or novel_for_year(year)
                or "Recommended Novel"), None
        elif parsed.get("passage_text"):
            section = passage_kind(parsed["passage_text"], parsed["stem"])
            topic, subtopic = None, None
        else:
            section, topic, subtopic = classify(
                subject, parsed["stem"] + " " + " ".join(parsed["options"]),
                year=year, novel_title=novel_title)
        parsed.update(subject=subject, year=str(year), qid=qid,
                      section=section, topic=topic, subtopic=subtopic)
        yield parsed
