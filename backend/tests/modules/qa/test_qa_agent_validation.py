import pytest

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaAgentUnavailable,
    QaInputDecision,
)
from app.modules.qa.agent.validation import validated_agent_response
from app.modules.qa.context import build_qa_context
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.modules.qa.tools.evidence import overlap_evidence
from app.modules.qa.tools.web_search import WebSearchResult


def _unused_web_search(*_args: object, **_kwargs: object) -> WebSearchResult:
    return WebSearchResult(status="unavailable")


def _policies() -> list[PolicyInput]:
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
                        "담보명": "암진단비",
                        "가입금액숫자": amount,
                        "지급유형": "정액",
                    }
                ],
            }
        )
        for policy_id, insurer, amount in (
            ("p1", "보험사A", 30_000_000),
            ("p2", "보험사B", 20_000_000),
        )
    ]


def _dependencies(question: str) -> QaAgentDependencies:
    return QaAgentDependencies(
        context=build_qa_context(question, _policies(), None, []),
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )


def test_consultation_uses_only_explicit_valid_evidence_ids_for_citations() -> None:
    dependencies = _dependencies("겹치는 보장을 보여줘")
    evidence = overlap_evidence(dependencies.context)
    registered = dependencies.register(
        "consultation",
        PortfolioQuestionResponse(
            status="answered",
            answer="선택한 근거로만 답하세요.",
            citations=[],
            limitations=[],
        ),
        evidence=evidence,
    )

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id,
            answer="두 증권에 같은 지급 성격의 담보가 있어요.",
            evidence_ids=[item.id for item in evidence],
        ),
        dependencies,
    )

    assert [item.evidence_id for item in result.citations] == [item.id for item in evidence[:3]]


def test_consultation_rejects_unregistered_evidence_id() -> None:
    dependencies = _dependencies("겹치는 보장을 보여줘")
    evidence = overlap_evidence(dependencies.context)
    registered = dependencies.register(
        "consultation",
        PortfolioQuestionResponse(
            status="answered",
            answer="선택한 근거로만 답하세요.",
            citations=[],
            limitations=[],
        ),
        evidence=evidence,
    )

    with pytest.raises(QaAgentUnavailable):
        validated_agent_response(
            dependencies.context,
            AgentCounselorDraft(
                selected_result_id=registered.result_id,
                answer="근거가 없는 답변",
                evidence_ids=["coverage:not-registered"],
            ),
            dependencies,
        )


def test_fresh_information_requires_a_web_result() -> None:
    dependencies = _dependencies("최신 보험 정책을 알려줘")
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=True,
        insurance_request="최신 보험 정책을 알려줘",
        out_of_scope_request=None,
        reason="시점에 따라 달라지는 정보",
    )

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            answer_mode="general_guidance",
            answer="공식 자료를 확인해야 해요.",
        ),
        dependencies,
    )

    assert result.status == "no_data"
    assert "공식 웹사이트 검색 근거" in result.answer


def test_single_web_result_is_recovered_without_a_selected_result_id() -> None:
    dependencies = _dependencies("최신 보험 정책을 알려줘")
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=True,
        insurance_request="최신 보험 정책을 알려줘",
        out_of_scope_request=None,
        reason="시점에 따라 달라지는 정보",
    )
    web_response = PortfolioQuestionResponse(
        status="answered",
        answer="공식 웹검색으로 확인한 안내입니다.",
        citations=[
            AnswerCitation(
                policy_id=None,
                insurer=None,
                product_name=None,
                source_id="web:1",
            )
        ],
        limitations=[],
    )
    dependencies.register("web", web_response)

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(answer=web_response.answer),
        dependencies,
    )

    assert result.answer == web_response.answer
    assert result.citations == web_response.citations


def test_required_web_result_replaces_an_explicit_non_web_selection() -> None:
    dependencies = _dependencies("최신 보험 정책을 알려줘")
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=True,
        insurance_request="최신 보험 정책을 알려줘",
        out_of_scope_request=None,
        reason="시점에 따라 달라지는 정보",
    )
    non_web = dependencies.register(
        "official_rag",
        PortfolioQuestionResponse(
            status="answered",
            answer="기존 공식자료 답변",
            citations=[],
            limitations=[],
        ),
    )
    dependencies.register(
        "web",
        PortfolioQuestionResponse(
            status="answered",
            answer="최신 공식 웹 답변",
            citations=[],
            limitations=[],
        ),
    )

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=non_web.result_id,
            answer="최신 공식 웹 답변",
        ),
        dependencies,
    )

    assert result.answer == "최신 공식 웹 답변"


