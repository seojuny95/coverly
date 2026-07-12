from pytest import MonkeyPatch

from app.services.rag.chunking import RagChunk, build_chunks
from app.services.rag.eval import evaluate_source_chunk_retrieval, load_retrieval_eval_cases
from app.services.rag.official_sources import rag_sources, verify_downloaded_sources
from app.services.rag.pgvector_store import VectorChunkHit
from app.services.rag.retrieve import ModelReranker, infer_profile, load_official_chunks, retrieve


def _forbid_local_official_rag() -> tuple[RagChunk, ...]:
    raise AssertionError("local official RAG must not run")


def test_official_sources_are_registered_and_verified() -> None:
    sources = rag_sources()

    assert {source.id for source in sources} == {
        "standard_terms_annex_15_2026_06_30",
        "fsc_policy_terms_roadmap_2019_10_22",
        "insurance_business_act",
        "financial_consumer_protection_act",
    }
    assert verify_downloaded_sources() == []


def test_indexing_source_chunker_preserves_standard_clause_article_citations() -> None:
    source = next(source for source in rag_sources() if source.category == "standard_clause")
    chunks = build_chunks(
        source,
        [
            "질병·상해보험 표준약관 ··· 2",
            "제1조(목적) 이 약관은 보험계약의 내용을 정합니다. "
            "계약자와 회사의 권리 의무를 설명합니다.\n"
            "제2조(계약 전 알릴 의무) 계약자 또는 피보험자는 중요한 사항을 알려야 합니다. "
            "회사는 이를 기준으로 계약 인수를 판단할 수 있습니다.",
        ],
    )

    assert len(chunks) == 2
    assert chunks[1].label == "제2조(계약 전 알릴 의무)"
    assert chunks[1].citation_label is not None
    assert "계약 전 알릴 의무" in chunks[1].citation_label


def test_lexical_reranker_scores_injected_candidates_by_profile() -> None:
    chunks = (
        RagChunk(
            id="payment",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text="제3조(보험금의 지급사유) 암 진단 확정 등 약관에서 정한 사유를 확인합니다.",
            page_start=10,
            page_end=10,
            label="제3조(보험금의 지급사유)",
        ),
        RagChunk(
            id="plain",
            source_id="fsc_policy_terms_roadmap_2019_10_22",
            source_title="보험약관 개선 로드맵",
            source_category="consumer_guide",
            publisher="금융위원회",
            text="보험약관의 용어순화와 소비자 이해도 제고 방향입니다.",
            page_start=2,
            page_end=2,
            label="약관 개선",
        ),
    )

    hits = retrieve(
        "암 진단비를 받을 수 있는지 볼 때 뭘 확인해야 해?",
        chunks=chunks,
        profile="claim_check",
    )

    assert hits[0].chunk.id == "payment"
    assert hits[0].rerank_score > hits[0].keyword_score


def test_optional_model_reranker_can_reorder_injected_candidates() -> None:
    chunks = (
        RagChunk(
            id="first",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text="보험금의 지급사유를 확인합니다.",
            page_start=1,
            page_end=1,
            label="지급사유",
        ),
        RagChunk(
            id="second",
            source_id="insurance_business_act",
            source_title="보험업법",
            source_category="law",
            publisher="국가법령정보센터",
            text="보험금 감액 또는 지급하지 아니하는 경우 사유를 설명하여야 합니다.",
            page_start=1,
            page_end=1,
            label="설명의무",
        ),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {"ranked": [{"chunk_id": "second"}, {"chunk_id": "first"}]}

    hits = retrieve(
        "보험금을 감액할 때 설명해야 해?",
        chunks=chunks,
        profile="claim_check",
        reranker=ModelReranker(complete),
    )

    assert [hit.chunk.id for hit in hits[:2]] == ["second", "first"]


def test_runtime_retrieve_uses_pgvector_candidates(monkeypatch: MonkeyPatch) -> None:
    from app.services.rag import retrieve as retrieve_module

    chunk = RagChunk(
        id="vector-hit",
        source_id="insurance_business_act",
        source_title="보험업법",
        source_category="law",
        publisher="국가법령정보센터",
        text="보험금 감액 사유를 설명하여야 합니다.",
        page_start=1,
        page_end=1,
        label="설명의무",
    )

    class Settings:
        database_url = "postgresql://example"
        openai_api_key = "test-key"
        openai_embedding_dimensions = 1536

    monkeypatch.setattr(retrieve_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(
        retrieve_module,
        "search_chunks",
        lambda *_args, **_kwargs: [VectorChunkHit(chunk=chunk, score=0.9)],
    )
    monkeypatch.setattr(retrieve_module, "load_official_chunks", _forbid_local_official_rag)

    hits = retrieve("보험금을 감액할 때 설명해야 해?")

    assert [hit.chunk.id for hit in hits] == ["vector-hit"]


def test_runtime_retrieve_returns_no_hits_when_pgvector_fails(monkeypatch: MonkeyPatch) -> None:
    from app.services.rag import retrieve as retrieve_module

    class Settings:
        database_url = "postgresql://example"
        openai_api_key = "test-key"
        openai_embedding_dimensions = 1536

    def fail(*_args: object, **_kwargs: object) -> list[VectorChunkHit]:
        raise RuntimeError("db down")

    monkeypatch.setattr(retrieve_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(retrieve_module, "search_chunks", fail)
    monkeypatch.setattr(retrieve_module, "load_official_chunks", _forbid_local_official_rag)

    hits = retrieve("계약 전 알릴 의무가 뭐야?")

    assert hits == []


def test_runtime_retrieve_without_database_does_not_use_local_official_rag(
    monkeypatch: MonkeyPatch,
) -> None:
    from app.services.rag import retrieve as retrieve_module

    class Settings:
        database_url = ""
        openai_api_key = ""
        openai_embedding_dimensions = 1536

    monkeypatch.setattr(retrieve_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(retrieve_module, "load_official_chunks", _forbid_local_official_rag)

    hits = retrieve("계약 전 알릴 의무가 뭐야?")

    assert hits == []


def test_infer_profile_routes_claim_checks_to_claim_profile() -> None:
    assert infer_profile("암이면 보험금 받을 수 있어?") == "claim_check"
    assert infer_profile("면책이 뭐야?") == "claim_check"
    assert infer_profile("고지의무 뜻이 뭐야?") == "term_explain"


def test_indexing_source_chunks_cover_eval_fixture() -> None:
    cases = load_retrieval_eval_cases()
    report = evaluate_source_chunk_retrieval(cases)

    assert report.total == 6
    assert report.recall == 1.0, report.results


def test_law_snapshots_are_available_for_pgvector_indexing() -> None:
    chunks = load_official_chunks()
    law_chunks = [chunk for chunk in chunks if chunk.source_id == "insurance_business_act"]

    assert law_chunks
    assert any("보험상품" in chunk.text for chunk in law_chunks)
