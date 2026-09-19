"""Import a branch's own subject-wise grade/score-band distribution sheet —
via pasted text, an uploaded CSV/XLSX file, or an AI-vision-read photo — into
the shape models.grade_distribution.BranchGradeDistribution stores.

Three steps, same "extract -> review -> save" shape as every other
scan/paste flow in this app:
  1. get a generic ``{'headers': [...], 'rows': [[...]]}`` table (parse_pasted_table
     / utils.broadsheet_import.parse_table / utils.waec_ocr.vision_extract_grade_distribution)
  2. classify_header() + build_distribution_rows() turn that into
     ``[{'subject', 'candidates', 'counts': {band: n}}]`` — always shown to the
     admin to correct before saving, never trusted blind.
"""
import csv
import io
import re

_DASHES = str.maketrans({'–': '-', '—': '-', '−': '-'})


def parse_pasted_table(text):
    """Pasted spreadsheet cells (tab-separated, the norm when copying out of
    Excel/Sheets) or a comma list — same ``{'headers', 'rows'}`` shape as
    utils.broadsheet_import.parse_table."""
    text = (text or '').strip('\n')
    lines = [ln for ln in text.split('\n') if ln.strip()]
    if not lines:
        return {'headers': [], 'rows': []}
    delimiter = '\t' if '\t' in lines[0] else ','
    grid = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    headers = [str(c).strip() for c in grid[0]] if grid else []
    while headers and not headers[-1]:
        headers.pop()
    ncol = len(headers)
    rows = []
    for row in grid[1:]:
        cells = [str(c).strip() for c in row][:ncol]
        cells += [''] * (ncol - len(cells))
        if any(cells):
            rows.append(cells)
    return {'headers': headers, 'rows': rows}


def _norm_key(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())


_CANDIDATES_KEYS = {'sat', 'nosat', 'candidates', 'totalcandidates', 'totalsat', 'nooffered', 'nsat'}
_IGNORE_SUBSTRINGS = ('pass', 'credit', 'rank', 'average', 'avg', 'remark', 'total', 'grandtotal')
_IGNORE_KEYS = {'sn', 's', 'no', 'num', 'position', 'pos'}


def classify_header(header, bands):
    """Best-guess role of one column header: ``('candidates', None)``,
    ``('ignore', None)`` (a derived stat like Passes/Credit% we recompute
    ourselves), or ``('band', [band, ...])`` — more than one band when the
    sheet combines columns (e.g. "D7-E8", "D7/E8")."""
    key = _norm_key(header)
    if not key:
        return ('ignore', None)
    if key in _CANDIDATES_KEYS or key.endswith('sat'):
        return ('candidates', None)
    if key in _IGNORE_KEYS or any(s in key for s in _IGNORE_SUBSTRINGS):
        return ('ignore', None)
    norm_bands = {_norm_key(b): b for b in bands}
    if key in norm_bands:
        return ('band', [norm_bands[key]])
    # a combined column, e.g. "D7-E8", "D7/E8", "D7 & E8"
    cleaned = str(header).translate(_DASHES)
    parts = [p for p in re.split(r'[-/&+,]', cleaned) if _norm_key(p)]
    if len(parts) >= 2:
        matched = [norm_bands.get(_norm_key(p)) for p in parts]
        if all(matched):
            return ('band', matched)
    return ('unknown', None)


# Common abbreviations seen on printed/handwritten branch summary sheets,
# mapped to a fragment of the canonical subject name (mirrors
# utils.broadsheet_import._SUBJECT_ALIASES, adapted for a plain name catalog
# instead of Subject ORM rows).
_SUBJECT_ALIASES = {
    # Mathematics — "General Mathematics" is the WAEC paper's own official
    # name for the subject we catalogue as plain "Mathematics"; treat every
    # common variant as the same subject.
    'pw': 'project', 'fm': 'further mathematics', 'fmaths': 'further mathematics',
    'addmaths': 'further mathematics', 'additionalmathematics': 'further mathematics',
    'additionalmaths': 'further mathematics',
    'chm': 'chemistry', 'chem': 'chemistry', 'phy': 'physics', 'phys': 'physics',
    'bio': 'biology',
    'eng': 'english language', 'english': 'english language', 'useofenglish': 'english language',
    'englishlang': 'english language', 'englishlanguagearts': 'english language',
    'lit': 'literature in english', 'literature': 'literature in english',
    'litinenglish': 'literature in english',
    'crs': 'christian religious studies', 'crk': 'christian religious studies',
    'christianreligiousknowledge': 'christian religious studies',
    'bibleknowledge': 'christian religious studies',
    'irs': 'islamic religious studies', 'irk': 'islamic religious studies',
    'islamicstudies': 'islamic religious studies',
    'civ': 'civic education', 'civic': 'civic education', 'civics': 'civic education',
    'com': 'commerce', 'comm': 'commerce',
    'gov': 'government', 'govt': 'government',
    'eco': 'economics', 'econs': 'economics', 'econ': 'economics',
    'geo': 'geography', 'geog': 'geography',
    'agr': 'agricultural science', 'agric': 'agricultural science', 'agriculture': 'agricultural science',
    'agricscience': 'agricultural science', 'agrics': 'agricultural science',
    'liv': 'livestock farming', 'livest': 'livestock farming', 'livestock': 'livestock farming',
    'dit': 'digital technologies', 'digital': 'digital technologies',
    'mth': 'mathematics', 'math': 'mathematics', 'maths': 'mathematics', 'gmaths': 'mathematics',
    'generalmathematics': 'mathematics', 'generalmaths': 'mathematics', 'genmaths': 'mathematics',
    'genmath': 'mathematics', 'coremaths': 'mathematics', 'coremathematics': 'mathematics',
    'mathematic': 'mathematics',
    'accounts': 'accounting', 'bookkeeping': 'accounting', 'principlesofaccounts': 'accounting',
    'financialaccounting': 'accounting', 'poa': 'accounting',
    'computerscience': 'computer studies', 'informationtechnology': 'computer studies',
    'ict': 'computer studies',
    'hist': 'history',
    'art': 'visual arts', 'fineart': 'visual arts', 'finearts': 'visual arts', 'visualart': 'visual arts',
    'td': 'technical drawing', 'techdrawing': 'technical drawing', 'technicaldrawings': 'technical drawing',
    'foodnutrition': 'food and nutrition',
    'homeecons': 'home economics', 'homeeconomics': 'home economics', 'homeec': 'home economics',
    'phe': 'physical education', 'pe': 'physical education',
    'physicalhealtheducation': 'physical education',
    'yorubalanguage': 'yoruba', 'igbolanguage': 'igbo', 'hausalanguage': 'hausa',
    'frenchlanguage': 'french',
}


