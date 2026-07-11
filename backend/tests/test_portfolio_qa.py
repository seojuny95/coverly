from app.schemas.portfolio import PolicyInput
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
                },
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        )
    ]


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
    assert "실손형 담보는 합산하지 않았습니다." in result.limitations
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


def test_qa_does_not_fall_back_to_total_for_unknown_specific_coverage() -> None:
    result = answer_portfolio_question("골절진단비는 얼마야?", _policies())

    assert result.status == "no_data"
    assert result.citations == []
    assert "찾지 못했습니다" in result.answer


def test_qa_refuses_policy_terms_and_adequacy_questions() -> None:
    for question in ("암이면 실제로 보상 받을 수 있어?", "이 보험이면 충분해?"):
        result = answer_portfolio_question(question, _policies())
        assert result.status == "refused"
        assert result.citations == []
        assert "확인할 수 없습니다" in result.answer


def test_qa_returns_no_data_without_uploaded_policies() -> None:
    result = answer_portfolio_question("내 보험 목록 알려줘", [])

    assert result.status == "no_data"
    assert result.citations == []
