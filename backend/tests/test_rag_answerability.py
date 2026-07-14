import json

import pytest

from app.services.rag.official.answerability import judge_evidence_sufficiency
from app.services.rag.official.evaluation.answerability import (
    evaluate_answerability,
    render_answerability_report,
)
from app.services.rag.official.evaluation.retrieval import RetrievalEvalCase
from app.services.rag.official.models import RagChunk, RetrievalHit


def test_evidence_judge_rejects_answerable_decision_without_valid_supports() -> None:
    chunk = _chunk("chunk-1", "보험금 청구는 약관에서 정한 서류가 필요합니다.")
    hit = RetrievalHit(chunk=chunk, score=1.0, keyword_score=1.0, vector_score=1.0)

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "label": "answerable",
            "supporting_citation_ids": ["missing-chunk"],
            "missing_context": [],
            "reason": "잘못된 근거 id를 반환했습니다.",
        }

    decision = judge_evidence_sufficiency("보험금 청구 서류가 뭐야?", [hit], complete=complete)

    assert decision.label == "unanswerable"
    assert decision.supporting_citation_ids == []
    assert decision.missing_context == ["질문에 직접 답하는 공식자료 근거"]


def test_answerability_eval_scores_scope_experiment_without_retrieval() -> None:
    cases = (
        RetrievalEvalCase(
            id="positive",
            query="청약 철회 기간은?",
            profile="claim_check",
            difficulty="medium",
            relevant_chunk_ids=("chunk-1",),
        ),
        RetrievalEvalCase(
            id="negative",
            query="오늘 보험회사 주가 알려줘",
            profile="out_of_scope",
            difficulty="hard",
            relevant_chunk_ids=(),
            expected_no_hits=True,
        ),
    )

    def scope_complete(_: str, user: str) -> dict[str, object]:
        question = json.loads(user)["question"]
        return {
            "label": "out_of_scope" if "주가" in question else "in_scope",
            "reason": "stub scope decision",
        }

    report = evaluate_answerability(
        cases,
        experiment="scope",
        scope_complete=scope_complete,
        evidence_complete=lambda _system, _user: {},
    )

    assert report.passed == 2
    assert report.positive_accept_rate == 1.0
    assert report.negative_reject_rate == 1.0
    assert "experiment=scope" in render_answerability_report(report)


def test_answerability_eval_requires_openai_key_for_live_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        openai_api_key = ""

    monkeypatch.setattr(
        "app.services.rag.official.evaluation.answerability.get_settings",
        lambda: _Settings(),
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        evaluate_answerability((), experiment="evidence")


def _chunk(chunk_id: str, text: str) -> RagChunk:
    return RagChunk(
        id=chunk_id,
        source_id="source",
        source_title="공식자료",
        source_category="standard_clause",
        publisher="테스트",
        text=text,
        page_start=1,
        page_end=1,
    )
