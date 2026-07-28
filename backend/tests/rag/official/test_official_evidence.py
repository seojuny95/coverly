from app.rag.official.evidence import search_official_evidence
from app.rag.official.models import RagChunk, RetrievalHit


def _hit(
    *,
    chunk_id: str = "chunk-1",
    text: str = "청약은 보험증권을 받은 날부터 15일 이내 철회할 수 있다.",
) -> RetrievalHit:
    chunk = RagChunk(
        id=chunk_id,
        source_id="standard-terms",
        source_title="보험업감독업무시행세칙 별표15 표준약관",
        source_category="standard_clause",
        publisher="금융감독원",
        text=text,
        page_start=10,
        page_end=11,
        citation_label="제17조(청약의 철회)",
        version_label="2026-06-15",
        source_url="https://example.com/terms",
    )
    return RetrievalHit(chunk=chunk, score=1.0, keyword_score=1.0, vector_score=1.0)


def test_search_official_evidence_returns_excerpt_and_provenance() -> None:
    result = search_official_evidence("청약철회 기간은?", hits=[_hit()])

    assert result.matched is True
    assert len(result.evidence) == 1
    assert result.evidence[0].excerpt.startswith("청약은")
    assert result.evidence[0].citation_label == "제17조(청약의 철회)"
    assert result.evidence[0].publisher == "금융감독원"
    assert result.evidence[0].source_url == "https://example.com/terms"
    assert result.limitations


def test_search_official_evidence_does_not_generate_an_answer() -> None:
    result = search_official_evidence("청약철회 기간은?", hits=[_hit()])

    payload = result.model_dump()

    assert "answer" not in payload
    assert "evidence" in payload


def test_search_official_evidence_returns_boundary_when_no_hit_exists() -> None:
    result = search_official_evidence("근거 없는 질문", hits=[])

    assert result.matched is False
    assert result.evidence == ()
    assert result.limitations == ("공식 자료에서 질문과 관련된 근거를 찾지 못했습니다.",)


def test_search_official_evidence_limits_and_compacts_excerpts() -> None:
    hits = [
        _hit(chunk_id=f"chunk-{index}", text=f"근거 {index} " + "가" * 1_000) for index in range(7)
    ]

    result = search_official_evidence("근거를 알려줘", hits=hits, final_k=3)

    assert len(result.evidence) == 3
    assert all(len(item.excerpt) <= 901 for item in result.evidence)
    assert all(item.excerpt.endswith("…") for item in result.evidence)
