"""Evaluation helpers for official-source RAG quality checks."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evals.rag.official.generation import (
        GenerationEvalCase,
        GenerationEvalReport,
        GenerationEvalResult,
    )
    from evals.rag.official.retrieval import (
        RetrievalEvalCase,
        RetrievalEvalReport,
        RetrievalEvalResult,
    )

__all__ = [
    "GenerationEvalCase",
    "GenerationEvalReport",
    "GenerationEvalResult",
    "RetrievalEvalCase",
    "RetrievalEvalReport",
    "RetrievalEvalResult",
    "evaluate_generation",
    "evaluate_retrieval",
    "load_generation_eval_cases",
    "load_retrieval_eval_cases",
    "render_report",
]

_EXPORT_MODULES = {
    "GenerationEvalCase": "evals.rag.official.generation",
    "GenerationEvalReport": "evals.rag.official.generation",
    "GenerationEvalResult": "evals.rag.official.generation",
    "RetrievalEvalCase": "evals.rag.official.retrieval",
    "RetrievalEvalReport": "evals.rag.official.retrieval",
    "RetrievalEvalResult": "evals.rag.official.retrieval",
    "evaluate_generation": "evals.rag.official.generation",
    "evaluate_retrieval": "evals.rag.official.retrieval",
    "load_generation_eval_cases": "evals.rag.official.generation",
    "load_retrieval_eval_cases": "evals.rag.official.retrieval",
    "render_report": "evals.rag.official.generation",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name), name)
