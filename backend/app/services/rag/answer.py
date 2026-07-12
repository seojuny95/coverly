"""Official-source RAG answer drafting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.services.llm import JsonCompleter, structured_completer
from app.services.rag.chunking import RagChunk
from app.services.rag.retrieve import RetrievalHit, infer_profile, retrieve

RagAnswerMode = Literal["term_explain", "claim_check", "general"]
RagAnswerStatus = Literal["answered", "no_evidence", "filtered"]

_MAX_CONTEXT_CHARS = 900
_OVERSTATED_CLAIM_TERMS = (
    "무조건 보상",
    "반드시 보상",
    "무조건 지급",
    "반드시 지급",
    "무조건 보험금",
    "반드시 보험금",
    "무조건 받을",
    "반드시 받을",
)
_POLICY_CONFIRMATION_NOTICE = "최종 지급 여부는 가입한 상품 약관과 보험사 심사로 확정돼요."


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

    This is intentionally independent from `/qa`; product routing is added only
    after retrieval and answer eval are stable.
    """
    normalized = question.strip()
    mode = _mode_for(normalized)
    selected_hits = (
        hits if hits is not None else retrieve(normalized, profile=mode, final_k=final_k)
    )
    if not normalized or not selected_hits:
        return _no_evidence(mode)

    completer = complete or structured_completer(_RagDraft)
    try:
        raw = completer(_system_prompt(mode), _user_prompt(normalized, selected_hits))
        draft = _RagDraft.model_validate(raw)
    except Exception:
        return _filtered(mode, selected_hits, missing_context=("답변 생성 실패",))

    citation_ids = _valid_citation_ids(draft.citation_ids, selected_hits)
    if not citation_ids:
        return _filtered(mode, selected_hits, missing_context=("유효한 근거 인용 없음",))

    answer = draft.answer.strip()
    if mode == "claim_check" and _contains_overstated_claim(answer):
        return _filtered(mode, selected_hits, missing_context=("근거 수준을 넘는 지급 단정",))

    limitations = [_standard_notice(mode)]
    if mode == "claim_check" and _POLICY_CONFIRMATION_NOTICE not in answer:
        answer = f"{answer}\n\n{_POLICY_CONFIRMATION_NOTICE}"
    return RagAnswer(
        status="answered",
        mode=mode,
        answer=answer,
        citations=tuple(
            _citation_by_id(citation_id, selected_hits) for citation_id in citation_ids
        ),
        limitations=tuple(limitations),
        missing_context=tuple(item.strip() for item in draft.missing_context if item.strip()),
    )


def _mode_for(question: str) -> RagAnswerMode:
    profile = infer_profile(question)
    if profile == "claim_check":
        return "claim_check"
    if profile == "term_explain":
        return "term_explain"
    return "general"


def _no_evidence(mode: RagAnswerMode) -> RagAnswer:
    return RagAnswer(
        status="no_evidence",
        mode=mode,
        answer="공식 자료에서 답변 근거를 찾지 못했습니다.",
        citations=(),
        limitations=("근거가 확인되지 않으면 답변하지 않습니다.",),
    )


def _filtered(
    mode: RagAnswerMode,
    hits: list[RetrievalHit],
    *,
    missing_context: tuple[str, ...],
) -> RagAnswer:
    return RagAnswer(
        status="filtered",
        mode=mode,
        answer="공식 자료 근거 안에서 안전하게 답변하지 못했습니다.",
        citations=tuple(_citation(hit.chunk) for hit in hits[:2]),
        limitations=("답변이 근거를 벗어나면 폐기합니다.",),
        missing_context=missing_context,
    )


def _system_prompt(mode: RagAnswerMode) -> str:
    base = (
        "당신은 사용자가 이미 가진 보험을 이해하도록 돕는 상담사입니다. "
        "제공된 공식자료 발췌문만 근거로 답하세요. "
        "근거에 없는 보험사, 상품명, 금액, 지급 조건을 만들지 마세요. "
        "특정 상품 가입·해지·증액을 권하지 마세요. "
        "citation_ids에는 실제로 사용한 발췌문 id만 넣으세요."
    )
    if mode == "claim_check":
        return (
            f"{base} 근거 발췌문에 지급사유·면책·금액·조건이 충분히 있으면 "
            "그 근거 범위 안에서 보상 여부, 면책 여부, 지급 여부, 금액을 말해도 됩니다. "
            "다만 근거가 표준약관이면 '표준약관 기준'이라고 밝히고, "
            "개별 상품 약관이나 사고·진단 사실이 부족하면 필요한 확인 항목을 함께 말하세요. "
            f"답변에는 반드시 '{_POLICY_CONFIRMATION_NOTICE}'와 같은 취지의 문장을 포함하세요."
        )
    return f"{base} 어려운 약관 용어는 쉬운 한국어로 풀어 설명하세요."


def _user_prompt(question: str, hits: list[RetrievalHit]) -> str:
    payload = {
        "question": question,
        "excerpts": [
            {
                "id": hit.chunk.id,
                "source_title": hit.chunk.source_title,
                "citation_label": hit.chunk.citation_label,
                "version": hit.chunk.version_label,
                "text": _trim(hit.chunk.text),
            }
            for hit in hits
        ],
        "output": {
            "answer": "사용자에게 보여줄 답변",
            "citation_ids": ["사용한 excerpt id"],
            "missing_context": ["개별 판단에 추가로 필요한 정보"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _trim(text: str) -> str:
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(compact) <= _MAX_CONTEXT_CHARS:
        return compact
    return compact[: _MAX_CONTEXT_CHARS - 1].rstrip() + "…"


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


def _contains_overstated_claim(answer: str) -> bool:
    return any(term in answer for term in _OVERSTATED_CLAIM_TERMS)


def _standard_notice(mode: RagAnswerMode) -> str:
    if mode == "claim_check":
        return "표준약관 기준의 일반 확인 안내입니다. 실제 상품 약관을 확인해야 합니다."
    return "공식자료 발췌문에 근거한 일반 설명입니다."
