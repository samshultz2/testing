"""Mock JAMB question rendering: [table: …] -> real table for the web (escaped,
maths left for MathJax) and LaTeX -> readable Unicode for non-MathJax surfaces."""
from utils.mathtext import question_html, latex_to_text


def test_question_html_renders_table_marker():
    out = str(question_html('Study the data [table: Price | Qty ; 8 | 10 ; 6 | 12] and answer.'))
    assert '<table class="mjq-table">' in out
    assert '<div class="mjq-tablewrap">' in out          # responsive scroll wrapper
    assert '<th>Price</th><th>Qty</th>' in out          # first row is the header
    assert '<td>8</td><td>10</td>' in out
    assert out.startswith('Study the data ') and out.endswith(' and answer.')


def test_question_html_escapes_but_keeps_math():
    out = str(question_html('If a < b then \\(3x^2+2x-5\\) & done'))
    assert '&lt;' in out and '&amp;' in out              # HTML-escaped, safe to mark safe
    assert '\\(3x^2+2x-5\\)' in out                      # math markup left intact for MathJax


def test_question_html_escapes_table_cell_content():
    out = str(question_html('[table: <script> | ok]'))
    assert '<script>' not in out and '&lt;script&gt;' in out   # cell content is escaped


def test_question_html_blank():
    assert str(question_html(None)) == '' and str(question_html('')) == ''


def test_latex_to_text_superscripts_and_symbols():
    assert latex_to_text('3x\\(^2\\) + 2x - 5') == '3x² + 2x - 5'
    assert latex_to_text('\\(\\frac{3}{5}\\)') == '(3)/(5)'
    assert latex_to_text('\\(\\sqrt{2}\\)') == '√(2)'
    assert latex_to_text('area = \\(\\pi r^2\\)') == 'area = π r²'
    assert latex_to_text('\\(101_{two}\\)') == '101_(two)'   # non-mappable subscript kept readable
