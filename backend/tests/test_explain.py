from app.services.policy.coverage.explanation import explain_coverages
from app.services.rag.official.models import RagChunk, RetrievalHit


def _hit(text: str) -> RetrievalHit:
    return RetrievalHit(
        chunk=RagChunk(
            id="official-1",
            source_id="standard_terms_annex_15_2026_06_30",
            source_title="표준약관",
            source_category="standard_clause",
            publisher="금융감독원",
            text=text,
            page_start=1,
            page_end=1,
            citation_label="표준약관 제3조",
        ),
        score=1.0,
        keyword_score=1.0,
        vector_score=1.0,
    )


def test_generates_an_explanation_for_a_coverage_name() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        assert "official_excerpts" in user
        assert "약관 확인이 필요하다는 안내" in system
        return {"설명목록": [{"담보명": "가입설명담보", "해설": "이런 상황에 보험금을 드려요."}]}

    explanations, ok = explain_coverages(
        ["가입설명담보"],
        complete=fake_complete,
        retrieve_context=lambda _: [_hit("보험금의 지급사유와 보상하지 않는 사항을 확인합니다.")],
    )

    assert ok is True
    assert explanations == {"가입설명담보": "이런 상황에 보험금을 드려요."}


def test_explains_every_requested_name() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {
            "설명목록": [
                {"담보명": "다중설명담보A", "해설": "A 설명이에요."},
                {"담보명": "다중설명담보B", "해설": "B 설명이에요."},
            ]
        }

    explanations, ok = explain_coverages(
        ["다중설명담보A", "다중설명담보B"],
        complete=fake_complete,
        retrieve_context=lambda _: [],
    )

    assert ok is True
    assert explanations == {"다중설명담보A": "A 설명이에요.", "다중설명담보B": "B 설명이에요."}


def test_reports_not_ok_when_the_llm_fails() -> None:
    def failing_complete(system: str, user: str) -> dict[str, object]:
        raise RuntimeError("API down")

    explanations, ok = explain_coverages(
        ["실패담보"],
        complete=failing_complete,
        retrieve_context=lambda _: [],
    )

    assert ok is False  # lets the caller degrade to 분석상태=부분
    assert "실패담보" not in explanations


def test_omits_names_the_llm_cannot_explain() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": []}

    explanations, ok = explain_coverages(
        ["설명불가능담보"],
        complete=fake_complete,
        retrieve_context=lambda _: [],
    )

    assert ok is True
    assert explanations == {}


def test_no_names_yields_no_explanations() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        return {"설명목록": [{"담보명": "지어낸담보", "해설": "호출되면 안 돼요."}]}

    assert explain_coverages([], complete=fake_complete) == ({}, True)


def test_passes_official_excerpts_to_explanation_prompt() -> None:
    def fake_complete(system: str, user: str) -> dict[str, object]:
        assert "제3조" in user
        assert "지급사유" in user
        assert "면책" in system
        return {"설명목록": [{"담보명": "암진단비", "해설": "암 진단 확정과 약관 조건을 봐요."}]}

    explanations, ok = explain_coverages(
        ["암진단비"],
        complete=fake_complete,
        retrieve_context=lambda _: [_hit("제3조(보험금의 지급사유) 진단확정과 면책을 확인합니다.")],
    )

    assert ok is True
    assert explanations["암진단비"] == "암 진단 확정과 약관 조건을 봐요."
