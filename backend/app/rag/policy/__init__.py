"""RAG for short-lived user-uploaded insurance policies."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rag.policy.generation import PolicyGenerationResult
    from app.rag.policy.models import PolicyChunk, PolicyRetrievalHit

__all__ = [
    "PolicyChunk",
    "PolicyGenerationResult",
    "PolicyRetrievalHit",
    "index_policy_document",
    "generate_policy_answer",
    "retrieve_policy_context",
    "retrieve_policy_context_by_session_ids",
]

_EXPORT_MODULES = {
    "PolicyChunk": "app.rag.policy.models",
    "PolicyGenerationResult": "app.rag.policy.generation",
    "PolicyRetrievalHit": "app.rag.policy.models",
    "generate_policy_answer": "app.rag.policy.generation",
    "index_policy_document": "app.rag.policy.indexing",
    "retrieve_policy_context": "app.rag.policy.retrieval",
    "retrieve_policy_context_by_session_ids": "app.rag.policy.retrieval",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name), name)