def test_general_guidance_without_tool_data_remains_available() -> None:
    dependencies = _dependencies("어떤 보험 질문을 할 수 있어?")

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            answer_mode="general_guidance",
            answer="올려주신 증권을 함께 살펴보는 상담을 도와드려요.",
        ),
        dependencies,
    )

    assert result.status == "answered"
    assert result.citations == []


def test_mixed_consultation_keeps_the_validated_answer_instead_of_internal_prompt() -> None:
    dependencies = _dependencies("내 보장을 봐주고 날씨도 알려줘")
    dependencies.input_decision = QaInputDecision(
        scope="mixed",
        should_block=False,
        requires_fresh_official_source=False,
        insurance_request="내 보장을 봐줘",
        out_of_scope_request="날씨도 알려줘",
        reason="보험과 범위 밖 요청이 함께 있음",
    )
    evidence = overlap_evidence(dependencies.context)
    registered = dependencies.register(
        "consultation",
        PortfolioQuestionResponse(
            status="answered",
            answer="제공된 evidence 중 질문에 필요한 항목만 고르세요.",
            citations=[],
            limitations=[],
        ),
        evidence=evidence,
    )

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id,
            answer="두 증권에 같은 지급 성격의 담보가 있어요.",
            evidence_ids=[item.id for item in evidence],
        ),
        dependencies,
    )

    assert result.answer.startswith("두 증권에")
    assert "제공된 evidence" not in result.answer
    assert "보험 상담 범위 밖" in result.answer


def test_synthesis_across_two_results_grounds_numbers_from_union() -> None:
    dependencies = _dependencies("두 증권 암진단비 각각 얼마야?")
    a = dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="보험사A 암진단비 30,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )
    b = dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="보험사B 암진단비 20,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )
    assert a.result_id != b.result_id

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=None,
            answer="보험사A는 3,000만원, 보험사B는 2,000만원이에요.",
        ),
        dependencies,
    )

    assert "3,000만원" in result.answer
    assert result.status == "answered"


def _two_coverage_results(dependencies: QaAgentDependencies) -> None:
    dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="보험사A 암진단비 30,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )
    dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="보험사B 암진단비 20,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )


def test_synthesis_number_absent_from_all_results_degrades_without_the_number() -> None:
    # Task 4b: the ungrounded number no longer hard-fails the whole turn; it is
    # dropped and the confirmed individual results are surfaced instead.
    dependencies = _dependencies("두 증권 암진단비 합계 얼마야?")
    _two_coverage_results(dependencies)

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=None,
            answer="두 증권 합계는 9,999만원이에요.",  # union에 없음
        ),
        dependencies,
    )

    assert "9,999" not in result.answer
    assert "30,000,000" in result.answer


def test_general_guidance_prose_does_not_become_empty_cited_synthesis() -> None:
    # 근거 없는 프로즈(숫자 0, evidence_ids 0)가 answered+인용0 으로 새면 안 된다
    dependencies = _dependencies("내 보장 어때?")
    _two_coverage_results(dependencies)
    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            answer_mode="general_guidance",
            answer="가입하신 담보들을 보면 대체로 잘 준비돼 있어요.",
        ),
        dependencies,
    )
    # degrade: 확인된 도구 원문이 반영되고, "근거 있는 척 빈 인용 answered"가 아니다
    assert "30,000,000" in result.answer or "3,000만" in result.answer
    assert not (
        result.status == "answered" and result.citations == [] and "30,000,000" not in result.answer
    )


def test_synthesis_preserves_web_result_citations() -> None:
    dependencies = _dependencies("최신 안내랑 내 담보 같이 봐줘")
    dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="암진단비 30,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )
    dependencies.register(
        "web",
        PortfolioQuestionResponse(
            status="answered",
            answer="최신 공식 안내입니다.",
            citations=[
                AnswerCitation(
                    policy_id=None,
                    insurer=None,
                    product_name=None,
                    source_id="web:1",
                )
            ],
            limitations=[],
        ),
    )
    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=None,
            answer="암진단비는 3,000만원이고, 최신 안내도 확인했어요.",
        ),
        dependencies,
    )
    assert any(c.source_id == "web:1" for c in result.citations)


