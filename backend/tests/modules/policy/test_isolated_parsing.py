import io

import pytest
from pypdf import PdfWriter

from app.modules.policy.isolated_parsing import parse_document_isolated
from app.modules.policy.parsing import PdfPasswordRequiredError


def _blank_pdf(*, password: str | None = None) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if password is not None:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_isolated_parser_returns_a_picklable_document() -> None:
    result = parse_document_isolated(_blank_pdf())

    assert result.text == ""
    assert result.layout_text == ""
    assert result.tables == ()


def test_isolated_parser_preserves_public_password_errors() -> None:
    with pytest.raises(PdfPasswordRequiredError):
        parse_document_isolated(_blank_pdf(password="secret"))
