"""Evaluation helpers for uploaded-policy RAG quality checks."""

from typing import TYPE_CHECKING, Any

from app.services.rag.policy.evaluation.retrieval import (
    PolicyEvalCase,
    PolicyEvalCaseResult,
    PolicyEvalReport,
    evaluate_policy_retrieval,
)

if TYPE_CHECKING:
    from app.services.rag.policy.evaluation.generation import (
        PolicyGenerationEvalCase,
        PolicyGenerationEvalReport,
        PolicyGenerationEvalResult,
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

_GENERATION_EXPORTS = {
    "PolicyGenerationEvalCase",
    "PolicyGenerationEvalReport",
    "PolicyGenerationEvalResult",
    "evaluate_generation",
    "load_generation_eval_cases",
    "load_practice_eval_cases",
    "render_report",
}


def __getattr__(name: str) -> Any:
    if name not in _GENERATION_EXPORTS:
        raise AttributeError(name)

    from app.services.rag.policy.evaluation import generation

    return getattr(generation, name)
