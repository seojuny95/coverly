"""Evidence returned by Policy RAG without answer generation."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.rag.embeddings import Embedder
from app.rag.policy.boundaries import (
    requires_unavailable_policy_context,
    safe_policy_evidence_fact,
)
from app.rag.policy.models import PolicyContentType, PolicyRetrievalHit
from app.rag.policy.retrieval import retrieve_policy_context_by_session_ids
from app.rag.policy.store import PolicyRagStore

_MAX_EXCERPT_CHARS = 1_200
_DEFAULT_TOP_K = 4


class PolicyTermEvidence(BaseModel):
    """One uploaded-policy excerpt the 상담 Agent may explain."""

    model_config = ConfigDict(frozen=True)

    document_ref: str
    excerpt: str
    content_type: PolicyContentType
    chunk_index: int = Field(ge=0)


class PolicyEvidenceResult(BaseModel):
    """Policy search result with evidence and its usage boundary."""

    model_config = ConfigDict(frozen=True)

    has_retrieved_evidence: bool
    supports_exhaustive_answer: bool = False
    requires_disclosure_links: bool = False
    evidence: tuple[PolicyTermEvidence, ...] = ()
    limitations: tuple[str, ...] = ()


def search_policy_evidence(
    session_ids: tuple[str, ...],
    question: str,
    *,
    scope_question: str | None = None,
    hits: Sequence[PolicyRetrievalHit] | None = None,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> PolicyEvidenceResult:
    """Return uploaded-policy excerpts without asking an LLM to answer."""

    normalized = " ".join(question.split())
    normalized_scope = " ".join((scope_question or question).split())
    if not session_ids or not normalized:
        return _no_evidence("증권 원문이 아직 색인되지 않았거나 업로드되지 않았습니다.")

    selected_hits = (
        list(hits)
        if hits is not None
        else retrieve_policy_context_by_session_ids(
            list(session_ids),
            normalized,
            top_k=top_k,
            store=store,
            embedder=embedder,
        )
    )
    allowed_session_ids = set(session_ids)
    selected_hits = [hit for hit in selected_hits if hit.chunk.session_id in allowed_session_ids][
        :top_k
    ]
    safe_hits = [(hit, safe_policy_evidence_fact(hit.chunk.text)) for hit in selected_hits]
    safe_hits = [(hit, fact) for hit, fact in safe_hits if fact]
    if not safe_hits:
        return _no_evidence("증권 원문에서 질문과 관련된 근거를 찾지 못했습니다.")

    if requires_unavailable_policy_context(
        normalized_scope,
        [fact for _, fact in safe_hits],
    ):
        return _no_evidence("증권 원문만으로 확정할 수 없는 질문입니다.")

    document_refs = {
        session_id: f"document-{index}" for index, session_id in enumerate(session_ids, start=1)
    }
    evidence: list[PolicyTermEvidence] = []
    for hit, fact in safe_hits:
        document_ref = hit.document_ref or document_refs[hit.chunk.session_id]
        evidence.append(_evidence_from_hit(hit, fact, document_ref=document_ref))

    return PolicyEvidenceResult(
        has_retrieved_evidence=True,
        evidence=tuple(evidence),
        limitations=(
            "업로드된 증권 원문의 검색 발췌문이며 상세 약관 전체를 대신하지 않습니다.",
            "발췌문에 없는 조건이나 지급 가능성은 추정하지 않아야 합니다.",
        ),
    )


def _evidence_from_hit(
    hit: PolicyRetrievalHit,
    fact: str,
    *,
    document_ref: str,
) -> PolicyTermEvidence:
    chunk = hit.chunk
    return PolicyTermEvidence(
        document_ref=document_ref,
        excerpt=_compact_excerpt(fact),
        content_type=chunk.content_type,
        chunk_index=chunk.chunk_index,
    )


def _compact_excerpt(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _MAX_EXCERPT_CHARS:
        return compact
    return f"{compact[:_MAX_EXCERPT_CHARS].rstrip()}…"


def _no_evidence(limitation: str) -> PolicyEvidenceResult:
    return PolicyEvidenceResult(
        has_retrieved_evidence=False,
        requires_disclosure_links=True,
        limitations=(limitation,),
    )
