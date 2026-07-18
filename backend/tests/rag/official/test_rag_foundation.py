import re
from pathlib import Path

import pytest

from app.rag.embeddings import HashingEmbedder, openai_embedder_from_settings
from app.rag.official.chunkers import build_chunks
from app.rag.official.indexing import build_vector_records
from app.rag.official.loaders import _load_law_xml_chunks, load_official_chunks
from app.rag.official.models import RagChunk, RetrievalHit
from app.rag.official.retrieval import retrieve, transform_query
from app.rag.official.sources import (
    OfficialSource,
    _parse_source,
    rag_sources,
    verify_downloaded_sources,
)
from evals.rag.official import (
    AcceptedEvidence,
    ExtractionEvalCase,
    RetrievalEvalCase,
    evaluate_extraction,
    evaluate_retrieval,
    load_extraction_eval_cases,
    load_retrieval_eval_cases,
)
from evals.rag.official.extraction import EVAL_FIXTURE as EXTRACTION_EVAL_FIXTURE
from evals.rag.official.retrieval import EVAL_FIXTURE


def test_rag_sources_are_verified_and_small() -> None:
    sources = rag_sources()

    assert {source.id for source in sources} == {
        "standard_terms_annex_15_2026_06_30",
        "fsc_policy_terms_roadmap_2019_10_22",
        "knia_auto_insurance_product_explanation_2024_04_01",
        "easylaw_insurance_policyholder_2026_06_15",
        "insurance_business_act",
        "financial_consumer_protection_act",
    }
    assert {source.id: source.document_type for source in sources} == {
        "standard_terms_annex_15_2026_06_30": "standard_terms",
        "fsc_policy_terms_roadmap_2019_10_22": "consumer_guide",
        "knia_auto_insurance_product_explanation_2024_04_01": "product_explanation",
        "easylaw_insurance_policyholder_2026_06_15": "consumer_guide",
        "insurance_business_act": "law",
        "financial_consumer_protection_act": "law",
    }
    assert verify_downloaded_sources() == []


def test_official_source_document_type_is_required() -> None:
    with pytest.raises(ValueError, match="test_source: official source document_type is required"):
        _parse_source(
            {
                "id": "test_source",
                "title": "테스트 문서",
                "category": "consumer_guide",
                "publisher": "테스트",
                "status": "downloaded",
            }
        )


def test_official_source_document_type_must_be_supported() -> None:
    with pytest.raises(
        ValueError,
        match="test_source: unsupported official source document_type unknown",
    ):
        _parse_source(
            {
                "id": "test_source",
                "title": "테스트 문서",
                "category": "consumer_guide",
                "document_type": "unknown",
                "publisher": "테스트",
                "status": "downloaded",
            }
        )


def test_standard_clause_chunking_preserves_article_citations() -> None:
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
    assert "질병·상해보험 표준약관" in chunks[1].citation_label
    assert "계약 전 알릴 의무" in chunks[1].citation_label


def test_standard_clause_chunking_keeps_section_context_for_split_blocks() -> None:
    source = next(source for source in rag_sources() if source.category == "standard_clause")
    huge_body = "첫 문장입니다.\n" + "\n".join(
        f"{index}. 반복 내용입니다." for index in range(1, 140)
    )

    chunks = build_chunks(
        source,
        [
            "질병·상해보험 표준약관 ··· 2",
            f"제9조(긴 표 조항) {huge_body}",
        ],
    )

    assert len(chunks) > 1
    assert chunks[1].text.splitlines()[0] == "[질병·상해보험 표준약관 > 제9조(긴 표 조항)]"
    assert chunks[1].citation_label is not None
    assert "질병·상해보험 표준약관" in chunks[1].citation_label


def test_standard_clause_chunking_caps_articles_without_paragraph_breaks() -> None:
    """Regression test: an annex article with no blank lines and no further
    article header used to become a single unbounded chunk (28k+ chars),
    which OpenAI's embedding endpoint rejects past 8192 tokens."""

    source = next(source for source in rag_sources() if source.category == "standard_clause")
    huge_body = "장기 무중단 특약 " * 300
    chunks = build_chunks(
        source,
        [
            "부록 ··· 2",
            f"제99조(장기 무중단 조항) {huge_body}",
        ],
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 1500 for chunk in chunks)
    assert all(chunk.label == "제99조(장기 무중단 조항)" for chunk in chunks)


