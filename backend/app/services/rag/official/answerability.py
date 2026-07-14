"""LLM-backed answerability checks for official-source RAG.

These checks intentionally make binary decisions through structured LLM output
instead of score thresholds or keyword-specific guards.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.llm import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.services.rag.official.models import RetrievalHit

_MAX_CONTEXT_CHARS = 700

ScopeLabel = Literal["in_scope", "out_of_scope"]
EvidenceLabel = Literal["answerable", "unanswerable"]


class QueryScopeDecision(BaseModel):
    label: ScopeLabel
    reason: str = Field(min_length=1, max_length=240)


class EvidenceSufficiencyDecision(BaseModel):
    label: EvidenceLabel
    supporting_citation_ids: list[str] = Field(default_factory=list, max_length=6)
    missing_context: list[str] = Field(default_factory=list, max_length=6)
    reason: str = Field(min_length=1, max_length=240)


def judge_query_scope(
    question: str,
    *,
    complete: JsonCompleter | None = None,
) -> QueryScopeDecision:
    """Decide whether a question belongs in official-source insurance RAG."""

    completer = complete or structured_completer(QueryScopeDecision)
    raw = completer(_scope_system_prompt(), _scope_user_prompt(question))
    return QueryScopeDecision.model_validate(raw)


def judge_evidence_sufficiency(
    question: str,
    hits: list[RetrievalHit],
    *,
    complete: JsonCompleter | None = None,
) -> EvidenceSufficiencyDecision:
    """Decide whether retrieved official excerpts can answer the question."""

    if not question.strip() or not hits:
        return EvidenceSufficiencyDecision(
            label="unanswerable",
            supporting_citation_ids=[],
            missing_context=["공식자료 근거"],
            reason="질문 또는 검색 근거가 비어 있습니다.",
        )

    completer = complete or structured_completer(EvidenceSufficiencyDecision)
    raw = completer(_evidence_system_prompt(), _evidence_user_prompt(question, hits))
    decision = EvidenceSufficiencyDecision.model_validate(raw)

    if decision.label == "answerable" and not _valid_supporting_ids(
        decision.supporting_citation_ids,
        hits,
    ):
        return EvidenceSufficiencyDecision(
            label="unanswerable",
            supporting_citation_ids=[],
            missing_context=["질문에 직접 답하는 공식자료 근거"],
            reason="답변 가능 판정에 유효한 supporting citation이 없습니다.",
        )

    if decision.label == "unanswerable":
        return EvidenceSufficiencyDecision(
            label="unanswerable",
            supporting_citation_ids=[],
            missing_context=decision.missing_context,
            reason=decision.reason,
        )

    return EvidenceSufficiencyDecision(
        label="answerable",
        supporting_citation_ids=_dedupe_supporting_ids(decision.supporting_citation_ids),
        missing_context=decision.missing_context,
        reason=decision.reason,
    )


def _scope_system_prompt() -> str:
    return (
        "너는 공식 보험 자료 RAG의 질문 라우터다. "
        "질문이 공식 보험 약관, 보험 법령, 보험 제도, 소비자 보호 자료, "
        "감독기관의 약관 개선·평가 자료로 일반적으로 답할 수 있으면 "
        "in_scope로 분류한다. "
        "특정 사용자의 권리 판단처럼 보여도, 질문이 공식자료의 일반 기준이나 "
        "금지·의무·절차를 묻는 형태면 in_scope다. "
        "보험회사나 감독기관이 해야 하는 조치, 지원 의무, 평가 방안, "
        "제도 개선 방향을 묻는 질문도 공식자료 일반 설명이면 in_scope다. "
        "실시간 정보, 뉴스, 주가, 예약/계정 처리, 사용자 개인 계약값처럼 "
        "공식자료만으로 답할 수 없으면 out_of_scope로 분류한다. "
        "보험과 관련된 표현이 있어도 개인 데이터, 현재 시점 확인, "
        "외부 서비스 실행이 필요하면 out_of_scope다."
    )


def _scope_user_prompt(question: str) -> str:
    return dump_prompt_json(
        {
            "question": question,
            "output": {
                "label": "in_scope 또는 out_of_scope",
                "reason": "짧은 판단 이유",
            },
        }
    )


def _evidence_system_prompt() -> str:
    return (
        "너는 공식 보험 자료 RAG의 근거 충분성 판정기다. "
        "질문에 직접 답하는 내용이 제공된 excerpt 안에 있을 때만 answerable로 분류한다. "
        "비슷한 보험 용어가 있어도 질문의 핵심을 직접 뒷받침하지 못하면 unanswerable이다. "
        "answerable이면 반드시 실제 excerpt id만 supporting_citation_ids에 넣는다. "
        "없는 사실, 개인 계약값, 실시간 정보, 외부 서비스 처리는 추정하지 않는다."
    )


def _evidence_user_prompt(question: str, hits: list[RetrievalHit]) -> str:
    return dump_prompt_json(
        {
            "question": question,
            "excerpts": [
                {
                    "id": hit.chunk.id,
                    "source_title": hit.chunk.source_title,
                    "citation_label": hit.chunk.citation_label,
                    "text": compact_prompt_text(hit.chunk.text, _MAX_CONTEXT_CHARS),
                }
                for hit in hits
            ],
            "output": {
                "label": "answerable 또는 unanswerable",
                "supporting_citation_ids": ["직접 근거가 되는 excerpt id"],
                "missing_context": ["답변에 부족한 근거"],
                "reason": "짧은 판단 이유",
            },
        }
    )


def _valid_supporting_ids(ids: list[str], hits: list[RetrievalHit]) -> bool:
    available = {hit.chunk.id for hit in hits}
    return bool(ids) and all(chunk_id in available for chunk_id in ids)


def _dedupe_supporting_ids(ids: list[str]) -> list[str]:
    valid: list[str] = []
    for chunk_id in ids:
        if chunk_id not in valid:
            valid.append(chunk_id)
    return valid
