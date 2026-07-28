"""Citation-ready evidence returned by Official RAG without answer generation."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.rag.official.models import RetrievalHit
from app.rag.official.retrieval import retrieve

_MAX_EXCERPT_CHARS = 900
_DEFAULT_FINAL_K = 5


class OfficialEvidence(BaseModel):
    """One official excerpt the 상담 Agent may cite and explain."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    excerpt: str
    source_id: str
    source_title: str
    source_category: str
    publisher: str
    citation_label: str
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    version_label: str | None = None
    source_url: str | None = None


class OfficialEvidenceResult(BaseModel):
    """Search result with evidence, provenance, and its usage boundary."""

    model_config = ConfigDict(frozen=True)

    matched: bool
    evidence: tuple[OfficialEvidence, ...] = ()
    limitations: tuple[str, ...] = ()


def search_official_evidence(
    question: str,
    *,
    hits: Sequence[RetrievalHit] | None = None,
    final_k: int = _DEFAULT_FINAL_K,
) -> OfficialEvidenceResult:
    """Return retrieved official excerpts without asking an LLM to answer."""

    normalized = " ".join(question.split())
    if not normalized:
        return _no_evidence()

    selected_hits = (
        list(hits)[:final_k] if hits is not None else retrieve(normalized, final_k=final_k)
    )
    if not selected_hits:
        return _no_evidence()

    return OfficialEvidenceResult(
        matched=True,
        evidence=tuple(_evidence_from_hit(hit) for hit in selected_hits),
        limitations=(
            "공식 자료의 검색 발췌문이며 개별 계약의 확정 조건이 아닙니다.",
            "발췌문에 없는 내용은 일반 지식으로 보충하지 말고 확인 불가로 안내해야 합니다.",
        ),
    )


def _evidence_from_hit(hit: RetrievalHit) -> OfficialEvidence:
    chunk = hit.chunk
    return OfficialEvidence(
        chunk_id=chunk.id,
        excerpt=_compact_excerpt(chunk.text),
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


def _compact_excerpt(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _MAX_EXCERPT_CHARS:
        return compact
    return f"{compact[:_MAX_EXCERPT_CHARS].rstrip()}…"


def _no_evidence() -> OfficialEvidenceResult:
    return OfficialEvidenceResult(
        matched=False,
        limitations=("공식 자료에서 질문과 관련된 근거를 찾지 못했습니다.",),
    )
