from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.qa.agent.answer_spec import (
    build_amount_label_map,
    build_answer_spec,
    spec_mode_for,
)
from app.modules.qa.agent.contracts import RegisteredToolResult
from app.modules.qa.schemas import PortfolioQuestionResponse


def _result(answer: str, *evidence: ConsultationEvidence) -> RegisteredToolResult:
    return RegisteredToolResult(
        kind="coverage_total",
        response=PortfolioQuestionResponse(
            status="answered", answer=answer, citations=[], limitations=[]
        ),
        evidence=tuple(evidence),
        trust_level="deterministic",
    )


def test_label_map_assigns_confirmed_amounts_from_evidence() -> None:
    r1 = _result(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    r2 = _result(
        "암수술비 5,000,000원",
        ConsultationEvidence(
            id="c2", fact="암수술비 5,000,000원", coverage_name="암수술비", amount=5_000_000
        ),
    )
    label_map = build_amount_label_map([r1, r2])
    # 확정 금액이 라벨로 노출되고, 값에는 정규화된 표시 금액이 담긴다
    assert set(label_map.values()) == {"30,000,000원", "5,000,000원"}
    # 라벨은 안정적(결정적)이고 중복 금액은 하나로 합쳐지지 않는다(서로 다른 담보)
    assert len(label_map) == 2


def test_label_map_is_empty_without_amounts() -> None:
    r = _result("가입 사실 확인", ConsultationEvidence(id="c1", fact="가입 확인", amount=None))
    assert build_amount_label_map([r]) == {}


def test_facts_placeholderize_confirmed_amounts() -> None:
    r = _result(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered",
        answer="암진단비는 30,000,000원이 확인돼요.",
        citations=[],
        limitations=[],
    )
    spec = build_answer_spec(validated, [r])
    # 확정 금액이 스펙 facts에서는 자리표시자로 바뀐다
    joined = " ".join(spec.facts)
    assert "30,000,000원" not in joined
    assert "{{amt1}}" in joined
    # 원문 숫자는 인용 대조용으로 grounding_sources에 남는다
    assert any("30,000,000원" in s for s in spec.grounding_sources)
    assert spec.amounts["amt1"] == "30,000,000원"
    assert spec.mode == "grounded"


def test_mode_derivation() -> None:
    assert spec_mode_for("answered", True) == "grounded"
    assert spec_mode_for("answered", False) == "general_guidance"
    assert spec_mode_for("no_data", False) == "insufficient"
    assert spec_mode_for("refused", False) == "out_of_scope"
    assert spec_mode_for("clarify", True) == "general_guidance"


def test_quoted_number_not_in_amounts_stays_raw_in_facts() -> None:
    validated = PortfolioQuestionResponse(
        status="answered", answer="대기기간은 90일이에요.", citations=[], limitations=[]
    )
    spec = build_answer_spec(validated, [])
    assert "90일" in " ".join(spec.facts)  # 계산 금액이 아니므로 자리표시자 아님
    assert spec.mode == "general_guidance"
