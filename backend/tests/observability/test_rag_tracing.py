from datetime import UTC, datetime, timedelta

from app.observability.rag_tracing import (
    trace_official_documents,
    trace_policy_documents,
    trace_query,
    trace_rerank_stage,
)
from app.rag.official.models import RagChunk, RetrievalHit
from app.rag.policy.models import PolicyChunk, PolicyRetrievalHit


def test_trace_query_excludes_non_query_arguments() -> None:
    traced = trace_query(
        {
            "query": "전화번호 010-1234-5678",
            "session_ids": ["private-session"],
            "store": object(),
        }
    )

    assert traced == {"query": "전화번호 [전화번호]"}


def test_official_retriever_trace_uses_langsmith_document_shape() -> None:
    hit = RetrievalHit(
        chunk=RagChunk(
            id="chunk-1",
            source_id="source-1",
            source_title="공식 자료",
            source_category="guide",
            publisher="기관",
            text="공식 근거 본문",
            page_start=2,
            page_end=3,
            citation_label="제1조",
        ),
        score=0.9,
        keyword_score=0.8,
        vector_score=0.7,
    )

    traced = trace_official_documents([hit])
    documents = traced["output"]

    assert documents[0]["type"] == "Document"
    assert documents[0]["page_content"] == "공식 근거 본문"
    assert documents[0]["metadata"]["source_id"] == "source-1"
    assert traced["metrics"] == {
        "document_count": 1,
        "unique_source_count": 1,
        "hits_per_source": {"source-1": 1},
        "total_content_chars": len("공식 근거 본문"),
    }


def test_policy_retriever_trace_keeps_masked_evidence_without_identifiers() -> None:
    now = datetime.now(UTC)
    hit = PolicyRetrievalHit(
        chunk=PolicyChunk(
            id="private-session:1",
            session_id="private-session",
            text=(
                "계약자 [개인정보](950524-*******)\n"
                "16836 경기 용인시 수지구 풍덕천로 91\n"
                "암진단비 3천만원"
            ),
            content_type="text",
            chunk_index=1,
            table_index=None,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        ),
        score=0.8,
        document_ref="document-1",
    )

    traced = trace_policy_documents([hit])
    documents = traced["output"]
    rendered = str(documents)

    assert documents[0]["type"] == "Document"
    assert "암진단비 3천만원" in documents[0]["page_content"]
    assert "16836" not in rendered
    assert "950524" not in rendered
    assert "풍덕천로 91" not in rendered
    assert "private-session" not in rendered
    assert "session_id" not in rendered
    assert documents[0]["metadata"]["document_ref"] == "document-1"
    assert traced["metrics"]["unique_document_count"] == 1
    assert traced["metrics"]["hits_per_document"] == {"document-1": 1}


def test_rerank_trace_records_candidate_count_without_candidate_text() -> None:
    traced = trace_rerank_stage(
        {
            "query": "암진단비",
            "hits": [object(), object()],
            "top_k": 1,
        }
    )

    assert traced == {"query": "암진단비", "top_k": 1, "input_count": 2}
