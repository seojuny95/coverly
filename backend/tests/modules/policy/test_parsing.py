import io

import pdfplumber
import pytest
from pypdf import PdfWriter

from app.modules.policy import parsing
from app.modules.policy.models import ParsedDocument
from app.modules.policy.parsing import (
    PdfComplexityLimitExceededError,
    PdfPageLimitExceededError,
    PdfPasswordIncorrectError,
    PdfPasswordRequiredError,
    parse_document,
)


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _encrypted_blank_pdf(password: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _owner_only_encrypted_blank_pdf(owner_password: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("", owner_password=owner_password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class _FakePage:
    def __init__(
        self,
        *,
        text: str = "",
        layout_text: str = "",
        tables: list[list[list[str | None]]] | None = None,
    ) -> None:
        self._text = text
        self._layout_text = layout_text
        self._tables = tables or []

    def extract_text(self, *, layout: bool = False) -> str:
        return self._layout_text if layout else self._text

    def extract_tables(self) -> list[list[list[str | None]]]:
        return self._tables


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _use_fake_pdf(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[_FakePage],
) -> None:
    def _open(*_args: object, **_kwargs: object) -> _FakePdf:
        return _FakePdf(pages)

    monkeypatch.setattr(pdfplumber, "open", _open)


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


def test_parse_document_requires_password_for_encrypted_pdf() -> None:
    try:
        parse_document(_encrypted_blank_pdf("secret"))
    except PdfPasswordRequiredError:
        pass
    else:
        raise AssertionError("expected PdfPasswordRequiredError")


def test_parse_document_rejects_wrong_password_for_encrypted_pdf() -> None:
    try:
        parse_document(_encrypted_blank_pdf("secret"), password="wrong")
    except PdfPasswordIncorrectError:
        pass
    else:
        raise AssertionError("expected PdfPasswordIncorrectError")


def test_parse_document_accepts_correct_password_for_encrypted_pdf() -> None:
    result = parse_document(_encrypted_blank_pdf("secret"), password="secret")
    assert isinstance(result, ParsedDocument)


def test_parse_document_accepts_owner_only_encrypted_pdf_without_password() -> None:
    result = parse_document(_owner_only_encrypted_blank_pdf("owner-secret"))
    assert isinstance(result, ParsedDocument)


def test_parse_document_extracts_normal_text_and_tables_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_pdf(
        monkeypatch,
        [
            _FakePage(
                text="policy overview",
                layout_text="policy  overview",
                tables=[[["coverage", "amount"], ["sample benefit", "100"]]],
            )
        ],
    )

    result = parse_document(b"%PDF-normal")

    assert result == ParsedDocument(
        text="policy overview",
        layout_text="policy  overview",
        tables=((("coverage", "amount"), ("sample benefit", "100")),),
    )


def test_parse_document_rejects_excessive_page_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parsing, "MAX_PDF_PAGES", 1)
    _use_fake_pdf(monkeypatch, [_FakePage(), _FakePage()])

    with pytest.raises(PdfPageLimitExceededError):
        parse_document(b"%PDF-too-many-pages")


def test_parse_document_rejects_excessive_extracted_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parsing, "MAX_PDF_EXTRACTED_CHARACTERS", 5)
    _use_fake_pdf(monkeypatch, [_FakePage(text="123456")])

    with pytest.raises(PdfComplexityLimitExceededError):
        parse_document(b"%PDF-too-much-text")


def test_parse_document_rejects_excessive_table_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parsing, "MAX_PDF_TABLE_CELLS", 1)
    _use_fake_pdf(monkeypatch, [_FakePage(tables=[[["coverage", "amount"]]])])

    with pytest.raises(PdfComplexityLimitExceededError):
        parse_document(b"%PDF-too-many-cells")
