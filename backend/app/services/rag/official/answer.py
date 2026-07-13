"""Answer pipeline for official-source RAG.

The answer flow stays intentionally small:

1. retrieve context
2. build one grounded prompt
3. ask the LLM for JSON
4. keep the answer only when it cites retrieved chunks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.services.llm import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.services.rag.official.models import RagChunk, RetrievalHit
from app.services.rag.official.retrieval import retrieve

# answer_official_question always returns "general" now that profile-based mode
# classification was removed. "term_explain"/"claim_check" stay in the type
# because portfolio_qa.py and its tests still branch on them for RagAnswer
# values built outside this module; simplifying the type would break that
# contract without actually removing the dead branch it feeds.
RagAnswerMode = Literal["term_explain", "claim_check", "general"]
RagAnswerStatus = Literal["answered", "no_evidence", "filtered"]

_MAX_CONTEXT_CHARS = 900


@dataclass(frozen=True)
class RagCitation:
    chunk_id: str
    source_id: str
    source_title: str
    source_category: str
    publisher: str
    citation_label: str
    page_start: int
    page_end: int
    version_label: str | None
    source_url: str | None


@dataclass(frozen=True)
class RagAnswer:
    status: RagAnswerStatus
    mode: RagAnswerMode
    answer: str
    citations: tuple[RagCitation, ...]
    limitations: tuple[str, ...]
    missing_context: tuple[str, ...] = ()


class _RagDraft(BaseModel):
    answer: str = Field(min_length=1, max_length=900)
    citation_ids: list[str] = Field(default_factory=list, max_length=6)
    missing_context: list[str] = Field(default_factory=list, max_length=6)


def answer_official_question(
    question: str,
    *,
    complete: JsonCompleter | None = None,
    hits: list[RetrievalHit] | None = None,
    final_k: int = 5,
) -> RagAnswer:
    """Draft an answer from official sources only.

    The caller may pass pre-retrieved hits for tests or upstream routing.
    """

    normalized = question.strip()
    selected_hits = hits if hits is not None else retrieve(normalized, final_k=final_k)

    if not normalized or not selected_hits:
        return _no_evidence()

    completer = complete or structured_completer(_RagDraft)

    try:
        raw = completer(_system_prompt(), _user_prompt(normalized, selected_hits))
        draft = _RagDraft.model_validate(raw)
    except Exception:
        return _filtered(selected_hits, missing_context=("답변 생성 실패",))

    citation_ids = _valid_citation_ids(draft.citation_ids, selected_hits)
    if not citation_ids:
        return _filtered(selected_hits, missing_context=("유효한 근거 인용 없음",))

    answer = draft.answer.strip()

    return RagAnswer(
        status="answered",
        mode="general",
        answer=answer,
        citations=tuple(
            _citation_by_id(citation_id, selected_hits) for citation_id in citation_ids
        ),
        limitations=("공식자료 발췌문에 근거한 일반 설명입니다.",),
        missing_context=tuple(item.strip() for item in draft.missing_context if item.strip()),
    )


def _no_evidence() -> RagAnswer:
    return RagAnswer(
        status="no_evidence",
        mode="general",
        answer="공식 자료에서 답변 근거를 찾지 못했습니다.",
        citations=(),
        limitations=("근거가 확인되지 않으면 답변하지 않습니다.",),
    )


def _filtered(
    hits: list[RetrievalHit],
    *,
    missing_context: tuple[str, ...],
) -> RagAnswer:
    return RagAnswer(
        status="filtered",
        mode="general",
        answer="공식 자료 근거 안에서 안전하게 답변하지 못했습니다.",
        citations=tuple(_citation(hit.chunk) for hit in hits[:2]),
        limitations=("답변이 근거를 벗어나면 폐기합니다.",),
        missing_context=missing_context,
    )


def _system_prompt() -> str:
    return (
        "당신은 사용자가 이미 가진 보험을 이해하도록 돕는 상담사입니다. "
        "제공된 공식자료 발췌문만 근거로 답하세요. "
        "근거에 없는 보험사, 상품명, 금액, 지급 조건을 만들지 마세요. "
        "특정 상품 가입·해지·증액을 권하지 마세요. "
        "어려운 약관 용어는 쉬운 한국어로 설명하세요. "
        "citation_ids에는 실제로 사용한 발췌문 id만 넣으세요. "
        "공식자료만으로 부족한 내용은 missing_context에 적으세요."
    )


def _user_prompt(question: str, hits: list[RetrievalHit]) -> str:
    payload = {
        "question": question,
        "excerpts": [
            {
                "id": hit.chunk.id,
                "source_title": hit.chunk.source_title,
                "citation_label": hit.chunk.citation_label,
                "version": hit.chunk.version_label,
                "text": compact_prompt_text(hit.chunk.text, _MAX_CONTEXT_CHARS),
            }
            for hit in hits
        ],
        "output": {
            "answer": "사용자에게 보여줄 답변",
            "citation_ids": ["사용한 excerpt id"],
            "missing_context": ["개별 판단에 추가로 필요한 정보"],
        },
    }
    return dump_prompt_json(payload)


def _valid_citation_ids(ids: list[str], hits: list[RetrievalHit]) -> list[str]:
    available = {hit.chunk.id for hit in hits}
    valid: list[str] = []
    for citation_id in ids:
        if citation_id in available and citation_id not in valid:
            valid.append(citation_id)
    return valid


def _citation_by_id(chunk_id: str, hits: list[RetrievalHit]) -> RagCitation:
    for hit in hits:
        if hit.chunk.id == chunk_id:
            return _citation(hit.chunk)
    raise ValueError(f"unknown citation id: {chunk_id}")


def _citation(chunk: RagChunk) -> RagCitation:
    return RagCitation(
        chunk_id=chunk.id,
        source_id=chunk.source_id,
        source_title=chunk.source_title,
        source_category=chunk.source_category,
        publisher=chunk.publisher,
        citation_label=chunk.citation_label or chunk.source_title,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        version_label=chunk.version_label,
        source_url=chunk.source_url,
    )
