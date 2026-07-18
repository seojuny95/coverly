import json
import re

import pytest

from app.rag.official.loaders import load_official_chunks
from app.rag.official.models import RagChunk
from evals.rag.official.generation import (
    EVAL_FIXTURE,
    GenerationEvalCase,
    evaluate_generation,
    load_generation_eval_cases,
    render_report,
)


def test_generation_eval_fixture_uses_existing_fixed_context_chunks() -> None:
    cases = load_generation_eval_cases()
    chunk_ids = {chunk.id for chunk in load_official_chunks()}
    case_ids = [case.id for case in cases]

    assert len(cases) == 60
    assert len(case_ids) == len(set(case_ids))
    assert {case.expected_status for case in cases} == {"answered", "no_evidence", "filtered"}
    assert all(chunk_id in chunk_ids for case in cases for chunk_id in case.hit_chunk_ids)
    assert all(
        citation_id in case.hit_chunk_ids
        for case in cases
        for citation_id in case.required_citation_ids
    )


def test_generation_eval_dataset_has_stable_schema() -> None:
    raw_cases = json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))
    expected_keys = {
        "id",
        "questions",
        "profile",
        "difficulty",
        "hit_chunk_ids",
        "expected_status",
        "must_include_groups",
        "must_not_include",
        "required_citation_ids",
        "expected_missing_context_terms",
    }

    assert raw_cases
    assert len(raw_cases) == 30
    assert all(len(raw_case["questions"]) == 2 for raw_case in raw_cases)
    assert all(set(raw_case) == expected_keys for raw_case in raw_cases)


def test_generation_eval_dataset_contains_no_personal_identifiers() -> None:
    serialized = EVAL_FIXTURE.read_text(encoding="utf-8")

    assert re.search(r"\b\d{6}-[1-4]\d{6}\b", serialized) is None
    assert re.search(r"\b01[016789]-?\d{3,4}-?\d{4}\b", serialized) is None
    assert re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", serialized) is None


def test_generation_eval_scores_contract_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk = RagChunk(
        id="chunk-1",
        source_id="source",
        source_title="공식자료",
        source_category="standard_clause",
        publisher="테스트",
        text="계약자는 청약할 때 중요한 사항을 사실대로 알려야 합니다.",
        page_start=1,
        page_end=1,
    )
    cases = (
        GenerationEvalCase(
            id="passing",
            question="암 진단비 받을 수 있어?",
            hit_chunk_ids=("chunk-1",),
            expected_status="answered",
            must_include_groups=(("사실대로", "정확히"),),
            must_not_include=("무조건 보장",),
            required_citation_ids=("chunk-1",),
            expected_missing_context_terms=("가입 상품 약관", "진단확정 서류"),
        ),
        GenerationEvalCase(
            id="failing",
            question="암 진단비 받을 수 있어?",
            hit_chunk_ids=("chunk-1",),
            expected_status="answered",
            must_include_groups=(("없는 표현", "다른 없는 표현"),),
            must_not_include=("무조건 보장", "반드시 지급"),
            required_citation_ids=("chunk-1",),
            expected_missing_context_terms=("없는 맥락",),
        ),
    )

    monkeypatch.setattr(
        "evals.rag.official.generation.load_official_chunks",
        lambda: (chunk,),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "answer": "청약할 때 중요한 사항을 사실대로 알려야 하며 반드시 지급됩니다.",
            "citation_ids": ["chunk-1"],
            "missing_context": ["가입 상품 약관", "진단 확정 서류"],
        }

    report = evaluate_generation(cases, complete=complete)

    assert report.passed == 1
    assert report.total == 2
    assert report.pass_rate == 0.5
    assert report.status_match_rate == 1.0
    assert report.citation_valid_rate == 1.0
    assert report.results[0].passed
    assert report.results[1].failed_checks == (
        "must_include",
        "must_not_include",
        "missing_context",
    )
    assert "FAIL failing" in render_report(report)


def test_generation_eval_accepts_one_citation_from_required_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = (
        RagChunk(
            id="chunk-1",
            source_id="source",
            source_title="공식자료",
            source_category="standard_clause",
            publisher="테스트",
            text="계약 전 알릴 의무는 중요한 사항을 사실대로 알리는 것입니다.",
            page_start=1,
            page_end=1,
        ),
        RagChunk(
            id="chunk-2",
            source_id="source",
            source_title="공식자료",
            source_category="standard_clause",
            publisher="테스트",
            text="동일한 내용을 다른 표준약관 조항에서도 설명합니다.",
            page_start=2,
            page_end=2,
        ),
    )
    case = GenerationEvalCase(
        id="citation-group",
        question="계약 전 알릴 의무가 뭐야?",
        hit_chunk_ids=("chunk-1", "chunk-2"),
        expected_status="answered",
        must_include_groups=(("사실대로",),),
        must_not_include=(),
        required_citation_ids=(),
        required_citation_groups=(("chunk-1", "chunk-2"),),
        expected_missing_context_terms=(),
    )

    monkeypatch.setattr(
        "evals.rag.official.generation.load_official_chunks",
        lambda: chunks,
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "answer": "중요한 사항을 사실대로 알리는 것입니다.",
            "citation_ids": ["chunk-2"],
            "missing_context": [],
        }

    report = evaluate_generation((case,), complete=complete)

    assert report.passed == 1
    assert report.required_citation_coverage == 1.0


def test_generation_eval_keeps_empty_explicit_case_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "evals.rag.official.generation.load_generation_eval_cases",
        lambda: (_ for _ in ()).throw(AssertionError("fixture should not load")),
    )

    report = evaluate_generation((), complete=lambda _system, _user: {})

    assert report.total == 0
    assert report.passed == 0
    assert report.pass_rate == 0.0


def test_generation_eval_missing_context_notes_use_item_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk = RagChunk(
        id="chunk-1",
        source_id="source",
        source_title="공식자료",
        source_category="standard_clause",
        publisher="테스트",
        text="보험금을 지급하지 않는 사유는 약관에서 확인합니다.",
        page_start=1,
        page_end=1,
    )
    cases = (
        GenerationEvalCase(
            id="missing-context-item",
            question="보험금을 지급하지 않는 사유는 어디서 확인해?",
            hit_chunk_ids=("chunk-1",),
            expected_status="answered",
            must_include_groups=(("약관",),),
            must_not_include=(),
            required_citation_ids=("chunk-1",),
            expected_missing_context_terms=("가입 상품 약관",),
        ),
    )

    monkeypatch.setattr(
        "evals.rag.official.generation.load_official_chunks",
        lambda: (chunk,),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "answer": "약관에서 확인할 수 있습니다.",
            "citation_ids": ["chunk-1"],
            "missing_context": ["가입 상품 약관 및 보험증권"],
        }

    report = evaluate_generation(cases, complete=complete)

    assert not report.results[0].passed
    assert report.results[0].failed_checks == ("missing_context",)
    assert report.results[0].notes == ("missing expected missing_context terms: 가입 상품 약관",)


def test_generation_eval_requires_openai_key_for_live_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        openai_api_key = ""

    monkeypatch.setattr(
        "evals.rag.official.generation.get_settings",
        lambda: _Settings(),
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        evaluate_generation(())
