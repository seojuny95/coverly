import json

from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.schemas.qa import ConversationMessage
from app.services.portfolio_analysis import analyze_portfolio
from app.services.portfolio_qa import answer_portfolio_question


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


def test_analysis_accepts_cited_llm_guidance_and_marks_low_confidence() -> None:
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
    assert result.counselor.amount_review_items[0].current_amount == 30_000_000
    assert result.counselor.amount_review_items[0].confidence == "low"
    assert result.counselor.amount_review_items[0].basis == "general_guidance"
    assert result.counselor.amount_review_items[0].requires_personal_context is True
    assert result.counselor.amount_review_items[0].required_context == [
        "소득",
        "치료·회복 기간 생활비",
        "부양 책임",
        "가용 예산",
    ]


def test_analysis_rewrites_direct_amount_actions_and_adequacy_conclusions() -> None:
    unsafe_phrases = (
        "1억원으로 늘리세요",
        "현재 금액이면 충분해요",
        "소득을 고려하면 1억원이 필요해요",
    )

    for phrase in unsafe_phrases:

        def complete(_system: str, _user: str, phrase: str = phrase) -> dict[str, object]:
            return {
                "strengths": [],
                "gaps": [],
                "amount_review_items": [
                    {
                        "coverage_evidence_id": "coverage:1",
                        "title": "암 진단비 금액 검토",
                        "guidance": phrase,
                        "rationale": "소득과 생활비를 함께 봐야 해요",
                        "suggested_range": None,
                    }
                ],
                "next_questions": [],
                "next_steps": [],
            }

        result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

        assert result.generation == "llm"
        assert phrase not in result.model_dump_json()
        review = result.counselor.amount_review_items[0]
        assert review.suggested_range is None
        assert review.confidence == "low"
        assert review.basis == "general_guidance"
        assert review.requires_personal_context is True


def test_analysis_supplies_required_personal_context_deterministically() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "strengths": [],
            "gaps": [],
            "amount_review_items": [
                {
                    "coverage_evidence_id": "coverage:1",
                    "title": "암 진단비 금액 검토",
                    "guidance": "일반 가이드의 범위를 참고해 보세요",
                    "rationale": "다른 가입자와 비교할 수 있어요",
                    "suggested_range": None,
                }
            ],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    assert result.generation == "llm"
    review = result.counselor.amount_review_items[0]
    assert "다른 가입자와 비교" not in review.rationale
    assert review.required_context == [
        "소득",
        "치료·회복 기간 생활비",
        "부양 책임",
        "가용 예산",
    ]


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


def test_analysis_rejects_adequacy_claim_with_valid_matching_evidence() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "strengths": [
                {
                    "title": "암 진단 보장이 충분해요",
                    "detail": "암 진단 담보가 잘 준비되어 있어요",
                    "evidence_ids": ["coverage:1"],
                }
            ],
            "gaps": [],
            "amount_review_items": [],
            "next_questions": [],
            "next_steps": [],
        }

    result = analyze_portfolio(_policies(), demographics=_demographics(), complete=complete)

    assert result.generation == "fallback"
    assert "충분해요" not in result.model_dump_json()


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


def test_qa_refuses_claim_decision_before_calling_llm() -> None:
    def complete(_system: str, _user: str) -> dict[str, object]:
        raise AssertionError("claim questions must not reach the LLM")

    result = answer_portfolio_question(
        "암 진단을 받으면 보험금을 받을 수 있나요?",
        _policies(),
        demographics=_demographics(),
        complete=complete,
    )

    assert result.status == "refused"
    assert result.generation == "fallback"
    assert result.citations == []
