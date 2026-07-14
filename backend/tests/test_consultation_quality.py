import json

from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.schemas.qa import ConversationMessage
from app.services.analysis.service import analyze_portfolio
from app.services.qa.service import answer_portfolio_question


def _policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "policy-1",
                "기본정보": {
                    "보험사": "테스트보험",
                    "상품명": "건강보험",
                    "보험분류": "상해·질병·실손",
                    "피보험자정보": {
                        "나이": 35,
                        "성별": "여성",
                        "생애단계": "성인",
                    },
                },
                "보장목록": [
                    {
                        "담보명": "암진단비",
                        "가입금액": "3천만원",
                        "지급유형": "정액",
                    }
                ],
            }
        )
    ]


def _demographics() -> InsuredDemographics:
    return InsuredDemographics(age=35, gender="여성", source="policy")


def test_analysis_ignores_unsupported_amount_review_output() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "암 진단 담보가 확인돼요",
                    "detail": "현재 증권에서 확인한 준비 항목이에요",
                    "evidence_ids": ["coverage:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [
                {
                    "coverage_evidence_id": "coverage:1",
                    "title": "치료 중 생활비와 비교해 보세요",
                    "guidance": "현재 금액을 소득 공백과 함께 검토하는 일반 가이드예요",
                    "rationale": "필요 금액은 소득과 부양 책임에 따라 달라져요",
                    "suggested_range": "상담에서 여러 범위를 비교해 보세요",
                }
            ],
            "next_questions": ["치료 중 필요한 월 생활비는 얼마인가요?"],
            "next_steps": ["가족의 부양 책임과 월 예산을 정리해 보세요"],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    assert result.generation == "llm"
    assert result.counselor.strengths[0].evidence_ids == ["coverage:1"]
    assert result.counselor.amount_review_items == []


def test_analysis_rejects_semantically_mismatched_strength_and_gap_evidence() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "수술 담보가 확인돼요",
                    "detail": "수술 준비 항목이에요",
                    "evidence_ids": ["coverage:1"],
                }
            ],
            "gaps": [
                {
                    "title": "심장질환 항목을 확인해 보세요",
                    "detail": "심장질환 담보가 확인되지 않았어요",
                    "evidence_ids": ["gap:1"],
                }
            ],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    assert result.generation == "fallback"
    rendered = result.model_dump_json()
    assert "수술 담보가 확인돼요" not in rendered
    assert "심장질환 담보가 확인되지 않았어요" not in rendered


def test_analysis_rejects_unknown_evidence_and_risky_claims() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "보장이 충분합니다",
                    "detail": "보험금이 지급됩니다",
                    "evidence_ids": ["made-up"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    assert result.generation == "fallback"
    rendered = result.model_dump_json()
    assert "보험금이 지급됩니다" not in rendered
    assert "made-up" not in rendered


def test_analysis_accepts_grounded_amount_opinion_and_llm_overview() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "overview": "전반적으로 진단 보장이 잘 잡혀 있어요.",
            "strengths": [
                {
                    "title": "암 진단 보장이 잘 준비돼 있어요",
                    "detail": "암 진단비 3천만원이 확인돼 진단 초기 목돈에 대응할 수 있어요",
                    "evidence_ids": ["coverage:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    assert result.generation == "llm"
    assert "잘 준비돼 있어요" in result.model_dump_json()
    assert result.counselor.overview == "전반적으로 진단 보장이 잘 잡혀 있어요."


def test_analysis_still_blocks_sales_commands_and_payout_claims() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "overview": "",
            "strengths": [
                {
                    "title": "암 진단 보장을 늘리세요",
                    "detail": "암 진단비를 증액하세요",
                    "evidence_ids": ["coverage:1"],
                },
                {
                    "title": "암 진단 담보가 확인돼요",
                    "detail": "암 진단을 받으면 보험금이 지급됩니다",
                    "evidence_ids": ["coverage:1"],
                },
                {
                    "title": "이 특약을 추천해요",
                    "detail": "이 특약은 반드시 가입하는 것이 좋습니다",
                    "evidence_ids": ["coverage:1"],
                },
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    rendered = result.model_dump_json()
    assert "늘리세요" not in rendered
    assert "증액하세요" not in rendered
    assert "보험금이 지급됩니다" not in rendered
    assert "반드시 가입" not in rendered


def test_qa_passes_recent_history_and_returns_only_catalog_citations() -> None:
    captured: dict[str, object] = {}

    def complete(_system: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        return {
            "confirmed_fact": "건강보험 가입 사실을 확인했어요",
            "guidance": "상담에서는 유지 가능한 예산도 함께 확인해 보세요",
            "evidence_ids": ["policy:1"],
            "suggestions": ["확인된 담보도 알려주세요"],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "이어서 무엇을 확인할까요?",
        _policies(),
        demographics=_demographics(),
        history=[ConversationMessage(role="user", content="암 보장을 먼저 봐줘")],
        complete=complete,
    )

    assert captured["history"] == [{"role": "user", "content": "암 보장을 먼저 봐줘"}]
    assert result.generation == "llm"
    assert [citation.evidence_id for citation in result.citations] == ["policy:1"]


def test_qa_falls_back_when_llm_cites_unknown_fact() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "confirmed_fact": "제공되지 않은 사실이에요",
            "guidance": None,
            "evidence_ids": ["unknown"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보험을 상담해줘",
        _policies(),
        demographics=_demographics(),
        complete=complete,
    )

    assert result.generation == "fallback"
    assert all(citation.evidence_id != "unknown" for citation in result.citations)


def test_qa_answers_claim_question_with_a_hedge_instead_of_refusing() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 관련 담보가 확인돼요.",
            "guidance": "정확한 지급 여부는 약관과 보험사에서 확인하는 게 좋아요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "암 진단을 받으면 보험금을 받을 수 있나요?",
        _policies(),
        demographics=_demographics(),
        complete=complete,
    )

    assert result.status == "answered"
    assert result.generation == "llm"
