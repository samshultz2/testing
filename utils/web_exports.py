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

from flask import Response

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PDF_MIME = 'application/pdf'


def _disposition(filename, inline):
    kind = 'inline' if inline else 'attachment'
    return {'Content-Disposition': f'{kind}; filename={filename}'}


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
