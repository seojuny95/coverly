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

from app.services.types import ParsedDocument, Table


def parse_document(pdf_bytes: bytes) -> ParsedDocument:
    """Parse a PDF to text and tables, degrading gracefully on corrupt input."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tables: list[Table] = []
            for page in pdf.pages:
                for raw_table in page.extract_tables():
                    rows = tuple(tuple(cell for cell in row) for row in raw_table)
                    tables.append(rows)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages).strip()
            layout_text = "\n".join(
                page.extract_text(layout=True) or "" for page in pdf.pages
            ).strip()
    except Exception:
        return ParsedDocument(text="", layout_text="", tables=())
    return ParsedDocument(text=text, layout_text=layout_text, tables=tuple(tables))
