"""Evaluation helpers for official-source RAG quality checks."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evals.rag.official.e2e import (
        OfficialRagE2EReport,
        OfficialRagE2EResult,
    )
    from evals.rag.official.extraction import (
        ExtractionEvalCase,
        ExtractionEvalReport,
        ExtractionEvalResult,
    )
    from evals.rag.official.generation import (
        GenerationEvalCase,
        GenerationEvalReport,
        GenerationEvalResult,
    )
    from evals.rag.official.retrieval import (
        AcceptedEvidence,
        RetrievalEvalCase,
        RetrievalEvalReport,
        RetrievalEvalResult,
    )

__all__ = [
    "ExtractionEvalCase",
    "ExtractionEvalReport",
    "ExtractionEvalResult",
    "OfficialRagE2EReport",
    "OfficialRagE2EResult",
    "GenerationEvalCase",
    "GenerationEvalReport",
    "GenerationEvalResult",
    "AcceptedEvidence",
    "RetrievalEvalCase",
    "RetrievalEvalReport",
    "RetrievalEvalResult",
    "evaluate_e2e",
    "evaluate_extraction",
    "evaluate_generation",
    "evaluate_retrieval",
    "load_extraction_eval_cases",
    "load_e2e_eval_cases",
    "load_generation_eval_cases",
    "load_retrieval_eval_cases",
    "render_extraction_report",
    "render_report",
]

_EXPORT_MODULES = {
    "ExtractionEvalCase": "evals.rag.official.extraction",
    "ExtractionEvalReport": "evals.rag.official.extraction",
    "ExtractionEvalResult": "evals.rag.official.extraction",
    "OfficialRagE2EReport": "evals.rag.official.e2e",
    "OfficialRagE2EResult": "evals.rag.official.e2e",
    "GenerationEvalCase": "evals.rag.official.generation",
    "GenerationEvalReport": "evals.rag.official.generation",
    "GenerationEvalResult": "evals.rag.official.generation",
    "AcceptedEvidence": "evals.rag.official.retrieval",
    "RetrievalEvalCase": "evals.rag.official.retrieval",
    "RetrievalEvalReport": "evals.rag.official.retrieval",
    "RetrievalEvalResult": "evals.rag.official.retrieval",
    "evaluate_e2e": "evals.rag.official.e2e",
    "evaluate_extraction": "evals.rag.official.extraction",
    "evaluate_generation": "evals.rag.official.generation",
    "evaluate_retrieval": "evals.rag.official.retrieval",
    "load_extraction_eval_cases": "evals.rag.official.extraction",
    "load_e2e_eval_cases": "evals.rag.official.e2e",
    "load_generation_eval_cases": "evals.rag.official.generation",
    "render_extraction_report": "evals.rag.official.extraction",
    "load_retrieval_eval_cases": "evals.rag.official.retrieval",
    "render_report": "evals.rag.official.generation",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name), name)
