"""Retrieve uploaded-policy chunks within explicit session boundaries."""

from app.services.rag.embeddings import Embedder, openai_embedder_from_settings
from app.services.rag.policy.models import PolicyRetrievalHit
from app.services.rag.policy.session_tokens import verified_policy_session_ids
from app.services.rag.policy.store import PolicyRagStore, shared_policy_store
from app.services.rag.text import normalize_text


def retrieve_policy_context(
    session_tokens: list[str],
    query: str,
    *,
    top_k: int = 4,
    candidate_k: int = 12,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
) -> list[PolicyRetrievalHit]:
    normalized = _normalize_query(query)
    if not session_tokens or not normalized or top_k <= 0:
        return []
    session_ids = verified_policy_session_ids(session_tokens)
    if not session_ids:
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
    return " ".join(query.split())


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
