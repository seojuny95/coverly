import json
import re

import pytest

from app.rag.official.models import RagChunk, RetrievalHit
from evals.rag.official.e2e import (
    EVAL_FIXTURE,
    evaluate_e2e,
    load_e2e_eval_cases,
    offline_extractive_completer,
    render_report,
)
from evals.rag.official.generation import GenerationEvalCase


def test_official_rag_e2e_dataset_selects_generation_scenarios() -> None:
    raw_cases = json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))
    cases = load_e2e_eval_cases()

    assert set(raw_cases) == {"generation_cases", "retrieval_cases", "extra_cases"}
    assert raw_cases["generation_cases"]["include"] == "all"
    assert raw_cases["retrieval_cases"]["include"] == "all"
    assert len(raw_cases["extra_cases"]) >= 15
    assert len(cases) >= 150
    assert {case.expected_status for case in cases} == {"answered", "filtered", "no_evidence"}


def test_official_rag_e2e_dataset_contains_no_personal_identifiers() -> None:
    serialized = EVAL_FIXTURE.read_text(encoding="utf-8")

    assert re.search(r"\b\d{6}-[1-4]\d{6}\b", serialized) is None
    assert re.search(r"\b01[016789]-?\d{3,4}-?\d{4}\b", serialized) is None
    assert re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", serialized) is None
    assert "계좌번호" not in serialized


def test_official_rag_e2e_scores_retrieval_then_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk = RagChunk(
        id="chunk-1",
        source_id="source",
        source_title="공식자료",
        source_category="standard_clause",
        publisher="테스트",
        text="보험나이는 6개월 미만 끝수는 버리고 6개월 이상은 1년으로 계산합니다.",
        page_start=1,
        page_end=1,
    )
    case = GenerationEvalCase(
        id="insurance-age__q1",
        question="보험나이는 어떻게 계산해?",
        hit_chunk_ids=("chunk-1",),
        expected_status="answered",
        must_include_groups=(("6개월",), ("1년",)),
        must_not_include=("가입하세요",),
        required_citation_ids=("chunk-1",),
        expected_missing_context_terms=(),
    )

    monkeypatch.setattr("evals.rag.official.e2e.load_official_chunks", lambda: (chunk,))
    monkeypatch.setattr(
        "evals.rag.official.e2e.retrieve",
        lambda **_: [RetrievalHit(chunk=chunk, score=1.0, keyword_score=1.0, vector_score=1.0)],
    )

    report = evaluate_e2e((case,), complete=offline_extractive_completer)

    assert report.passed == 1
    assert report.pass_rate == 1.0
    assert report.retrieval_required_citation_rate == 1.0
    assert report.failure_buckets == {"passed": 1}
    assert "passed=1/1" in render_report(report)


def test_official_rag_e2e_accepts_one_retrieved_citation_from_required_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk = RagChunk(
        id="chunk-2",
        source_id="source",
        source_title="공식자료",
        source_category="standard_clause",
        publisher="테스트",
        text="계약자는 청약할 때 중요한 사항을 사실대로 알려야 합니다.",
        page_start=1,
        page_end=1,
    )
    case = GenerationEvalCase(
        id="disclosure__q1",
        question="계약 전 알릴 의무가 뭐야?",
        hit_chunk_ids=("chunk-1", "chunk-2"),
        expected_status="answered",
        must_include_groups=(("사실대로",),),
        must_not_include=(),
        required_citation_ids=(),
        required_citation_groups=(("chunk-1", "chunk-2"),),
        expected_missing_context_terms=(),
    )

    monkeypatch.setattr("evals.rag.official.e2e.load_official_chunks", lambda: (chunk,))
    monkeypatch.setattr(
        "evals.rag.official.e2e.retrieve",
        lambda **_: [RetrievalHit(chunk=chunk, score=1.0, keyword_score=1.0, vector_score=1.0)],
    )

    report = evaluate_e2e((case,), complete=offline_extractive_completer)

    assert report.passed == 1
    assert report.retrieval_required_citation_rate == 1.0


def test_official_rag_e2e_accepts_equivalent_standard_clause_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_chunk = RagChunk(
        id="life-disclosure",
        source_id="standard_terms",
        source_title="표준약관",
        source_category="standard_clause",
        publisher="테스트",
        text="중요한 사항을 사실대로 알려야 합니다.",
        page_start=1,
        page_end=1,
        label="제13조(계약 전 알릴 의무)",
    )
    retrieved_chunk = RagChunk(
        id="injury-disclosure",
        source_id="standard_terms",
        source_title="표준약관",
        source_category="standard_clause",
        publisher="테스트",
        text="중요한 사항을 사실대로 알려야 합니다.",
        page_start=2,
        page_end=2,
        label="제15조(계약전 알릴 의무)",
    )
    case = GenerationEvalCase(
        id="equivalent-standard-clause",
        question="계약 전 알릴 의무가 뭐야?",
        hit_chunk_ids=("life-disclosure",),
        expected_status="answered",
        must_include_groups=(("사실대로",),),
        must_not_include=(),
        required_citation_ids=("life-disclosure",),
        expected_missing_context_terms=(),
    )

    monkeypatch.setattr(
        "evals.rag.official.e2e.load_official_chunks",
        lambda: (expected_chunk, retrieved_chunk),
    )
    monkeypatch.setattr(
        "evals.rag.official.e2e.retrieve",
        lambda **_: [
            RetrievalHit(chunk=retrieved_chunk, score=1.0, keyword_score=1.0, vector_score=1.0)
        ],
    )

    report = evaluate_e2e((case,), complete=offline_extractive_completer)

    assert report.passed == 1
    assert report.results[0].citation_ids == ("injury-disclosure",)


def test_official_rag_e2e_requires_openai_key_for_live_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        openai_api_key = ""

    monkeypatch.setattr("evals.rag.official.e2e.get_settings", lambda: _Settings())

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        evaluate_e2e((), complete=None, live_generation=True)
