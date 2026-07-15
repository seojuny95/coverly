from app.modules.coverage.indemnity import classify_indemnity
from app.modules.portfolio.schemas import CoverageInput, PolicyInput


def _coverage(**values: object) -> CoverageInput:
    return CoverageInput.model_validate({"담보명": "담보", **values})


def _policy(*, category: str = "건강보험", tags: list[str] | None = None) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "기본정보": {
                "보험사": "테스트보험",
                "상품명": "테스트상품",
                "보험분류": category,
                "상품태그": tags or [],
            },
            "보장목록": [],
        }
    )


def test_indemnity_category_matching_is_normalized() -> None:
    result = classify_indemnity(
        _coverage(담보명="상해입원의료비", 보장분류="실 손 형"),
        policy=_policy(),
    )

    assert result.payment_basis == "indemnity"
    assert result.coverage_domain == "medical_expense"
    assert result.medical_indemnity_status == "confirmed"


def test_non_medical_actual_loss_reimbursement_is_excluded() -> None:
    result = classify_indemnity(
        _coverage(담보명="자동차사고벌금(대물, 실손)", 지급유형="실손"),
        policy=_policy(category="손해보험", tags=["자동차보험"]),
    )

    assert result.payment_basis == "indemnity"
    assert result.coverage_domain == "auto"
    assert result.medical_indemnity_status == "excluded"


def test_non_medical_actual_loss_terms_are_excluded_even_with_health_category() -> None:
    cases = (
        ("벌금(실손)", "legal_cost"),
        ("대물배상(실손)", "liability"),
        ("휴대품손해(실손)", "property_damage"),
        ("화재손해(실손)", "property_damage"),
    )

    for coverage_name, expected_domain in cases:
        result = classify_indemnity(
            _coverage(담보명=coverage_name, 지급유형="실손"),
            policy=_policy(category="건강보험"),
        )

        assert result.payment_basis == "indemnity"
        assert result.coverage_domain == expected_domain
        assert result.medical_indemnity_status == "excluded"


def test_travel_medical_expense_can_still_be_medical_indemnity() -> None:
    result = classify_indemnity(
        _coverage(담보명="해외의료비(실손)", 지급유형="실손"),
        policy=_policy(category="손해보험", tags=["여행자보험"]),
    )

    assert result.coverage_domain == "medical_expense"
    assert result.medical_indemnity_status == "confirmed"


def test_auto_medical_expense_stays_outside_medical_indemnity() -> None:
    result = classify_indemnity(
        _coverage(담보명="자동차상해 의료비", 지급유형="실손"),
        policy=_policy(category="손해보험", tags=["자동차보험"]),
    )

    assert result.coverage_domain == "auto"
    assert result.medical_indemnity_status == "excluded"
