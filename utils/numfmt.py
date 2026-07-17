"""Human number formatting shared across results displays and printouts.

Whole numbers print without a trailing ``.0`` (34, not 34.0); genuinely
fractional numbers print to a fixed number of decimals (default 2), so 34.3 ->
"34.30" and 34.333 -> "34.33". Non-numeric / blank values pass through so the
caller's own placeholder (``-`` etc.) is preserved.
"""


def fmt_num(value, dp=2, blank=''):
    """Format ``value`` as a whole number when it is whole, else to ``dp`` decimals."""
    if value is None or value == '':
        return blank
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    if f == int(f):
        return str(int(f))
    return f'{f:.{dp}f}'
