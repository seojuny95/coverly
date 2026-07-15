"""Answer pipeline for official-source RAG.

The answer flow stays intentionally small:

1. retrieve context
2. build one grounded prompt
3. ask the LLM for JSON
4. keep the answer only when it cites retrieved chunks
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.prompts import load_prompt
from app.integrations.openai import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.rag.official.models import RagChunk, RetrievalHit
from app.rag.official.retrieval import retrieve

# answer_official_question always returns "general" now that profile-based mode
# classification was removed. "term_explain"/"claim_check" stay in the type
# because portfolio_qa.py and its tests still branch on them for RagAnswer
# values built outside this module; simplifying the type would break that
# contract without actually removing the dead branch it feeds.
RagAnswerMode = Literal["term_explain", "claim_check", "general"]
RagAnswerStatus = Literal["answered", "no_evidence", "filtered"]

_MAX_CONTEXT_CHARS = 900
_PROMPT_PATH = Path(__file__).with_name("rag_answer_prompt.md")
_GENERIC_MISSING_CONTEXT = (
    "개별 판단에 추가로 필요한 정보",
    "개별 판단에 필요한 정보",
    "추가 정보",
    "구체적인 정보",
    "자세한 정보",
    "질문에 필요한 구체 확인 항목",
)


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
    if not normalized:
        return _no_evidence()

    selected_hits = hits if hits is not None else retrieve(normalized, final_k=final_k)

    if not selected_hits:
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
        missing_context=_missing_context(draft.missing_context),
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
    return load_prompt(_PROMPT_PATH)


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
            "missing_context": ["질문에 필요한 구체 확인 항목"],
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


def _missing_context(items: list[str]) -> tuple[str, ...]:
    cleaned = [_normalize_missing_context(item) for item in items]
    concrete = [item for item in cleaned if item and not _is_generic_missing_context(item)]

    return tuple(dict.fromkeys(concrete))


def _normalize_missing_context(item: str) -> str:
    return " ".join(item.strip().split())


def _is_generic_missing_context(item: str) -> bool:
    return any(generic in item for generic in _GENERIC_MISSING_CONTEXT)


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
