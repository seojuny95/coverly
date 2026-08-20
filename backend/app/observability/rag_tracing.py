"""Serialization boundaries for RAG traces."""

from __future__ import annotations

from typing import Any

from app.observability.sanitization import mask_trace_text
from app.rag.official.models import RetrievalHit
from app.rag.policy.models import PolicyRetrievalHit


def trace_query(inputs: dict[str, Any]) -> dict[str, Any]:
    """Keep only the user query from a traced retrieval call."""

    query = inputs.get("query", "")
    return {"query": mask_trace_text(query) if isinstance(query, str) else ""}


def trace_rag_stage(inputs: dict[str, Any]) -> dict[str, Any]:
    """Keep query and tuning values, excluding stores, vectors, and session ids."""

    traced = trace_query(inputs)
    for key in ("candidate_k", "final_k", "top_k"):
        value = inputs.get(key)
        if isinstance(value, int):
            traced[key] = value
    return traced


def trace_rerank_stage(inputs: dict[str, Any]) -> dict[str, Any]:
    """Add candidate volume without serializing candidate documents."""

    traced = trace_rag_stage(inputs)
    hits = inputs.get("hits")
    if isinstance(hits, list):
        traced["input_count"] = len(hits)
    return traced


def trace_embedding_output(embedding: tuple[float, ...]) -> dict[str, int]:
    return {"dimensions": len(embedding)}


def trace_hit_summary(hits: list[Any]) -> dict[str, Any]:
    """Record ranking diagnostics without duplicating retrieved text."""

    scores = [round(float(hit.score), 6) for hit in hits if hasattr(hit, "score")]
    return {
        "count": len(hits),
        "scores": scores,
    }


def trace_official_documents(hits: list[RetrievalHit]) -> dict[str, Any]:
    documents = [
        {
            "type": "Document",
            "page_content": mask_trace_text(hit.chunk.text),
            "metadata": {
                "source_id": hit.chunk.source_id,
                "source_title": hit.chunk.source_title,
                "citation_label": hit.chunk.citation_label,
                "page_start": hit.chunk.page_start,
                "page_end": hit.chunk.page_end,
                "score": hit.score,
            },
        }
        for hit in hits
    ]
    hits_per_source: dict[str, int] = {}
    for hit in hits:
        source_id = hit.chunk.source_id
        hits_per_source[source_id] = hits_per_source.get(source_id, 0) + 1
    return {
        "output": documents,
        "metrics": {
            "document_count": len(documents),
            "unique_source_count": len(hits_per_source),
            "hits_per_source": hits_per_source,
            "total_content_chars": sum(len(document["page_content"]) for document in documents),
        },
    }


def trace_policy_documents(
    hits: list[PolicyRetrievalHit],
) -> dict[str, Any]:
    """Expose masked policy evidence without session or chunk identifiers."""

    documents = [
        {
            "type": "Document",
            "page_content": mask_trace_text(hit.chunk.text),
            "metadata": {
                "document_ref": hit.document_ref,
                "content_type": hit.chunk.content_type,
                "chunk_index": hit.chunk.chunk_index,
                "score": hit.score,
            },
        }
        for hit in hits
    ]
    hits_per_document: dict[str, int] = {}
    for hit in hits:
        document_ref = hit.document_ref or "unmapped"
        hits_per_document[document_ref] = hits_per_document.get(document_ref, 0) + 1
    return {
        "output": documents,
        "metrics": {
            "document_count": len(documents),
            "unique_document_count": len(hits_per_document),
            "hits_per_document": hits_per_document,
            "total_content_chars": sum(len(document["page_content"]) for document in documents),
        },
    }
