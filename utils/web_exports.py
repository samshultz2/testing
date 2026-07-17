"""Shared helpers for file-download responses (Excel / PDF).

Consolidates the ``BytesIO`` + ``mimetype`` + ``Content-Disposition`` boilerplate
that was repeated ~19 times across the route modules. Behaviour is identical to
the inline versions; this just removes the duplication and gives one place to
fix MIME/headers.

Example:
    from utils.web_exports import xlsx_response
    wb = Workbook(); ...
    return xlsx_response(wb, f'students_{term}.xlsx')
"""
from io import BytesIO
from xml.sax.saxutils import escape as _xml_escape

from flask import Response

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PDF_MIME = 'application/pdf'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
PNG_MIME = 'image/png'

# Characters that make Excel/Sheets treat a cell as a formula.
_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def formula_guard(value):
    """Neutralise CSV/Excel formula injection: a string that starts with a
    formula trigger (e.g. a student named ``=cmd|...``) is prefixed with a
    single quote so spreadsheets render it as text instead of executing it.
    Non-strings (numbers, dates) pass through unchanged."""
    if isinstance(value, str) and value[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def pdf_escape(value):
    """Escape a value before it is interpolated into reportlab ``Paragraph``
    mini-XML markup. A name/comment containing ``<``/``&``/``>`` would otherwise
    corrupt the layout or inject reportlab tags (reportlab runs no JS, so this is
    markup-injection hardening, not XSS). ``None`` becomes ''."""
    return _xml_escape('' if value is None else str(value))


def _disposition(filename, inline):
    """RFC 6266 Content-Disposition. The filename is quoted (so spaces — e.g. a
    term name like "First Term" — don't truncate the download) and also sent as
    ``filename*=UTF-8''`` so accented names survive; control chars are stripped
    to prevent header injection."""
    from urllib.parse import quote
    kind = 'inline' if inline else 'attachment'
    name = ''.join(c for c in str(filename) if c >= ' ' and c not in '\r\n')
    ascii_name = name.replace('"', '').replace('\\', '').encode('ascii', 'ignore').decode() or 'download'
    star = quote(name, safe='')
    return {'Content-Disposition': f'{kind}; filename="{ascii_name}"; filename*=UTF-8\'\'{star}'}


CSV_MIME = 'text/csv; charset=utf-8'


def csv_response(text, filename, inline=False):
    """Build a ``.csv`` download from CSV text (e.g. ``io.StringIO().getvalue()``).

    Prepends a UTF-8 BOM so Excel — the tool used for financial/ministry audits —
    renders accented names correctly instead of mojibake, sets an explicit utf-8
    charset, and quotes the filename (see :func:`_disposition`)."""
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    body = '﻿' + text                    # BOM for Excel UTF-8 detection
    return Response(body.encode('utf-8'), mimetype=CSV_MIME,
                    headers=_disposition(filename, inline))


def xlsx_response(data, filename, inline=False):
    """Build an ``.xlsx`` download response.

    ``data`` may be an openpyxl ``Workbook`` (it is saved), a ``BytesIO`` (read
    via ``getvalue``), or raw ``bytes`` — covering every existing call shape.
    """
    if hasattr(data, 'save'):          # openpyxl Workbook
        buf = BytesIO()
        data.save(buf)
        data = buf
    if hasattr(data, 'getvalue'):      # BytesIO / similar buffer
        data = data.getvalue()
    return Response(data, mimetype=XLSX_MIME,
                    headers=_disposition(filename, inline))


def pdf_response(data, filename, inline=True):
    """Wrap PDF bytes (or a ``BytesIO``) in a response.

    Defaults to ``inline`` so the browser previews the PDF; pass
    ``inline=False`` to force a download.
    """
    if hasattr(data, 'getvalue'):
        data = data.getvalue()
    return Response(data, mimetype=PDF_MIME,
                    headers=_disposition(filename, inline))


def docx_response(data, filename, inline=False):
    """Wrap Word (.docx) bytes (or a python-docx ``Document`` / ``BytesIO``)."""
    if hasattr(data, 'save') and not hasattr(data, 'getvalue'):   # python-docx Document
        buf = BytesIO(); data.save(buf); data = buf
    if hasattr(data, 'getvalue'):
        data = data.getvalue()
    return Response(data, mimetype=DOCX_MIME,
                    headers=_disposition(filename, inline))


def png_response(data, filename, inline=True):
    """Wrap PNG image bytes (or a ``BytesIO``) in a response."""
    if hasattr(data, 'getvalue'):
        data = data.getvalue()
    return Response(data, mimetype=PNG_MIME,
                    headers=_disposition(filename, inline))
