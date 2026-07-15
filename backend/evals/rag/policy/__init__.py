"""Evaluation helpers for uploaded-policy RAG quality checks."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evals.rag.policy.generation import (
        PolicyGenerationEvalCase,
        PolicyGenerationEvalReport,
        PolicyGenerationEvalResult,
    )
    from evals.rag.policy.retrieval import (
        PolicyEvalCase,
        PolicyEvalCaseResult,
        PolicyEvalReport,
    )

__all__ = [
    "PolicyEvalCase",
    "PolicyEvalCaseResult",
    "PolicyEvalReport",
    "PolicyGenerationEvalCase",
    "PolicyGenerationEvalReport",
    "PolicyGenerationEvalResult",
    "evaluate_generation",
    "evaluate_policy_retrieval",
    "load_generation_eval_cases",
    "load_practice_eval_cases",
    "render_report",
]

_EXPORT_MODULES = {
    "PolicyEvalCase": "evals.rag.policy.retrieval",
    "PolicyEvalCaseResult": "evals.rag.policy.retrieval",
    "PolicyEvalReport": "evals.rag.policy.retrieval",
    "PolicyGenerationEvalCase": "evals.rag.policy.generation",
    "PolicyGenerationEvalReport": "evals.rag.policy.generation",
    "PolicyGenerationEvalResult": "evals.rag.policy.generation",
    "evaluate_generation": "evals.rag.policy.generation",
    "evaluate_policy_retrieval": "evals.rag.policy.retrieval",
    "load_generation_eval_cases": "evals.rag.policy.generation",
    "load_practice_eval_cases": "evals.rag.policy.generation",
    "render_report": "evals.rag.policy.generation",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name), name)
