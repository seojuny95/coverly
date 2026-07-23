"""Single-pass PDF parsing: bytes -> ParsedDocument.

pdfplumber recovers both the text layer and ruled tables in one open. text is
plain reading-order text (classification, summary); layout_text preserves
column alignment for the coverage table fallback; tables carries raw tables for
coverage selection. Page, extracted-character, and table-cell limits bound the
work before downstream processing.

Never raises on a malformed PDF: it degrades to empty text so the route maps the
empty result to 422 instead of a 500. Resource-limit errors remain explicit.
"""

import io

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.modules.policy.models import ParsedDocument, Table

MAX_PDF_PAGES = 100
MAX_PDF_EXTRACTED_CHARACTERS = 500_000
MAX_PDF_TABLE_CELLS = 50_000


class PdfPasswordRequiredError(Exception):
    """The PDF is encrypted and needs a password before text extraction."""


class PdfPasswordIncorrectError(Exception):
    """The supplied PDF password could not unlock the document."""


class PdfPageLimitExceededError(Exception):
    """The PDF has more pages than the parser accepts."""


class PdfComplexityLimitExceededError(Exception):
    """The PDF expands beyond the parser's text or table-cell budget."""


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


def _append_text(
    parts: list[str],
    value: str,
    extracted_characters: int,
) -> int:
    separator_characters = 1 if parts else 0
    extracted_characters += separator_characters + len(value)
    if extracted_characters > MAX_PDF_EXTRACTED_CHARACTERS:
        raise PdfComplexityLimitExceededError
    parts.append(value)
    return extracted_characters


def _append_tables(
    tables: list[Table],
    raw_tables: list[list[list[str | None]]],
    *,
    extracted_characters: int,
    table_cells: int,
) -> tuple[int, int]:
    for raw_table in raw_tables:
        rows: list[tuple[str | None, ...]] = []
        for raw_row in raw_table:
            table_cells += len(raw_row)
            if table_cells > MAX_PDF_TABLE_CELLS:
                raise PdfComplexityLimitExceededError

            row = tuple(raw_row)
            extracted_characters += sum(len(cell) for cell in row if cell is not None)
            if extracted_characters > MAX_PDF_EXTRACTED_CHARACTERS:
                raise PdfComplexityLimitExceededError
            rows.append(row)
        tables.append(tuple(rows))
    return extracted_characters, table_cells


def parse_document(pdf_bytes: bytes, password: str | None = None) -> ParsedDocument:
    """Parse a PDF to text and tables, degrading gracefully on corrupt input."""
    _check_pdf_password(pdf_bytes, password)
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes), password=password) as pdf:
            pages = pdf.pages
            if len(pages) > MAX_PDF_PAGES:
                raise PdfPageLimitExceededError

            text_parts: list[str] = []
            layout_text_parts: list[str] = []
            tables: list[Table] = []
            extracted_characters = 0
            table_cells = 0

            for page in pages:
                extracted_characters = _append_text(
                    text_parts,
                    page.extract_text() or "",
                    extracted_characters,
                )
                extracted_characters = _append_text(
                    layout_text_parts,
                    page.extract_text(layout=True) or "",
                    extracted_characters,
                )
                extracted_characters, table_cells = _append_tables(
                    tables,
                    page.extract_tables(),
                    extracted_characters=extracted_characters,
                    table_cells=table_cells,
                )
    except (PDFPasswordIncorrect, PDFEncryptionError):
        if password:
            raise PdfPasswordIncorrectError from None
        raise PdfPasswordRequiredError from None
    except (PdfPageLimitExceededError, PdfComplexityLimitExceededError):
        raise
    except Exception:
        return ParsedDocument(text="", layout_text="", tables=())
    text = "\n".join(text_parts).strip()
    layout_text = "\n".join(layout_text_parts).strip()
    return ParsedDocument(text=text, layout_text=layout_text, tables=tuple(tables))
