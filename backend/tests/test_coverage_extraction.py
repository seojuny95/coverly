import pytest

from app.services.coverage import extraction as extraction_module
from app.services.coverage.extraction import STATUS_OK, STATUS_PARTIAL, extract_coverages
from app.services.coverage.types import Coverage


def _coverage(name: str, detail: str | None) -> Coverage:
    return {"담보명": name, "가입금액": "1,000원", "보장내용": detail, "해설": None}


def test_generates_explanation_for_coverage_missing_policy_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        return {name: f"{name} 설명이에요." for name in names}, True

    coverages, status = extract_coverages(
        b"%PDF-",
        normalize=lambda _s: [_coverage("교통사고처리지원금", None)],
        explain=fake_explain,
    )

    assert status == STATUS_OK
    assert coverages[0]["해설"] == "교통사고처리지원금 설명이에요."


def test_policy_wording_is_not_overwritten_by_generated_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    # An explanation is offered for every name, but a coverage that already has
    # policy wording must keep it — 해설 stays None (증권 원문 우선).
    def fake_explain(names: list[str]) -> tuple[dict[str, str], bool]:
        return {name: "지어낸 설명" for name in names}, True

    coverages, status = extract_coverages(
        b"%PDF-",
        normalize=lambda _s: [
            _coverage("암진단비", "암 진단 시 지급"),
            _coverage("교통사고처리지원금", None),
        ],
        explain=fake_explain,
    )

    assert status == STATUS_OK
    assert coverages[0]["보장내용"] == "암 진단 시 지급"
    assert coverages[0]["해설"] is None
    assert coverages[1]["해설"] == "지어낸 설명"


def test_partial_when_explanations_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    coverages, status = extract_coverages(
        b"%PDF-",
        normalize=lambda _s: [_coverage("암진단비", None)],
        explain=lambda _names: ({}, False),
    )

    assert status == STATUS_PARTIAL
    assert coverages[0]["담보명"] == "암진단비"  # coverages are still returned
    assert coverages[0]["해설"] is None


def test_degrades_to_empty_partial_when_normalization_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extraction_module, "extract_coverage_source", lambda _b: "| 담보표 |")

    def failing_normalize(_source: str) -> list[Coverage]:
        raise RuntimeError("LLM down")

    coverages, status = extract_coverages(b"%PDF-", normalize=failing_normalize)

    assert coverages == []
    assert status == STATUS_PARTIAL


def test_degrades_to_empty_partial_on_unreadable_pdf() -> None:
    # Real pdfplumber path: garbage bytes must never raise out of the pipeline.
    coverages, status = extract_coverages(b"%PDF-broken not a real pdf")

    assert coverages == []
    assert status == STATUS_PARTIAL
