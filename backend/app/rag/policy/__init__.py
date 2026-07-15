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
    "delete_policy_session",
    "index_policy_document",
    "generate_policy_answer",
    "refresh_policy_session",
    "retrieve_policy_context",
]

_EXPORT_MODULES = {
    "PolicyChunk": "app.rag.policy.models",
    "PolicyGenerationResult": "app.rag.policy.generation",
    "PolicyRetrievalHit": "app.rag.policy.models",
    "delete_policy_session": "app.rag.policy.sessions",
    "generate_policy_answer": "app.rag.policy.generation",
    "index_policy_document": "app.rag.policy.indexing",
    "refresh_policy_session": "app.rag.policy.sessions",
    "retrieve_policy_context": "app.rag.policy.retrieval",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name), name)
