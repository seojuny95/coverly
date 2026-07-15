"""Index one uploaded policy into the session-scoped vector store."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.integrations.postgres.policy_rag_store import shared_policy_store
from app.rag.embeddings import Embedder, openai_embedder_from_settings
from app.rag.policy.models import PolicyChunk, PolicyVectorRecord
from app.rag.policy.pii import mask_policy_pii
from app.rag.policy.session_tokens import (
    ensure_policy_session_secret_configured,
    sign_policy_session_id,
)
from app.rag.policy.source import PolicyDocument, build_policy_source_chunks
from app.rag.policy.store import PolicyRagStore


def build_policy_vector_records(
    doc: PolicyDocument,
    *,
    session_id: str,
    created_at: datetime,
    expires_at: datetime,
    embedder: Embedder,
) -> tuple[PolicyVectorRecord, ...]:
    source_chunks = build_policy_source_chunks(doc)
    masked_texts = [mask_policy_pii(chunk.text).strip() for chunk in source_chunks]
    nonempty = [
        (source, text) for source, text in zip(source_chunks, masked_texts, strict=True) if text
    ]
    if not nonempty:
        return ()

    embeddings = embedder.embed_texts([text for _, text in nonempty])
    records: list[PolicyVectorRecord] = []
    for chunk_index, ((source, text), embedding) in enumerate(
        zip(nonempty, embeddings, strict=True), start=1
    ):
        records.append(
            PolicyVectorRecord(
                chunk=PolicyChunk(
                    id=f"{session_id}:{chunk_index}",
                    session_id=session_id,
                    text=text,
                    content_type=source.content_type,
                    chunk_index=chunk_index,
                    table_index=source.table_index,
                    created_at=created_at,
                    expires_at=expires_at,
                ),
                embedding=embedding,
            )
        )
    return tuple(records)


def index_policy_document(
    doc: PolicyDocument,
    *,
    store: PolicyRagStore | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
) -> str | None:
    ensure_policy_session_secret_configured()
    created_at = now or datetime.now(UTC)
    settings = get_settings()
    expires_at = created_at + timedelta(seconds=settings.policy_rag_ttl_seconds)
    max_expires_at = created_at + timedelta(seconds=settings.policy_rag_max_ttl_seconds)
    session_id = uuid.uuid4().hex
    records = build_policy_vector_records(
        doc,
        session_id=session_id,
        created_at=created_at,
        expires_at=expires_at,
        embedder=embedder or openai_embedder_from_settings(),
    )
    if not records:
        return None
    (store or shared_policy_store()).add(records)
    return sign_policy_session_id(
        session_id,
        expires_at,
        max_expires_at=max_expires_at,
    )
