"""Ephemeral RAG over uploaded policy text.

The store is process-local by design: uploaded source text, chunks, and local
embeddings disappear when the process ends or the session is explicitly
deleted. Nothing here writes user policy text to disk.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from dataclasses import dataclass
from threading import RLock

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_PHONE_RE = re.compile(r"01[016789]-?\d{3,4}-?\d{4}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RRN_RE = re.compile(r"\d{6}-?[1-4]\d{6}")
_DEFAULT_TTL_SECONDS = 60 * 60
_VECTOR_SIZE = 128
_MAX_CHUNK_CHARS = 900


@dataclass(frozen=True)
class SessionRagChunk:
    id: str
    session_id: str
    text: str
    embedding: tuple[float, ...]
    created_at: float


@dataclass(frozen=True)
class SessionRagHit:
    chunk: SessionRagChunk
    score: float


class SessionRagStore:
    def __init__(self, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._chunks_by_session: dict[str, tuple[SessionRagChunk, ...]] = {}
        self._created_at: dict[str, float] = {}
        self._lock = RLock()

    def add_text(self, text: str, *, now: float | None = None) -> str | None:
        normalized = _mask_pii(text).strip()
        if not normalized:
            return None
        created_at = time.time() if now is None else now
        session_id = uuid.uuid4().hex
        chunks = tuple(
            SessionRagChunk(
                id=f"session:{session_id}:{index}",
                session_id=session_id,
                text=chunk,
                embedding=_embed(chunk),
                created_at=created_at,
            )
            for index, chunk in enumerate(_chunk_text(normalized), start=1)
        )
        if not chunks:
            return None
        with self._lock:
            self.cleanup_expired(now=created_at)
            self._created_at[session_id] = created_at
            self._chunks_by_session[session_id] = chunks
        return session_id

    def retrieve(
        self,
        session_ids: list[str],
        query: str,
        *,
        top_k: int = 4,
        now: float | None = None,
    ) -> list[SessionRagHit]:
        if not session_ids or not query.strip():
            return []
        checked_at = time.time() if now is None else now
        query_embedding = _embed(query)
        hits: list[SessionRagHit] = []
        with self._lock:
            self.cleanup_expired(now=checked_at)
            for session_id in dict.fromkeys(session_ids):
                for chunk in self._chunks_by_session.get(session_id, ()):
                    score = _cosine(query_embedding, chunk.embedding)
                    if score > 0:
                        hits.append(SessionRagHit(chunk=chunk, score=score))
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.id))
        return hits[:top_k]

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._created_at.pop(session_id, None)
            self._chunks_by_session.pop(session_id, None)

    def cleanup_expired(self, *, now: float | None = None) -> None:
        checked_at = time.time() if now is None else now
        expired = [
            session_id
            for session_id, created_at in self._created_at.items()
            if checked_at - created_at > self._ttl_seconds
        ]
        for session_id in expired:
            self._created_at.pop(session_id, None)
            self._chunks_by_session.pop(session_id, None)


_STORE = SessionRagStore()


def store_policy_text(text: str) -> str | None:
    return _STORE.add_text(text)


def retrieve_policy_context(
    session_ids: list[str], query: str, *, top_k: int = 4
) -> list[SessionRagHit]:
    return _STORE.retrieve(session_ids, query, top_k=top_k)


def delete_policy_session(session_id: str) -> None:
    _STORE.delete(session_id)


def _chunk_text(text: str) -> list[str]:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) > _MAX_CHUNK_CHARS:
            chunks.append(current)
            current = paragraph
            continue
        current = f"{current}\n{paragraph}".strip() if current else paragraph
    if current:
        chunks.append(current)
    return chunks


def _mask_pii(text: str) -> str:
    masked = _PHONE_RE.sub("[전화번호]", text)
    masked = _EMAIL_RE.sub("[이메일]", masked)
    return _RRN_RE.sub("[주민등록번호]", masked)


def _embed(text: str) -> tuple[float, ...]:
    vector = [0.0] * _VECTOR_SIZE
    for token in _TOKEN_RE.findall(text.casefold()):
        if len(token) < 2:
            continue
        digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
        index = int.from_bytes(digest, "big") % _VECTOR_SIZE
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