def test_ungrounded_number_degrades_to_confirmed_results_not_total_failure() -> None:
    dependencies = _dependencies("두 증권 합계 얼마야?")
    _two_coverage_results(dependencies)
    # 지어낸 9,999만원: 모델 문장은 버리되, 확인된 개별 결과로 degrade (턴 전체 실패 아님)
    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=None,
            answer="두 증권 합계는 9,999만원이에요.",
        ),
        dependencies,
    )
    assert "9,999" not in result.answer  # 지어낸 숫자 제거
    assert "30,000,000" in result.answer or "3,000만" in result.answer  # 확인된 근거 반영


def test_policy_terms_required_blocks_multi_result_synthesis() -> None:
    dependencies = _dependencies("내 암보험 지급조건 두 개 다 알려줘")
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=False,
        requires_uploaded_policy_terms=True,
        insurance_request="지급조건",
        out_of_scope_request=None,
        reason="원문 필요",
    )
    _two_coverage_results(dependencies)
    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=None,
            answer="A는 3,000만원, B는 2,000만원이에요.",
        ),
        dependencies,
    )
    # 종합이 발동하지 않고 원문-필요 거절로 간다
    assert result.status == "no_data"
    assert "약관" in result.answer


def test_mixed_scope_synthesis_keeps_scope_disclaimer() -> None:
    dependencies = _dependencies("두 증권 암진단비 보고 날씨도 알려줘")
    dependencies.input_decision = QaInputDecision(
        scope="mixed",
        should_block=False,
        requires_fresh_official_source=False,
        insurance_request="두 증권 암진단비 봐줘",
        out_of_scope_request="날씨도 알려줘",
        reason="보험과 범위 밖 요청이 함께 있음",
    )
    dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="보험사A 암진단비 30,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )
    dependencies.register(
        "coverage_total",
        PortfolioQuestionResponse(
            status="answered",
            answer="보험사B 암진단비 20,000,000원 확인",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=None,
            answer="보험사A는 3,000만원, 보험사B는 2,000만원이에요.",
        ),
        dependencies,
    )

    assert "보험 상담 범위 밖" in result.answer


def _policy_terms_required_decision() -> QaInputDecision:
    return QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=False,
        requires_uploaded_policy_terms=True,
        insurance_request="지급조건",
        out_of_scope_request=None,
        reason="원문 필요",
    )


def test_policy_terms_missing_session_gives_not_ready_message() -> None:
    dependencies = _dependencies("내 보험 지급조건 알려줘")
    dependencies.input_decision = _policy_terms_required_decision()
    dependencies.unmatched("policy_terms", "No uploaded policy-text session exists.")

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(answer_mode="insufficient_evidence", answer="확인이 어려워요."),
        dependencies,
    )

    assert result.status == "no_data"
    assert "준비" in result.answer or "읽는 중" in result.answer


def test_policy_terms_no_match_gives_not_found_in_policy_message() -> None:
    dependencies = _dependencies("내 보험 지급조건 알려줘")
    dependencies.input_decision = _policy_terms_required_decision()
    dependencies.unmatched("policy_terms", "No uploaded policy text matched.")

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(answer_mode="insufficient_evidence", answer="확인이 어려워요."),
        dependencies,
    )

    assert result.status == "no_data"
    assert "확인하지 못했습니다" in result.answer
    assert "준비" not in result.answer


def test_policy_terms_missing_distinguishes_no_session_vs_no_match() -> None:
    session_missing = _dependencies("내 보험 지급조건 알려줘")
    session_missing.input_decision = _policy_terms_required_decision()
    session_missing.unmatched("policy_terms", "No uploaded policy-text session exists.")

    no_match = _dependencies("내 보험 지급조건 알려줘")
    no_match.input_decision = _policy_terms_required_decision()
    no_match.unmatched("policy_terms", "Policy evidence was insufficient.")

    draft = AgentCounselorDraft(answer_mode="insufficient_evidence", answer="확인이 어려워요.")
    session_result = validated_agent_response(session_missing.context, draft, session_missing)
    match_result = validated_agent_response(no_match.context, draft, no_match)

    assert session_result.answer != match_result.answer


def test_insurance_scope_rejects_an_out_of_scope_final_mode() -> None:
    dependencies = _dependencies("가입한 보험은 몇 개야?")
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=False,
        insurance_request="가입한 보험은 몇 개야?",
        out_of_scope_request=None,
        reason="보험 증권 질문",
    )

    with pytest.raises(QaAgentUnavailable):
        validated_agent_response(
            dependencies.context,
            AgentCounselorDraft(answer_mode="out_of_scope", answer="보험 상담 범위 밖입니다."),
            dependencies,
        )
