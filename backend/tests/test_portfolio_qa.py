import json

from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.schemas.qa import ConversationMessage
from app.services.portfolio_qa import answer_portfolio_question


def _policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {
                    "보험사": "테스트보험",
                    "상품명": "건강보험",
                    "보험분류": "질병",
                    "피보험자정보": {
                        "나이": 35,
                        "성별": "여성",
                        "생애단계": "성인",
                    },
                },
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        )
    ]


def _alias_policies() -> list[PolicyInput]:
    rows = [
        ("p1", "보험사A", "허혈성심장질환진단비", 10_000_000),
        ("p2", "보험사B", "허혈성심질환진단비(감액없음)", 20_000_000),
    ]
    return [
        PolicyInput.model_validate(
            {
                "id": policy_id,
                "기본정보": {
                    "보험사": insurer,
                    "상품명": f"건강보험-{policy_id}",
                    "보험분류": "질병",
                },
                "보장목록": [
                    {
                        "담보명": coverage_name,
                        "가입금액숫자": amount,
                        "지급유형": "정액",
                    }
                ],
            }
        )
        for policy_id, insurer, coverage_name, amount in rows
    ]


def _named_insurer_policies(insurer: str) -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": insurer, "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        )
    ]


def test_qa_answers_how_to_claim_with_insurer_channels() -> None:
    def forbidden(_: str, __: str) -> dict[str, object]:
        raise AssertionError("LLM should not be called for claim-channel questions")

    result = answer_portfolio_question(
        "실손 어떻게 청구해?", _named_insurer_policies("삼성화재"), complete=forbidden
    )

    assert result.status == "answered"
    assert result.claim_channels is not None
    assert any(insurer.name == "삼성화재" for insurer in result.claim_channels.insurers)
    assert result.claim_channels.indemnity is not None
    assert result.claim_channels.indemnity.name == "실손24"
    assert any("약관" in limitation for limitation in result.limitations)


def test_qa_claim_channels_include_clickable_links() -> None:
    result = answer_portfolio_question("실손 어떻게 청구해?", _named_insurer_policies("삼성화재"))

    assert result.claim_channels is not None
    insurer = result.claim_channels.insurers[0]
    assert insurer.name == "삼성화재"
    assert any(link.url.startswith("http") for link in insurer.links)
    assert result.claim_channels.indemnity is not None
    assert any(link.url.startswith("http") for link in result.claim_channels.indemnity.links)


def test_qa_still_refuses_coverage_verdict_questions() -> None:
    result = answer_portfolio_question(
        "암이면 실제로 보상 받을 수 있어?", _named_insurer_policies("삼성화재")
    )

    assert result.status == "refused"
    assert "약관" in result.answer


def test_qa_answers_holdings_with_policy_citation() -> None:
    result = answer_portfolio_question("가입한 보험 목록 알려줘", _policies())

    assert result.status == "answered"
    assert "1건" in result.answer
    assert "건강보험" in result.answer
    assert result.citations[0].policy_id == "p1"


def test_qa_uses_confirmed_summary_for_amount_answer() -> None:
    result = answer_portfolio_question("전체 가입금액 합계가 얼마야?", _policies())

    assert result.status == "answered"
    assert "30,000,000원" in result.answer
    assert "실손형 담보는 가입금액 합계에 포함하지 않았습니다." in result.limitations
    assert result.citations[0].coverage_name == "암진단비"


def test_qa_filters_specific_coverage_amount_and_citations() -> None:
    policies = _policies()
    policies[0].보장목록.append(
        policies[0].보장목록[0].model_copy(update={"담보명": "질병수술비", "가입금액": "100만원"})
    )

    result = answer_portfolio_question("암진단비 가입금액은 얼마야?", policies)

    assert result.status == "answered"
    assert "30,000,000원" in result.answer
    assert "31,000,000원" not in result.answer
    assert {citation.coverage_name for citation in result.citations} == {"암진단비"}


def test_qa_resolves_curated_aliases_to_the_same_coverage_total() -> None:
    for question in (
        "허혈성심장질환진단비는 얼마야?",
        "허혈성심질환진단비(감액없음) 가입금액은 얼마야?",
    ):
        result = answer_portfolio_question(question, _alias_policies())

        assert result.status == "answered"
        assert "허혈성심질환진단비" in result.answer
        assert "30,000,000원" in result.answer
        assert {citation.coverage_name for citation in result.citations} == {"허혈성심질환진단비"}


def test_qa_does_not_fall_back_to_total_for_unknown_specific_coverage() -> None:
    result = answer_portfolio_question("골절진단비는 얼마야?", _policies())

    assert result.status == "no_data"
    assert result.citations == []
    assert "찾지 못" in result.answer


