"""Embedding helpers for official-source chunks and queries.

Production indexing uses LlamaIndex's OpenAIEmbedding wrapper. The hashing
embedder exists only so tests and local diagnostics can run without network.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from llama_index.embeddings.openai import OpenAIEmbedding

from app.settings import get_settings

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_HASH_VECTOR_SIZE = 256


class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        """Return one normalized embedding per text."""


class HashingEmbedder:
    """Deterministic local embedder for tests and offline development."""

    model_name = "local-hashing-256"

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [_hash_embed(text) for text in texts]


class LlamaIndexOpenAIEmbedder:
    """Small wrapper around LlamaIndex's OpenAI embedding integration."""

    def __init__(self, *, api_key: str, model: str, dimensions: int) -> None:
        self.model_name = model
        self._embed_model = OpenAIEmbedding(
            api_key=api_key,
            model=model,
            dimensions=dimensions,
            timeout=30.0,
            max_retries=2,
        )

    def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        embeddings = self._embed_model.get_text_embedding_batch(texts)
        return [tuple(float(value) for value in embedding) for embedding in embeddings]

    def embed_query(self, query: str) -> tuple[float, ...]:
        embedding = self._embed_model.get_query_embedding(query)
        return tuple(float(value) for value in embedding)


def openai_embedder_from_settings() -> LlamaIndexOpenAIEmbedder:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if settings.openai_embedding_dimensions != settings.rag_embedding_dim:
        raise RuntimeError(
            "OPENAI_EMBEDDING_DIMENSIONS "
            f"({settings.openai_embedding_dimensions}) must match RAG_EMBEDDING_DIM "
            f"({settings.rag_embedding_dim}) — the pgvector column width has to match "
            "what the embedder actually produces."
        )
    return LlamaIndexOpenAIEmbedder(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
    )


def _hash_embed(text: str) -> tuple[float, ...]:
    vector = [0.0] * _HASH_VECTOR_SIZE
    for token in _TOKEN_RE.findall(text.casefold()):
        if len(token) < 2:
            continue
        digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
        index = int.from_bytes(digest, "big") % _HASH_VECTOR_SIZE
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(value / norm for value in vector)
