"""Retrieve uploaded-policy chunks within explicit session boundaries."""

from app.services.rag.embeddings import Embedder, openai_embedder_from_settings
from app.services.rag.policy.models import PolicyRetrievalHit
from app.services.rag.policy.store import PolicyRagStore, shared_policy_store
from app.services.rag.text import normalize_text


def retrieve_policy_context(
    session_ids: list[str],
    query: str,
    *,
    top_k: int = 4,
    candidate_k: int = 12,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
) -> list[PolicyRetrievalHit]:
    normalized = _normalize_query(query)
    if not session_ids or not normalized or top_k <= 0:
        return []
    active_embedder = embedder or openai_embedder_from_settings()
    query_embedding = active_embedder.embed_texts([normalized])[0]
    hits = (store or shared_policy_store()).query(
        session_ids,
        query_embedding,
        top_k=max(top_k, candidate_k),
    )
    return _dedupe_hits(hits)[:top_k]


def _normalize_query(query: str) -> str:
    normalized = " ".join(query.split())
    hints: list[str] = []
    if "보험기간" in normalized:
        hints.extend(["기본정보", "보험기간"])
    if "납입기간" in normalized or "납입주기" in normalized:
        hints.extend(["계약사항", "월납"])
    if "상해급수" in normalized or "몇 급" in normalized or "급수" in normalized:
        hints.extend(["가입정보", "상해급수"])
    metadata_terms = ("판매플랜", "운행차량", "이륜차부담보특약", "직업/직무")
    if any(term in normalized for term in metadata_terms):
        hints.append("가입정보")
    if not hints:
        return normalized
    return " ".join([normalized, *dict.fromkeys(hints)])


def _dedupe_hits(hits: list[PolicyRetrievalHit]) -> list[PolicyRetrievalHit]:
    deduped: list[PolicyRetrievalHit] = []
    seen: set[str] = set()
    for hit in hits:
        key = normalize_text(hit.chunk.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped
