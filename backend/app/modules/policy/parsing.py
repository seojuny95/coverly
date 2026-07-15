"""Single-pass PDF parsing: bytes -> ParsedDocument.

pdfplumber recovers both the text layer and ruled tables in one open, so the
whole pipeline parses the PDF exactly once. text is plain reading-order text
(classification, summary); layout_text preserves column alignment for the
coverage table fallback; tables carries every table raw for coverage selection.

Never raises on a malformed PDF: it degrades to empty text so the route maps the
empty result to 422 instead of a 500.
"""

import io

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.modules.policy.models import ParsedDocument, Table


class PdfPasswordRequiredError(Exception):
    """The PDF is encrypted and needs a password before text extraction."""


class PdfPasswordIncorrectError(Exception):
    """The supplied PDF password could not unlock the document."""


def _check_pdf_password(pdf_bytes: bytes, password: str | None) -> None:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except PdfReadError:
        return

    if not reader.is_encrypted:
        return

    if not password:
        if reader.decrypt("") == 0:
            raise PdfPasswordRequiredError
        return

    if reader.decrypt(password) == 0:
        raise PdfPasswordIncorrectError


def parse_document(pdf_bytes: bytes, password: str | None = None) -> ParsedDocument:
    """Parse a PDF to text and tables, degrading gracefully on corrupt input."""
    _check_pdf_password(pdf_bytes, password)
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes), password=password) as pdf:
            tables: list[Table] = []
            for page in pdf.pages:
                for raw_table in page.extract_tables():
                    rows = tuple(tuple(cell for cell in row) for row in raw_table)
                    tables.append(rows)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
            layout_text = "\n".join(
                page.extract_text(layout=True) or "" for page in pdf.pages
            ).strip()
    except (PDFPasswordIncorrect, PDFEncryptionError):
        if password:
            raise PdfPasswordIncorrectError from None
        raise PdfPasswordRequiredError from None
    except Exception:
        return ParsedDocument(text="", layout_text="", tables=())
    return ParsedDocument(text=text, layout_text=layout_text, tables=tuple(tables))
