"""Retrieval pipeline for official-source RAG.

The production path is intentionally small:

1. normalize the user question
2. embed the normalized query
3. run pgvector hybrid search
4. return the top chunks

Diagnostics and tests may pass explicit chunks with their own embedder. That
path builds temporary records in process, but production retrieval always
goes through pgvector — this module has no test-only defaults of its own.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable

from app.core.config import get_settings
from app.integrations.postgres.official_rag_store import shared_pgvector_store
from app.rag.embeddings import Embedder, openai_embedder_from_settings
from app.rag.official.models import (
    QueryPlan,
    RagChunk,
    RetrievalHit,
    VectorRecord,
    chunk_embedding_text,
)
from app.rag.official.store import OfficialRagStore

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_RRF_K = 20


def retrieve(
    query: str,
    *,
    chunks: tuple[RagChunk, ...] | None = None,
    embedder: Embedder | None = None,
    candidate_k: int = 120,
    final_k: int = 6,
    vector_weight: float = 0.40,
    bm25_weight: float = 0.60,
    store: OfficialRagStore | None = None,
) -> list[RetrievalHit]:
    """Retrieve official-source chunks with plain hybrid search.

    ``chunks`` is for tests, evaluation, and diagnostics — they build records
    in process instead of going through pgvector. Callers on that path must
    pass ``embedder`` themselves (an offline ``HashingEmbedder`` for fast,
    deterministic checks, or the real OpenAI embedder to also measure
    embedding quality against a chunk sample). This module does not default
    to either, so it stays free of test-only concerns.
    """

    plan = transform_query(query)
    if not plan.search_query:
        return []

    if chunks is None:
        return _retrieve_from_pgvector(
            plan,
            candidate_k=candidate_k,
            final_k=final_k,
            store=store,
        )

    if embedder is None:
        raise ValueError("embedder is required when chunks is provided")

    records = _records_from_chunks(chunks, embedder=embedder)
    if not records:
        return []

    hits = _retrieve_from_records(
        plan,
        records,
        embedder=embedder,
        top_k=candidate_k,
        vector_weight=vector_weight,
        bm25_weight=bm25_weight,
    )
    return _rerank_with_rrf(plan, hits, top_k=candidate_k)[:final_k]


def transform_query(query: str) -> QueryPlan:
    """Return the normalized search query without domain-specific expansion."""

    normalized = " ".join(query.strip().split())
    return QueryPlan(
        original_query=query,
        search_query=normalized,
        terms=_tokens(normalized),
    )


def _retrieve_from_pgvector(
    plan: QueryPlan,
    *,
    candidate_k: int,
    final_k: int,
    store: OfficialRagStore | None,
) -> list[RetrievalHit]:
    if not get_settings().database_url:
        raise RuntimeError("DATABASE_URL is required for RAG retrieval")

    query_embedding = openai_embedder_from_settings().embed_query(plan.search_query)
    hits = (store or shared_pgvector_store()).query(
        query_embedding=query_embedding,
        query_text=plan.search_query,
        top_k=max(candidate_k, final_k),
    )
    return _rerank_with_rrf(plan, hits, top_k=candidate_k)[:final_k]


def _retrieve_from_records(
    plan: QueryPlan,
    records: tuple[VectorRecord, ...],
    *,
    embedder: Embedder,
    top_k: int,
    vector_weight: float,
    bm25_weight: float,
) -> list[RetrievalHit]:
    query_embedding = embedder.embed_texts([plan.search_query])[0]
    bm25 = _Bm25(records)

    vector_scores = {
        record.chunk.id: _cosine(query_embedding, record.embedding) for record in records
    }
    keyword_scores = {record.chunk.id: bm25.score(record, plan.terms) for record in records}

    normalized_vectors = _normalize_scores(vector_scores)
    normalized_keywords = _normalize_scores(keyword_scores)

    hits = [
        RetrievalHit(
            chunk=record.chunk,
            score=(
                normalized_vectors[record.chunk.id] * vector_weight
                + normalized_keywords[record.chunk.id] * bm25_weight
            ),
            keyword_score=keyword_scores[record.chunk.id],
            vector_score=vector_scores[record.chunk.id],
        )
        for record in records
        if vector_scores[record.chunk.id] > 0 or keyword_scores[record.chunk.id] > 0
    ]

    hits.sort(
        key=lambda hit: (
            -hit.score,
            -hit.keyword_score,
            -hit.vector_score,
            hit.chunk.source_id,
            hit.chunk.page_start,
            hit.chunk.id,
        )
    )
    return hits[:top_k]


def _records_from_chunks(
    chunks: tuple[RagChunk, ...], *, embedder: Embedder
) -> tuple[VectorRecord, ...]:
    embeddings = embedder.embed_texts([chunk_embedding_text(chunk) for chunk in chunks])

    return tuple(
        VectorRecord(chunk=chunk, embedding=embedding)
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    )


def _tokens(text: str) -> tuple[str, ...]:
    tokens = [token.casefold() for token in _TOKEN_RE.findall(text) if token.strip()]
    for token in tuple(tokens):
        if any("가" <= char <= "힣" for char in token):
            tokens.extend(_char_ngrams(token))
    return tuple(dict.fromkeys(tokens))


def _char_ngrams(text: str) -> tuple[str, ...]:
    if len(text) < 2:
        return ()
    ngrams: list[str] = []
    for size in (2, 3, 4):
        if len(text) < size:
            continue
        ngrams.extend(text[index : index + size] for index in range(len(text) - size + 1))
    return tuple(ngrams)


def _rerank_with_rrf(
    plan: QueryPlan, hits: list[RetrievalHit], *, top_k: int
) -> list[RetrievalHit]:
    if not hits:
        return []

    bm25 = _Bm25.from_chunks(tuple(hit.chunk for hit in hits))
    keyword_scores = {hit.chunk.id: bm25.score_chunk(hit.chunk, plan.terms) for hit in hits}
    vector_ranks = _rank_positions(
        hits,
        key=lambda hit: (
            -hit.vector_score,
            -hit.score,
            hit.chunk.source_id,
            hit.chunk.page_start,
            hit.chunk.id,
        ),
    )
    keyword_ranks = _rank_positions(
        hits,
        key=lambda hit: (
            -keyword_scores[hit.chunk.id],
            -hit.vector_score,
            hit.chunk.source_id,
            hit.chunk.page_start,
            hit.chunk.id,
        ),
    )

    ranked_hits = sorted(
        hits,
        key=lambda hit: (
            -_rrf_score(vector_ranks[hit.chunk.id], keyword_ranks[hit.chunk.id]),
            -hit.vector_score,
            -keyword_scores[hit.chunk.id],
            hit.chunk.source_id,
            hit.chunk.page_start,
            hit.chunk.id,
        ),
    )
    return [
        RetrievalHit(
            chunk=hit.chunk,
            score=_rrf_score(vector_ranks[hit.chunk.id], keyword_ranks[hit.chunk.id]),
            keyword_score=keyword_scores[hit.chunk.id],
            vector_score=hit.vector_score,
        )
        for hit in ranked_hits[:top_k]
    ]


def _rank_positions(
    hits: list[RetrievalHit],
    *,
    key: Callable[[RetrievalHit], tuple[float | str | int, ...]],
) -> dict[str, int]:
    ordered = sorted(hits, key=key)
    return {hit.chunk.id: rank for rank, hit in enumerate(ordered, start=1)}


def _rrf_score(*ranks: int, k: int = _RRF_K) -> float:
    return sum(1 / (k + rank) for rank in ranks)


class _Bm25:
    @classmethod
    def from_chunks(cls, chunks: tuple[RagChunk, ...]) -> _Bm25:
        return cls(tuple(VectorRecord(chunk=chunk, embedding=()) for chunk in chunks))

    def __init__(self, records: tuple[VectorRecord, ...]) -> None:
        self._documents = {
            record.chunk.id: _tokens(chunk_embedding_text(record.chunk)) for record in records
        }
        self._doc_count = len(records)
        self._avgdl = self._average_document_length()
        self._doc_freqs = self._document_frequencies(self._documents)

    def score(self, record: VectorRecord, terms: tuple[str, ...]) -> float:
        return self.score_chunk(record.chunk, terms)

    def score_chunk(self, chunk: RagChunk, terms: tuple[str, ...]) -> float:
        tokens = self._documents[chunk.id]
        if not tokens or self._avgdl == 0:
            return 0.0

        counts = Counter(tokens)
        score = 0.0

        for term in terms:
            term_freq = counts[term.casefold()]
            if term_freq <= 0:
                continue

            doc_freq = self._doc_freqs.get(term.casefold(), 0)
            score += self._score_term(term_freq, doc_freq, len(tokens))

        return score

    def _average_document_length(self) -> float:
        if not self._doc_count:
            return 0.0

        return sum(len(tokens) for tokens in self._documents.values()) / self._doc_count

    @staticmethod
    def _document_frequencies(documents: dict[str, tuple[str, ...]]) -> Counter[str]:
        freqs: Counter[str] = Counter()
        for tokens in documents.values():
            freqs.update(set(tokens))

        return freqs

    def _score_term(self, term_freq: int, doc_freq: int, doc_len: int) -> float:
        k1 = 1.2
        b = 0.75

        idf = math.log(1 + (self._doc_count - doc_freq + 0.5) / (doc_freq + 0.5))
        numerator = term_freq * (k1 + 1)
        denominator = term_freq + k1 * (1 - b + b * doc_len / self._avgdl)

        return idf * numerator / denominator


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    positive = [score for score in scores.values() if score > 0]
    if not positive:
        return {key: 0.0 for key in scores}

    max_score = max(positive)
    return {key: max(value, 0.0) / max_score for key, value in scores.items()}


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


__all__ = [
    "RetrievalHit",
    "QueryPlan",
    "retrieve",
    "transform_query",
]
