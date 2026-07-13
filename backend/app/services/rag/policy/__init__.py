"""RAG for short-lived user-uploaded insurance policies."""

from app.services.rag.policy.indexing import index_policy_document
from app.services.rag.policy.models import PolicyChunk, PolicyRetrievalHit
from app.services.rag.policy.retrieval import retrieve_policy_context
from app.services.rag.policy.store import shared_policy_store


def delete_policy_session(session_id: str) -> None:
    shared_policy_store().delete(session_id)


__all__ = [
    "PolicyChunk",
    "PolicyRetrievalHit",
    "delete_policy_session",
    "index_policy_document",
    "retrieve_policy_context",
]
