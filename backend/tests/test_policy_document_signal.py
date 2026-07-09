from app.services.policy_document import classify_policy_document


def test_policy_document_signal_accepts_common_policy_fields() -> None:
    result = classify_policy_document("보험증권 증권번호 계약자 피보험자 보험기간 보험료 보험금액")

    assert result.is_likely_policy is True
    assert result.score == 7
    assert result.matched_terms == [
        "보험증권",
        "증권번호",
        "계약자",
        "피보험자",
        "보험기간",
        "보험료",
        "보험금액",
    ]


def test_policy_document_signal_rejects_generic_documents() -> None:
    result = classify_policy_document("회의록 참석자 안건 결정사항 다음 회의 일정")

    assert result.is_likely_policy is False
    assert result.score == 0
    assert result.matched_terms == []