def test_product_explanation_chunking_uses_document_sections() -> None:
    source = next(
        source
        for source in rag_sources()
        if source.id == "knia_auto_insurance_product_explanation_2024_04_01"
    )

    chunks = build_chunks(
        source,
        [
            "자동차보험 설명서",
            "주 의! 실손 담보 중복가입 시 불이익\n"
            "실제 손해액을 보상하는 담보는 여러 개 중복 가입할 필요가 없습니다.\n"
            "발생한 손해액을 초과하여 보험금을 지급하지 않기 때문입니다.\n"
            "주 의! 예금자보호 관련 유의사항\n"
            "이 상품은 예금자보호법에 따라 보호되는 상품입니다.",
        ],
    )

    assert [chunk.label for chunk in chunks] == [
        "주 의! 실손 담보 중복가입 시 불이익",
        "주 의! 예금자보호 관련 유의사항",
    ]
    assert "발생한 손해액을 초과하여 보험금을 지급하지" in chunks[0].text
    assert "예금자보호법" in chunks[1].text


def test_build_vector_records_embeds_chunks() -> None:
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
    )

    records = build_vector_records(chunks=chunks, embedder=HashingEmbedder())

    assert len(records) == 1
    assert records[0].chunk.id == "payment"
    assert any(value > 0 for value in records[0].embedding)


def test_vector_records_keep_chunk_metadata() -> None:
    chunks = (
        RagChunk(
            id="payment",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text="보험금의 지급사유를 확인합니다.",
            page_start=1,
            page_end=1,
        ),
    )
    records = build_vector_records(chunks=chunks, embedder=HashingEmbedder())

    assert records[0].chunk.id == "payment"
    assert records[0].chunk.source_title == "표준약관"


def test_build_vector_records_defaults_to_the_openai_embedder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: production indexing must not silently fall back to the
    offline hashing embedder, which embeds in a different vector space than
    the OpenAI embedder retrieval queries with."""

    calls: list[list[str]] = []

    class _StubEmbedder:
        def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
            calls.append(texts)
            return [(1.0, 0.0) for _ in texts]

    monkeypatch.setattr(
        "app.rag.official.indexing.openai_embedder_from_settings",
        lambda: _StubEmbedder(),
    )
    chunks = (
        RagChunk(
            id="payment",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text="보험금의 지급사유를 확인합니다.",
            page_start=1,
            page_end=1,
        ),
    )

    records = build_vector_records(chunks=chunks)

    assert calls
    assert records[0].embedding == (1.0, 0.0)


def test_openai_embedder_rejects_mismatched_dimension_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: OPENAI_EMBEDDING_DIMENSIONS used to be read into
    Settings but never actually passed to the OpenAI embedder, so shrinking it
    without also updating RAG_EMBEDDING_DIM silently produced vectors that
    didn't match the pgvector column width."""

    class _StubSettings:
        openai_api_key = "test-key"
        openai_embedding_model = "text-embedding-3-small"
        openai_embedding_dimensions = 512
        rag_embedding_dim = 1536

    monkeypatch.setattr(
        "app.rag.embeddings.get_settings",
        lambda: _StubSettings(),
    )

    with pytest.raises(RuntimeError, match="must match"):
        openai_embedder_from_settings()


def test_retrieve_uses_hybrid_vector_and_bm25_search() -> None:
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
        "암 진단 확정 지급사유",
        chunks=chunks,
        embedder=HashingEmbedder(),
    )

    assert hits[0].chunk.id == "payment"
    assert hits[0].keyword_score > 0
    assert hits[0].vector_score > 0


def test_retrieve_requires_an_explicit_embedder_for_in_memory_chunks() -> None:
    """retrieve() is production code — it must not fall back to a test-only
    embedder on its own. Callers on the in-memory path own that choice."""

    chunks = (
        RagChunk(
            id="payment",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text="보험금의 지급사유를 확인합니다.",
            page_start=1,
            page_end=1,
        ),
    )

    with pytest.raises(ValueError, match="embedder is required"):
        retrieve("지급사유", chunks=chunks)


def test_transform_query_normalizes_whitespace_and_adds_korean_ngrams() -> None:
    plan = transform_query("암 진단비 받을 수 있어?")

    assert plan.search_query == "암 진단비 받을 수 있어?"
    assert plan.terms == ("암", "진단비", "받을", "수", "있어", "진단", "단비")


