"""Retrieve uploaded-policy chunks within explicit session boundaries."""

from app.services.rag.embeddings import Embedder, openai_embedder_from_settings
from app.services.rag.policy.models import PolicyRetrievalHit
from app.services.rag.policy.session_tokens import verified_policy_session_ids
from app.services.rag.policy.store import PolicyRagStore, shared_policy_store


def retrieve_policy_context(
    session_tokens: list[str],
    query: str,
    *,
    top_k: int = 4,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
) -> list[PolicyRetrievalHit]:
    normalized = " ".join(query.split())
    if not session_tokens or not normalized or top_k <= 0:
        return []
    session_ids = verified_policy_session_ids(session_tokens)
    if not session_ids:
        return []
    active_embedder = embedder or openai_embedder_from_settings()
    query_embedding = active_embedder.embed_texts([normalized])[0]
    return (store or shared_policy_store()).query(
        session_ids,
        query_embedding,
        top_k=top_k,
    )
