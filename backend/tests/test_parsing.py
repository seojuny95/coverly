import io

from pypdf import PdfWriter

from app.services.policy.models import ParsedDocument
from app.services.policy.parsing import parse_document


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_parse_document_returns_parsed_document_shape() -> None:
    result = parse_document(_blank_pdf())
    assert isinstance(result, ParsedDocument)
    assert isinstance(result.text, str)
    assert isinstance(result.layout_text, str)
    assert isinstance(result.tables, tuple)


def test_parse_document_blank_pdf_has_empty_text_and_no_tables() -> None:
    result = parse_document(_blank_pdf())
    assert result.text == ""
    assert result.layout_text == ""
    assert result.tables == ()


def test_parse_document_does_not_raise_on_corrupt_bytes() -> None:
    # Robustness: a malformed PDF must surface as empty text (route maps to 422),
    # never an unhandled crash.
    result = parse_document(b"%PDF-broken")
    assert result.text == ""
    assert result.tables == ()