def test_retrieval_eval_fixture_passes_current_small_corpus() -> None:
    cases = load_retrieval_eval_cases()
    report = evaluate_retrieval(cases)

    assert report.total_cases == 72
    assert report.total == 54
    assert report.recall >= 0.3, report.results
    assert 0.0 <= report.mrr <= 1.0
    assert 0.0 <= report.precision_at_k <= 1.0
    assert 0.0 <= report.ndcg_at_k <= 1.0
    assert report.diagnostic_negative_total == 18
    assert report.average_latency_seconds >= 0.0


def test_retrieval_eval_fixture_uses_exact_existing_chunks_without_pii() -> None:
    cases = load_retrieval_eval_cases()
    chunk_ids = {chunk.id for chunk in load_official_chunks()}
    fixture_text = EVAL_FIXTURE.read_text(encoding="utf-8")

    assert len(cases) == 72
    assert len({case.id for case in cases}) == len(cases)
    assert all(
        case.expected_no_hits or set(case.relevant_chunk_ids).issubset(chunk_ids) for case in cases
    )
    assert all(case.relevant_chunk_ids or case.expected_no_hits for case in cases)
    assert all(case.accepted_evidence or case.expected_no_hits for case in cases)
    assert all(not case.accepted_evidence or not case.expected_no_hits for case in cases)
    assert re.search(r"\b\d{6}-[1-4]\d{6}\b", fixture_text) is None
    assert re.search(r"\b01[016789]-?\d{3,4}-?\d{4}\b", fixture_text) is None
    assert re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", fixture_text) is None


def test_extraction_eval_fixture_passes_current_official_sources() -> None:
    cases = load_extraction_eval_cases()
    report = evaluate_extraction(cases)

    assert report.total == 130
    assert report.pass_rate == 1.0
    assert report.chunk_found_rate == 1.0
    assert report.metadata_match_rate == 1.0
    assert report.citation_match_rate == 1.0
    assert report.text_coverage_rate == 1.0


def test_extraction_eval_fixture_uses_existing_chunks_without_pii() -> None:
    cases = load_extraction_eval_cases()
    chunks_by_id = {chunk.id: chunk for chunk in load_official_chunks()}
    fixture_text = EXTRACTION_EVAL_FIXTURE.read_text(encoding="utf-8")

    assert len(cases) == 130
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.chunk_id is None or case.chunk_id in chunks_by_id for case in cases)
    assert sum(case.case_type == "curated" for case in cases) == 50
    assert sum(case.case_type == "broad_regression" for case in cases) == 80
    assert all(case.chunk_id is None for case in cases if case.case_type == "curated")
    assert all(case.chunk_id is not None for case in cases if case.case_type == "broad_regression")
    assert re.search(r"\b\d{6}-[1-4]\d{6}\b", fixture_text) is None
    assert re.search(r"\b01[016789]-?\d{3,4}-?\d{4}\b", fixture_text) is None
    assert re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", fixture_text) is None


def test_extraction_eval_reports_metadata_citation_and_text_failures() -> None:
    chunk = RagChunk(
        id="chunk",
        source_id="source",
        source_title="문서",
        source_category="law",
        publisher="테스트",
        text="본문",
        page_start=1,
        page_end=1,
        label="제1조(목적)",
        citation_label="문서 제1조(목적)",
    )
    cases = (
        ExtractionEvalCase(
            id="case",
            case_type="broad_regression",
            source_id="source",
            chunk_id="chunk",
            expected_source_category="standard_clause",
            expected_label="제2조(정의)",
            expected_citation_contains=("없는 citation",),
            expected_page_start=2,
            expected_page_end=2,
            must_include=("없는 본문",),
        ),
    )

    report = evaluate_extraction(cases, chunks=(chunk,))

    assert report.passed == 0
    assert report.results[0].failed_checks == ("metadata", "citation", "text")


