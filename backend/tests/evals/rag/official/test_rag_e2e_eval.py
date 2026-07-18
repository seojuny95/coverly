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

    assert len(raw_cases) >= 30
    assert all(set(raw_case) == {"id"} for raw_case in raw_cases)
    assert len(cases) == len(raw_cases) * 2
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
    assert "passed=1/1" in render_report(report)


def test_official_rag_e2e_requires_openai_key_for_live_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        openai_api_key = ""

    monkeypatch.setattr("evals.rag.official.e2e.get_settings", lambda: _Settings())

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        evaluate_e2e((), complete=None, live_generation=True)
