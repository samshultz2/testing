"""Engine-agnostic OCR table reconstruction + post-processing.

These exercise the core correctness requirement of the score-sheet importer:
every value lands in the CORRECT row and CORRECT column (from token geometry,
not OCR reading order), and no score is ever invented.
"""
from utils.ocr.reconstruct import reconstruct
from utils.ocr import postprocess as pp


def _tok(text, x1, y1, x2, y2, conf=0.98):
    return {'text': text, 'conf': conf, 'box': [x1, y1, x2, y2]}


def _sheet_tokens():
    """A 3-column sheet (Name, LIT, PHY), header + two student rows. LIT of the
    second student is blank (no token); PHY of the second is 'IOO' (needs rescue).
    Tokens are deliberately given out of reading order to prove geometry wins."""
    return [
        # header
        _tok('Student Name', 10, 0, 110, 18), _tok('LIT', 140, 0, 170, 18), _tok('PHY', 240, 0, 270, 18),
        # row 1 (scores listed before the name to scramble reading order)
        _tok('85', 142, 40, 168, 58), _tok('62', 242, 40, 268, 58), _tok('Ada Obi', 10, 40, 95, 58),
        # row 2 — LIT missing; PHY is 'IOO'
        _tok('Bola Eze', 10, 80, 100, 98), _tok('IOO', 240, 80, 272, 98, conf=0.95),
    ]


def test_reconstruct_places_values_in_right_cells():
    g = reconstruct(_sheet_tokens(), expected_headers=['Student Name', 'LIT', 'PHY'])
    assert g['headers'] == ['Student Name', 'LIT', 'PHY']
    r1 = g['rows'][0]['cells']
    assert r1[0]['text'] == 'Ada Obi'      # name landed in col 0 despite token order
    assert r1[1]['text'] == '85'           # LIT
    assert r1[2]['text'] == '62'           # PHY
    r2 = g['rows'][1]['cells']
    assert r2[0]['text'] == 'Bola Eze'
    assert r2[1]['tokens'] == 0            # blank LIT — nothing invented
    assert r2[2]['text'] == 'IOO'


def test_postprocess_validates_without_hallucinating():
    g = reconstruct(_sheet_tokens(), expected_headers=['Student Name', 'LIT', 'PHY'])
    g = pp.process(g, name_col=0, numeric_cols={1, 2}, min_conf=0.6)
    r1 = g['rows'][0]['cells']
    assert r1[1]['value'] == 85 and r1[1]['review_status'] == pp.OK
    assert r1[2]['value'] == 62 and r1[2]['review_status'] == pp.OK
    r2 = g['rows'][1]['cells']
    # Blank cell stays blank — NOT turned into 0.
    assert r2[1]['value'] is None and r2[1]['review_status'] == pp.EMPTY
    # 'IOO' rescued to 100 but flagged as corrected (needs a glance).
    assert r2[2]['value'] == 100 and r2[2]['review_status'] == pp.CORRECTED
    assert 'normalized' in r2[2]['reasons']


def test_zero_is_kept_distinct_from_empty():
    assert pp.normalize_score('0') == (0, pp.OK, [])
    assert pp.normalize_score('') == (None, pp.EMPTY, [])
    assert pp.normalize_score('-') == (None, pp.EMPTY, [])


def test_out_of_range_and_ambiguous_flagged():
    v, st, why = pp.normalize_score('150')
    assert st == pp.REVIEW and 'out_of_range' in why
    v, st, why = pp.normalize_score('7?')
    assert v is None and st == pp.REVIEW and 'ambiguous' in why


def test_name_never_numeric_validated_and_crop_flag():
    # A name box hard against the left edge is flagged possibly-cropped, not changed.
    toks = [_tok('Student Name', 10, 0, 110, 18), _tok('LIT', 140, 0, 170, 18),
            _tok('nthony Jeffery', 0, 40, 95, 58, conf=0.5), _tok('69', 142, 40, 168, 58)]
    g = reconstruct(toks, expected_headers=['Student Name', 'LIT'])
    g = pp.process(g, name_col=0, numeric_cols={1}, min_conf=0.6, image_width=400)
    name_cell = g['rows'][0]['cells'][0]
    assert name_cell['value'] == 'nthony Jeffery'      # preserved, not "corrected"
    assert name_cell['review_status'] == pp.REVIEW
    assert 'possibly_cropped' in name_cell['reasons']
    assert 'low_confidence' in name_cell['reasons']


def test_low_confidence_number_requires_review():
    toks = [_tok('Student Name', 10, 0, 110, 18), _tok('BIO', 140, 0, 170, 18),
            _tok('Ada', 10, 40, 95, 58), _tok('90', 142, 40, 168, 58, conf=0.42)]
    g = reconstruct(toks, expected_headers=['Student Name', 'BIO'])
    g = pp.process(g, name_col=0, numeric_cols={1}, min_conf=0.6)
    cell = g['rows'][0]['cells'][1]
    assert cell['value'] == 90 and cell['review_status'] == pp.REVIEW
    assert 'low_confidence' in cell['reasons']
    assert g['review_count'] >= 1 and (0, 1) in g['issues']


def test_pipeline_with_supplied_tokens():
    from utils.ocr.pipeline import extract_table
    out = extract_table(b'', expected_headers=['Student Name', 'LIT', 'PHY'],
                        tokens=_sheet_tokens())
    assert out is not None
    assert out['headers'] == ['Student Name', 'LIT', 'PHY']
    assert out['name_col'] == 0
    # Values view: row 1 has the scores; row 2 LIT blank, PHY rescued to 100.
    assert out['rows'][0][1] == '85' and out['rows'][0][2] == '62'
    assert out['rows'][1][1] == '' and out['rows'][1][2] == '100'
    # The corrected 'IOO' cell is flagged for a human glance.
    assert '1,2' in out['cell_flags']