def test_retrieval_eval_reports_first_passing_rank_and_mrr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hits = [
        RetrievalHit(
            chunk=RagChunk(
                id="wrong",
                source_id="wrong_source",
                source_title="다른 문서",
                source_category="law",
                publisher="테스트",
                text="관련 없는 내용",
                page_start=1,
                page_end=1,
            ),
            score=1.0,
            keyword_score=0.0,
            vector_score=1.0,
        ),
        RetrievalHit(
            chunk=RagChunk(
                id="right-source",
                source_id="expected_source",
                source_title="기대 문서",
                source_category="law",
                publisher="테스트",
                text="아직 다른 표현만 있는 내용",
                page_start=1,
                page_end=1,
            ),
            score=0.9,
            keyword_score=0.0,
            vector_score=0.9,
        ),
        RetrievalHit(
            chunk=RagChunk(
                id="right-term",
                source_id="expected_source",
                source_title="기대 문서",
                source_category="law",
                publisher="테스트",
                text="기대용어가 있는 내용",
                page_start=2,
                page_end=2,
            ),
            score=0.8,
            keyword_score=0.0,
            vector_score=0.8,
        ),
    ]

    def _fake_retrieve(
        *,
        query: str,
        chunks: tuple[RagChunk, ...] | None = None,
        embedder: object | None = None,
        final_k: int = 5,
    ) -> list[RetrievalHit]:
        return hits

    monkeypatch.setattr("evals.rag.official.retrieval.retrieve", _fake_retrieve)
    cases = (
        RetrievalEvalCase(
            id="case",
            query="질문",
            profile="term_explain",
            difficulty="medium",
            relevant_chunk_ids=("right-term",),
        ),
    )

    report = evaluate_retrieval(cases, production=True)

    assert report.results[0].rank == 3
    assert report.results[0].precision_at_k == 1 / 3
    assert report.recall == 1.0
    assert report.mrr == 1 / 3
    assert report.precision_at_k == 1 / 3
    assert report.ndcg_at_k == 0.5
    assert report.average_latency_seconds >= 0.0


def test_retrieval_eval_uses_exact_relevant_chunk_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hits = [
        RetrievalHit(
            chunk=RagChunk(
                id="right-label",
                source_id="expected_source",
                source_title="기대 문서",
                source_category="law",
                publisher="테스트",
                text="본문에는 같은 표현이 없습니다.",
                page_start=1,
                page_end=1,
                label="제18조(설명 의무)",
                citation_label="기대 문서 제18조(설명 의무)",
            ),
            score=0.9,
            keyword_score=0.0,
            vector_score=0.9,
        ),
    ]

    def _fake_retrieve(
        *,
        query: str,
        chunks: tuple[RagChunk, ...] | None = None,
        embedder: object | None = None,
        final_k: int = 5,
    ) -> list[RetrievalHit]:
        return hits

    monkeypatch.setattr("evals.rag.official.retrieval.retrieve", _fake_retrieve)
    cases = (
        RetrievalEvalCase(
            id="case",
            query="질문",
            profile="term_explain",
            difficulty="medium",
            relevant_chunk_ids=("right-label",),
        ),
    )

    report = evaluate_retrieval(cases, production=True)

    assert report.results[0].passed is True
    assert report.results[0].rank == 1


def test_retrieval_eval_accepts_semantic_official_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hits = [
        RetrievalHit(
            chunk=RagChunk(
                id="alternative",
                source_id="consumer_guide",
                source_title="소비자 안내",
                source_category="consumer_guide",
                publisher="테스트",
                text="보험증권을 받은 날부터 15일 이내에 청약을 철회할 수 있습니다.",
                page_start=1,
                page_end=1,
                label="청약 철회",
                citation_label="소비자 안내 p.1",
            ),
            score=0.9,
            keyword_score=0.0,
            vector_score=0.9,
        ),
    ]

    def _fake_retrieve(
        *,
        query: str,
        chunks: tuple[RagChunk, ...] | None = None,
        embedder: object | None = None,
        final_k: int = 5,
    ) -> list[RetrievalHit]:
        return hits

    monkeypatch.setattr("evals.rag.official.retrieval.retrieve", _fake_retrieve)
    cases = (
        RetrievalEvalCase(
            id="case",
            query="질문",
            profile="claim_check",
            difficulty="medium",
            relevant_chunk_ids=("exact",),
            accepted_evidence=(
                AcceptedEvidence(
                    source_categories=("consumer_guide",),
                    required_terms=("청약", "철회", "15일"),
                ),
            ),
        ),
    )

    report = evaluate_retrieval(cases, production=True)

    assert report.results[0].exact_matched is False
    assert report.results[0].accepted_matched is True
    assert report.results[0].accepted_rank == 1
    assert report.accepted_recall == 1.0


