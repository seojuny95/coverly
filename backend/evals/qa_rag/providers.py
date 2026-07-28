"""RAG providers injected into the real 상담 Agent during evaluation."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.modules.qa.context import QaContext
from app.rag.embeddings import HashingEmbedder
from app.rag.official.evidence import OfficialEvidenceResult, search_official_evidence
from app.rag.official.loaders import load_official_chunks
from app.rag.official.retrieval import retrieve as retrieve_official
from app.rag.policy.evidence import PolicyEvidenceResult, search_policy_evidence
from app.rag.policy.retrieval import retrieve_policy_context_by_session_ids
from evals.rag.execution import RetrievalMode
from evals.rag.policy.retrieval import (
    OfflinePolicyRetrievalContext,
    policy_retrieval_eval_context,
)


@dataclass
class RagExecutionStats:
    official_retrieval_calls: int = 0
    policy_retrieval_calls: int = 0
    official_elapsed_seconds: float = 0.0
    policy_elapsed_seconds: float = 0.0

    def as_dict(self, *, retrieval_mode: RetrievalMode) -> dict[str, int | float | str]:
        return {
            "official_retrieval_calls": self.official_retrieval_calls,
            "policy_retrieval_calls": self.policy_retrieval_calls,
            "official_elapsed_seconds": round(self.official_elapsed_seconds, 3),
            "policy_elapsed_seconds": round(self.policy_elapsed_seconds, 3),
            "official_answer_generation": "disabled",
            "policy_answer_generation": "disabled",
            "official_semantic_rerank": (
                "disabled" if retrieval_mode == "offline" else "enabled_not_counted"
            ),
        }


class RagProviders:
    """Bind the selected retrieval mode to the Agent's injectable RAG seams."""

    def __init__(
        self,
        *,
        mode: RetrievalMode,
        policy_context: OfflinePolicyRetrievalContext,
    ) -> None:
        self._mode = mode
        self._policy_context = policy_context
        self._official_chunks = load_official_chunks() if mode == "offline" else None
        self._official_embedder = HashingEmbedder() if mode == "offline" else None
        self.stats = RagExecutionStats()

    def configure_context(self, context: QaContext) -> None:
        context.official_evidence_retriever = self.retrieve_official
        context.policy_evidence_retriever = self.retrieve_policy

    def retrieve_official(self, question: str) -> OfficialEvidenceResult:
        started = time.perf_counter()
        self.stats.official_retrieval_calls += 1
        try:
            if self._mode == "production":
                return search_official_evidence(question)

            hits = retrieve_official(
                question,
                chunks=self._official_chunks,
                embedder=self._official_embedder,
                final_k=5,
            )
            return search_official_evidence(question, hits=hits)
        finally:
            self.stats.official_elapsed_seconds += time.perf_counter() - started

    def retrieve_policy(
        self,
        session_ids: tuple[str, ...],
        question: str,
        scope_question: str,
    ) -> PolicyEvidenceResult:
        started = time.perf_counter()
        self.stats.policy_retrieval_calls += 1
        try:
            mapped_session_ids = self._policy_context.map_session_ids(session_ids)
            hits = retrieve_policy_context_by_session_ids(
                list(mapped_session_ids),
                question,
                store=self._policy_context.store,
                embedder=self._policy_context.embedder,
            )
            return search_policy_evidence(
                tuple(mapped_session_ids),
                question,
                scope_question=scope_question,
                hits=hits,
            )
        finally:
            self.stats.policy_elapsed_seconds += time.perf_counter() - started


@contextmanager
def rag_provider_context(
    *,
    mode: RetrievalMode,
    policy_dataset_path: Path,
) -> Iterator[RagProviders]:
    """Create isolated Policy storage and matching Official retrieval providers."""

    with policy_retrieval_eval_context(
        mode=mode,
        path=policy_dataset_path,
    ) as policy_context:
        yield RagProviders(mode=mode, policy_context=policy_context)
