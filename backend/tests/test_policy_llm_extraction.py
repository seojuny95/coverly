from app.services.policy.llm_extraction import _build_response_format, get_insurer_candidates


def test_llm_insurer_field_is_constrained_to_catalog() -> None:
    candidates = get_insurer_candidates()

    assert {"DB손해보험", "NH농협손해보험", "현대해상화재보험", "흥국화재"}.issubset(
        set(candidates)
    )

    response_format = _build_response_format(candidates)
    insurer_schema = response_format["format"]["schema"]["properties"]["보험사"]

    assert insurer_schema["type"] == ["string", "null"]
    assert insurer_schema["enum"] == [*candidates, None]


def test_llm_response_format_uses_strict_json_schema() -> None:
    response_format = _build_response_format(get_insurer_candidates())

    assert response_format["format"]["type"] == "json_schema"
    assert response_format["format"]["strict"] is True
    assert response_format["format"]["schema"]["additionalProperties"] is False
    assert set(response_format["format"]["schema"]["required"]) == {
        "보험사",
        "상품명",
        "증권번호",
        "계약자",
        "피보험자",
        "보험기간",
        "만기일",
        "납입기간",
        "보험료",
    }