def match_subject_name(raw, catalog):
    """Best-guess canonical subject name for a raw cell against ``catalog``
    (a list of plain subject-name strings) — or the cleaned original text
    when nothing matches, so an unrecognised subject still imports (just
    won't merge with a same-named DB subject on the breakdown page)."""
    raw = (raw or '').strip()
    key = _norm_key(raw)
    if not key or not catalog:
        return raw
    for name in catalog:
        if _norm_key(name) == key:
            return name
    frag = _SUBJECT_ALIASES.get(key)
    if frag:
        ndrag = _norm_key(frag)
        # Exact match first — a plain substring check would let "Mathematics"
        # win over "Further Mathematics" (it's literally contained in it).
        for name in catalog:
            if _norm_key(name) == ndrag:
                return name
        candidates = [name for name in catalog if ndrag in _norm_key(name) or _norm_key(name) in ndrag]
        if candidates:
            return max(candidates, key=lambda n: len(_norm_key(n)))
    for name in catalog:
        nn = _norm_key(name)
        if nn.startswith(key) or (len(key) >= 3 and key.startswith(nn[:4])):
            return name
    return raw


_TOTALS_ROW_KEYS = {'totaloverall', 'total', 'overall', 'grandtotal'}


def build_distribution_rows(headers, rows, bands, subject_catalog=None):
    """Turn a generic ``{'headers', 'rows'}`` table into
    ``[{'subject', 'candidates', 'counts': {band: n}}]``. Column 0 is always
    the subject (every branch sheet we've seen puts it first); every other
    column is classified with :func:`classify_header`."""
    roles = [('subject', None)]
    for h in headers[1:]:
        roles.append(classify_header(h, bands))

    out = []
    for row in rows:
        subj_raw = (row[0] if row else '').strip()
        if not subj_raw or _norm_key(subj_raw) in _TOTALS_ROW_KEYS:
            continue
        subject = match_subject_name(subj_raw, subject_catalog)
        candidates = 0
        counts = {b: 0 for b in bands}
        for i, (role, extra) in enumerate(roles):
            if i == 0 or i >= len(row):
                continue
            raw = (row[i] or '').strip().replace(',', '')
            if not raw:
                continue
            try:
                val = int(round(float(raw)))
            except ValueError:
                continue
            if role == 'candidates':
                candidates = val
            elif role == 'band' and extra:
                if len(extra) == 1:
                    counts[extra[0]] = counts.get(extra[0], 0) + val
                else:
                    share, rem = divmod(val, len(extra))
                    for j, b in enumerate(extra):
                        counts[b] = counts.get(b, 0) + share + (1 if j < rem else 0)
        if not candidates:
            candidates = sum(counts.values())
        out.append({'subject': subject, 'candidates': candidates, 'counts': counts})
    return merge_rows_by_subject(out)


def merge_rows_by_subject(rows):
    """Collapse rows that share the same subject (after normalization —
    e.g. a sheet listing both "Mathematics" and "General Mathematics") into
    one, summing candidates and band counts. Preserves first-seen order."""
    merged = {}
    order = []
    for r in rows:
        key = _norm_key(r['subject'])
        if not key:
            continue
        if key not in merged:
            merged[key] = {'subject': r['subject'], 'candidates': 0, 'counts': {}}
            order.append(key)
        m = merged[key]
        m['candidates'] += r.get('candidates', 0)
        for b, c in (r.get('counts') or {}).items():
            m['counts'][b] = m['counts'].get(b, 0) + c
    return [merged[k] for k in order]
