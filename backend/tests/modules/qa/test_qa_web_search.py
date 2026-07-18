from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.context import build_qa_context
from app.modules.qa.tools.web_search import (
    _contains_unallowed_url,
    _search_prompt,
    _validated_source_urls,
    sanitize_search_query,
    search_allowed_domains,
)


def test_held_insurer_search_uses_only_verified_insurer_domains() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험사": "삼성화재", "상품명": "건강보험"},
            "보장목록": [],
        }
    )
    context = build_qa_context("보험사 최신 안내를 찾아줘", [policy], None, [])

    assert search_allowed_domains(context, "insurer_guidance") == ["samsungfire.com"]


def test_law_update_search_uses_only_official_domains() -> None:
    context = build_qa_context("보험 법령의 최신 변경을 알려줘", [], None, [])

    assert search_allowed_domains(context, "law_update") == [
        "law.go.kr",
        "fsc.go.kr",
        "korea.kr",
        "molit.go.kr",
    ]


def test_search_query_masks_personal_identifiers() -> None:
    query = sanitize_search_query("010-1234-5678 test@example.com 계약 전 알릴 의무")

    assert "010-1234-5678" not in query
    assert "test@example.com" not in query
    assert "[전화번호]" in query
    assert "[이메일]" in query


def test_web_sources_require_cited_allowlisted_urls() -> None:
    response = {
        "output": [
            {
                "content": [
                    {
                        "annotations": [
                            {"type": "url_citation", "url": "https://www.korea.kr/one"},
                            {"type": "url_citation", "url": "https://www.molit.go.kr/two"},
                            {"type": "url_citation", "url": "https://example.com/rejected"},
                        ]
                    }
                ]
            }
        ]
    }

    assert _validated_source_urls(response, ["korea.kr", "molit.go.kr"]) == [
        "https://www.korea.kr/one",
        "https://www.molit.go.kr/two",
    ]
    assert _contains_unallowed_url("https://example.com/rejected", ["fsc.go.kr"])


def test_law_prompt_requires_source_evidence_instead_of_name_inference() -> None:
    prompt = _search_prompt("법률 별칭의 의미를 알려줘", "law_update")

    assert "공식 페이지 본문에 그 별칭이 직접 등장" in prompt
    assert "관련 없는 법률을 유추하지 마세요" in prompt