def test_qa_refuses_claim_conclusion_but_offers_grounded_adequacy_review() -> None:
    refused = answer_portfolio_question("암이면 실제로 보상 받을 수 있어?", _policies())
    review = answer_portfolio_question(
        "이 보험이면 충분해?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=lambda _system, _user: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert refused.status == "refused"
    assert refused.citations == []
    assert "약관" in refused.answer
    assert review.status == "answered"
    assert review.citations
    assert "함께 살펴볼 제안" in review.answer


def test_qa_returns_no_data_without_uploaded_policies() -> None:
    result = answer_portfolio_question("내 보험 목록 알려줘", [])

    assert result.status == "no_data"
    assert result.citations == []


def test_qa_passes_recent_history_and_demographics_to_llm() -> None:
    captured: dict[str, object] = {}

    def complete(_: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        return {
            "confirmed_fact": "암 진단 관련 담보의 가입 사실이 확인돼요.",
            "guidance": "일반 가이드로 생활비와 예산을 함께 비교해 보세요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": ["수술비도 함께 볼까요?"],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "그럼 무엇을 먼저 볼까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        history=[ConversationMessage(role="user", content="암 진단비부터 봐줘")],
        complete=complete,
    )

    assert result.generation == "llm"
    assert result.citations[0].evidence_id == "coverage:1"
    assert captured["history"] == [{"role": "user", "content": "암 진단비부터 봐줘"}]
    assert captured["demographics"] == {
        "age": 35,
        "gender": "여성",
        "source": "policy",
        "status": "verified_policy",
    }


def test_qa_masks_identifiers_in_question_and_history_before_llm() -> None:
    captured: dict[str, object] = {}
    question_identifier = "TESTBIRTH-A-1******"
    history_identifier = "TESTBIRTH-B4123456"

    def complete(_: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        assert question_identifier not in user
        assert history_identifier not in user
        assert "TESTBIRTH-A" not in user
        assert "TESTBIRTH-B" not in user
        return {
            "confirmed_fact": "암 진단 관련 담보의 가입 사실이 확인돼요.",
            "guidance": "일반 가이드로 생활비와 예산을 함께 비교해 보세요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        f"제 정보 {question_identifier}를 바탕으로 무엇을 준비할까요?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        history=[
            ConversationMessage(
                role="user",
                content=f"이전 정보는 {history_identifier}였어요.",
            )
        ],
        complete=complete,
    )

    assert result.generation == "llm"
    assert captured["question"] == "제 정보 ******-*******를 바탕으로 무엇을 준비할까요?"
    assert captured["history"] == [{"role": "user", "content": "이전 정보는 ******-*******였어요."}]


def test_qa_filters_hallucinated_numbers_and_invalid_evidence() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "치매진단비 1억원이 가입되어 있어요.",
            "guidance": "충분합니다.",
            "evidence_ids": ["coverage:999"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장의 좋은 점을 알려줘",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "fallback"
    assert "치매진단비" not in result.answer
    assert "1억원" not in result.answer


def test_qa_keeps_guidance_with_everyday_advisory_words() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실이 확인돼요.",
            "guidance": "지금 보장을 잘 유지하시면 좋아요. 필요할 때 함께 준비해요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장을 어떻게 준비할까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert "유지하시면 좋아요" in result.answer


def test_qa_allows_hedged_money_range_in_guidance() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실이 확인돼요.",
            "guidance": "정답은 아니지만 월 3만원 정도로 준비하는 분들도 있어요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장을 어떻게 준비할까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert "월 3만원" in result.answer


def test_qa_drops_unsafe_guidance_but_keeps_confirmed_answer() -> None:
    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실이 확인돼요.",
            "guidance": "지금 바로 암보험 가입하세요.",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "내 보장을 어떻게 준비할까?",
        _policies(),
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
        complete=complete,
    )

    assert result.generation == "llm"
    assert result.citations[0].evidence_id == "coverage:1"
    assert "가입하세요" not in result.answer
    assert any(section.basis == "confirmed_fact" for section in result.sections)
    assert all(section.basis != "general_guidance" for section in result.sections)


def test_qa_does_not_call_llm_for_claim_or_amount_questions() -> None:
    def forbidden(_: str, __: str) -> dict[str, object]:
        raise AssertionError("LLM should not be called")

    claim = answer_portfolio_question(
        "암 진단을 받으면 보험금을 받을 수 있어?", _policies(), complete=forbidden
    )
    amount = answer_portfolio_question(
        "암진단비 가입금액은 얼마야?", _policies(), complete=forbidden
    )

    assert claim.status == "refused"
    assert amount.status == "answered"
    assert "30,000,000원" in amount.answer