def test_retrieval_eval_negative_cases_are_diagnostic_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hit = RetrievalHit(
        chunk=RagChunk(
            id="some-hit",
            source_id="source",
            source_title="공식 문서",
            source_category="consumer_guide",
            publisher="테스트",
            text="검색 결과",
            page_start=1,
            page_end=1,
        ),
        score=0.9,
        keyword_score=0.0,
        vector_score=0.9,
    )

    def _fake_retrieve(
        *,
        query: str,
        chunks: tuple[RagChunk, ...] | None = None,
        embedder: object | None = None,
        final_k: int = 5,
    ) -> list[RetrievalHit]:
        return [hit]

    monkeypatch.setattr("evals.rag.official.retrieval.retrieve", _fake_retrieve)
    cases = (
        RetrievalEvalCase(
            id="positive",
            query="보험 질문",
            profile="term_explain",
            difficulty="medium",
            relevant_chunk_ids=("some-hit",),
        ),
        RetrievalEvalCase(
            id="negative",
            query="오늘 날씨 알려줘",
            profile="out_of_scope",
            difficulty="hard",
            relevant_chunk_ids=(),
            expected_no_hits=True,
        ),
    )

    report = evaluate_retrieval(cases, production=True)

    assert report.passed == 1
    assert report.total == 1
    assert report.total_cases == 2
    assert report.pass_rate == 1.0
    assert report.diagnostic_negative_no_hit_rate == 0.0


def test_law_snapshots_are_loaded_as_rag_chunks() -> None:
    chunks = load_official_chunks()
    law_chunks = [chunk for chunk in chunks if chunk.source_id == "insurance_business_act"]

    assert law_chunks
    assert any("보험상품" in chunk.text for chunk in law_chunks)


_LAW_XML_WITH_BRANCH_ARTICLE = """<?xml version="1.0" encoding="UTF-8"?>
<법령>
  <조문단위>
    <조문번호>11</조문번호>
    <조문여부>조문</조문여부>
    <조문제목>보험회사의 겸영업무</조문제목>
    <조문내용>제11조(보험회사의 겸영업무) 경영건전성을 해치지 않는 금융업무를 할 수 있다.</조문내용>
  </조문단위>
  <조문단위>
    <조문번호>11</조문번호>
    <조문가지번호>2</조문가지번호>
    <조문여부>조문</조문여부>
    <조문제목>보험회사의 부수업무</조문제목>
    <조문내용>제11조의2(보험회사의 부수업무) 보험업에 부수하는 업무를 할 수 있다.</조문내용>
  </조문단위>
</법령>
"""


def test_law_xml_branch_articles_get_distinct_ids_and_labels(tmp_path: Path) -> None:
    """Regression test: 조문가지번호 (e.g. 제11조의2) used to be ignored, so
    "제11조"/"제11조의2"/"제11조의3" collapsed onto the same id and every
    branch article but the first was silently dropped from the index."""

    xml_path = tmp_path / "law.xml"
    xml_path.write_text(_LAW_XML_WITH_BRANCH_ARTICLE, encoding="utf-8")
    source = OfficialSource(
        id="test_law",
        title="테스트 법률",
        category="law",
        document_type="law",
        publisher="법제처",
        status="downloaded",
        rag_enabled=True,
        local_path=str(xml_path),
    )

    chunks = _load_law_xml_chunks(source)

    assert [chunk.label for chunk in chunks] == [
        "제11조(보험회사의 겸영업무)",
        "제11조의2(보험회사의 부수업무)",
    ]
    assert len({chunk.id for chunk in chunks}) == 2


def test_evaluate_retrieval_production_flag_skips_in_memory_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[RagChunk, ...] | None] = []

    def _fake_retrieve(
        *,
        query: str,
        chunks: tuple[RagChunk, ...] | None = None,
        embedder: object | None = None,
        final_k: int = 5,
    ) -> list[RetrievalHit]:
        calls.append(chunks)
        return []

    monkeypatch.setattr("evals.rag.official.retrieval.retrieve", _fake_retrieve)
    cases = (
        RetrievalEvalCase(
            id="case",
            query="질문",
            profile="out_of_scope",
            difficulty="hard",
            relevant_chunk_ids=(),
            expected_no_hits=True,
        ),
    )

    evaluate_retrieval(cases, production=True)
    evaluate_retrieval(cases, production=False)

    assert calls[0] is None
    assert calls[1] is not None
