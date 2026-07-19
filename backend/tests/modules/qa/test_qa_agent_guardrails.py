import asyncio
from typing import cast

from agents import GuardrailFunctionOutput, RunContextWrapper
from agents.tool_context import ToolContext

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    GroundedToolAnswer,
    QaAgentDependencies,
    QaInputDecision,
)
from app.modules.qa.agent.definition import create_qa_agent, grounded_output_guardrail
from app.modules.qa.agent.grounding import numeric_claims_are_grounded
from app.modules.qa.agent.input_guardrail import (
    _guardrail_instructions,
    is_situational_turn,
    qa_input_guardrail,
)
from app.modules.qa.agent.prompt import build_agent_input
from app.modules.qa.agent.runtime import _unambiguous_tool_fallback
from app.modules.qa.agent.validation import validated_agent_response
from app.modules.qa.context import build_qa_context
from app.modules.qa.contracts import ConsultationEvidence
from app.modules.qa.schemas import ConversationMessage, PortfolioQuestionResponse
from app.modules.qa.tools.coverages import calculate_coverage_total
from app.modules.qa.tools.web_search import WebSearchResult


def _unused_web_search(*_args: object, **_kwargs: object) -> WebSearchResult:
    return WebSearchResult(status="unavailable")


def _dependencies(
    decision: dict[str, object],
) -> QaAgentDependencies:
    context = build_qa_context(
        "며칠 사이 보험 관련 공식 안내가 달라졌는지 확인해줘",
        [
            PolicyInput.model_validate(
                {
                    "id": "p1",
                    "기본정보": {"보험사": "테스트보험", "상품명": "건강보험"},
                    "보장목록": [],
                }
            )
        ],
        None,
        [],
    )
    return QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
        classify_input=lambda _system, _user: decision,
    )


def test_sdk_input_guardrail_stores_structured_freshness_decision() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": True,
            "insurance_request": "최근 보험 공식 안내 변경을 확인해줘",
            "out_of_scope_request": None,
            "reason": "시점에 따라 달라지는 공식 안내를 요구함",
        }
    )

    result = cast(
        GuardrailFunctionOutput,
        qa_input_guardrail.guardrail_function(
            RunContextWrapper(dependencies),
            create_qa_agent("gpt-4.1-mini"),
            "ignored",
        ),
    )

    assert result.tripwire_triggered is False
    assert dependencies.input_decision is not None
    assert dependencies.input_decision.requires_fresh_official_source is True


def test_sdk_input_guardrail_stores_situational_decision() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "is_situational": True,
            "insurance_request": "대장암 진단을 받았는데 관련 보장을 봐줘",
            "out_of_scope_request": None,
            "reason": "질병을 말하며 열린 도움을 구함",
        }
    )

    result = cast(
        GuardrailFunctionOutput,
        qa_input_guardrail.guardrail_function(
            RunContextWrapper(dependencies),
            create_qa_agent("gpt-4.1-mini"),
            "ignored",
        ),
    )

    assert result.tripwire_triggered is False
    assert dependencies.input_decision is not None
    assert dependencies.input_decision.is_situational is True
    assert is_situational_turn(dependencies) is True


def test_guardrail_instructions_route_coverly_meta_questions() -> None:
    # Meta/policy/capability questions about Coverly itself must be pulled to the
    # coverly scope, even when they contain insurance terms (약관) or read like
    # casual chat — otherwise they leak to insurance (unnecessary RAG) or greeting.
    # Normalize wrapping whitespace so the assertions don't depend on line breaks.
    instructions = " ".join(_guardrail_instructions().split())
    assert "insurance가 아니라 coverly" in instructions  # 약관 등 보험 용어가 있어도 coverly
    assert "greeting이 아니라 coverly" in instructions  # 기능 질문은 인사가 아님


def test_situational_turn_false_when_no_decision() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "insurance_request": "암진단비 가입금액만 알려줘",
            "out_of_scope_request": None,
            "reason": "특정 담보 금액만 물음",
        }
    )
    # 분류가 실행되기 전에는 상황형 아님
    assert is_situational_turn(dependencies) is False


def test_sdk_input_guardrail_blocks_out_of_scope_before_main_agent() -> None:
    dependencies = _dependencies(
        {
            "scope": "out_of_scope",
            "should_block": True,
            "requires_fresh_official_source": False,
            "insurance_request": None,
            "out_of_scope_request": "보험 상담 범위와 관계없는 요청",
            "reason": "보험 상담 범위와 관계없는 요청",
        }
    )

    result = cast(
        GuardrailFunctionOutput,
        qa_input_guardrail.guardrail_function(
            RunContextWrapper(dependencies),
            create_qa_agent("gpt-4.1-mini"),
            "ignored",
        ),
    )

    assert result.tripwire_triggered is True


def test_qa_masks_pii_at_every_model_boundary() -> None:
    question = "950524-1123456 010-1234-5678 test@example.com 보험을 확인해줘"
    history = [
        ConversationMessage(
            role="user",
            content="이전 연락처는 02-123-4567 old@example.com이야.",
        )
    ]
    context = build_qa_context(question, [], None, history)
    captured: dict[str, str] = {}

    def classify_input(_system: str, user: str) -> dict[str, object]:
        captured["input"] = user
        return {
            "scope": "insurance",
            "should_block": True,
            "requires_fresh_official_source": False,
            "insurance_request": "보험을 확인해줘",
            "out_of_scope_request": None,
            "reason": "보험 질문",
        }

    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
        classify_input=classify_input,
    )
    result = cast(
        GuardrailFunctionOutput,
        qa_input_guardrail.guardrail_function(
            RunContextWrapper(dependencies),
            create_qa_agent("gpt-4.1-mini"),
            "ignored",
        ),
    )

    captured["agent"] = build_agent_input(context)

    serialized = "\n".join(captured.values())
    for raw in (
        "950524-1123456",
        "010-1234-5678",
        "test@example.com",
        "02-123-4567",
        "old@example.com",
    ):
        assert raw not in serialized
    assert "[전화번호]" in serialized
    assert "[이메일]" in serialized
    assert result.tripwire_triggered is False
    assert dependencies.input_decision is not None
    assert dependencies.input_decision.should_block is False


def test_agent_does_not_force_a_keyword_selected_first_tool() -> None:
    agent = create_qa_agent("gpt-4.1-mini")

    assert agent.model_settings.tool_choice is None
    assert agent.input_guardrails == [qa_input_guardrail]
    assert {tool.name for tool in agent.tools} == {
        "list_policies",
        "find_coverages",
        "inspect_portfolio",
        "calculate_coverage_total",
        "find_overlapping_coverages",
        "get_claim_channels",
        "retrieve_official_guidance",
        "retrieve_policy_terms",
        "search_official_web",
    }


def test_sdk_output_guardrail_validates_and_caches_without_output_llm() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "insurance_request": "보험을 설명해줘",
            "out_of_scope_request": None,
            "reason": "보험 질문",
        }
    )

    result = cast(
        GuardrailFunctionOutput,
        grounded_output_guardrail.guardrail_function(
            RunContextWrapper(dependencies),
            create_qa_agent("gpt-4.1-mini"),
            AgentCounselorDraft(
                answer_mode="general_guidance",
                answer="가입한 보험의 구체 조건은 약관에서 확인이 필요해요.",
            ),
        ),
    )

    assert result.tripwire_triggered is False
    assert cast(dict[str, object], result.output_info)["valid"] is True
    assert dependencies.validated_response is not None
    assert dependencies.validated_response.status == "answered"


def test_sdk_output_guardrail_trips_when_validation_cannot_ground_draft() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "insurance_request": "가입금액을 알려줘",
            "out_of_scope_request": None,
            "reason": "보험 질문",
        }
    )

    result = cast(
        GuardrailFunctionOutput,
        grounded_output_guardrail.guardrail_function(
            RunContextWrapper(dependencies),
            create_qa_agent("gpt-4.1-mini"),
            AgentCounselorDraft(
                answer_mode="general_guidance",
                answer="가입금액은 3,000만원이에요.",
            ),
        ),
    )

    assert result.tripwire_triggered is True
    assert dependencies.validated_response is None


def test_generated_tool_result_is_not_used_as_guardrail_fallback() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": True,
            "insurance_request": "최신 안내를 찾아줘",
            "out_of_scope_request": None,
            "reason": "현재 정보가 필요함",
        }
    )
    dependencies.register(
        "web",
        PortfolioQuestionResponse(
            status="answered",
            answer="생성된 웹검색 답변",
            citations=[],
            limitations=[],
        ),
        trust_level="generated",
    )

    assert _unambiguous_tool_fallback(dependencies) is None


def test_deterministic_tool_result_remains_available_as_guardrail_fallback() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "insurance_request": "보험 개수를 알려줘",
            "out_of_scope_request": None,
            "reason": "증권 질문",
        }
    )
    response = PortfolioQuestionResponse(
        status="answered",
        answer="업로드된 보험은 1건입니다.",
        citations=[],
        limitations=[],
    )
    dependencies.register("policies", response, trust_level="deterministic")

    assert _unambiguous_tool_fallback(dependencies) == response


def test_non_web_result_cannot_be_guardrail_fallback_for_fresh_information() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": True,
            "insurance_request": "최신 보험 정책을 확인해줘",
            "out_of_scope_request": None,
            "reason": "최신 공식 정보가 필요함",
        }
    )
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=True,
        insurance_request="최신 보험 정책을 확인해줘",
        out_of_scope_request=None,
        reason="최신 공식 정보가 필요함",
    )
    dependencies.register(
        "policies",
        PortfolioQuestionResponse(
            status="answered",
            answer="현재 보유 증권은 1개예요.",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )

    assert _unambiguous_tool_fallback(dependencies) is None


def test_structured_value_grounding_checks_periods_percentages_and_dates() -> None:
    evidence = (
        ConsultationEvidence(
            id="terms:1",
            fact="가입 후 90일, 보험가입금액의 50%, 2026년 7월 기준",
        ),
    )

    assert numeric_claims_are_grounded(
        "가입 후 90일이며 50%를 지급하고 2026년 7월 기준이에요.",
        "",
        evidence,
    )
    assert not numeric_claims_are_grounded(
        "가입 후 180일이며 80%를 지급해요.",
        "",
        evidence,
    )
    assert numeric_claims_are_grounded(
        "가입금액은 6천만원이에요.",
        "가입금액은 60,000,000원입니다.",
        (),
    )


def test_insufficient_evidence_requires_a_recorded_tool_failure() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "insurance_request": "암진단비 대기기간을 확인해줘",
            "out_of_scope_request": None,
            "reason": "약관 질문",
        }
    )
    dependencies.unmatched("policy_terms", "No uploaded policy text matched.")

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            answer_mode="insufficient_evidence",
            answer="업로드된 증권 원문에서 대기기간을 확인하지 못했어요.",
        ),
        dependencies,
    )

    assert result.status == "no_data"
    assert result.generation == "llm"
    assert result.citations == []


def test_insufficient_evidence_uses_an_available_grounded_result() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "insurance_request": "암진단비를 확인해줘",
            "out_of_scope_request": None,
            "reason": "증권 질문",
        }
    )
    registered = dependencies.register(
        "coverage_lookup",
        PortfolioQuestionResponse(
            status="answered",
            answer="암진단비 가입 사실을 확인했습니다.",
            citations=[],
            limitations=[],
        ),
        trust_level="deterministic",
    )
    dependencies.unmatched("policy_terms", "No uploaded policy text matched.")

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            answer_mode="insufficient_evidence",
            selected_result_id=registered.result_id,
            answer="암진단비 가입 사실은 확인되지만 지급 조건은 원문에서 확인하지 못했어요.",
        ),
        dependencies,
    )

    assert result.status == "answered"
    assert "가입 사실은 확인" in result.answer


def test_general_source_cannot_replace_required_uploaded_policy_terms() -> None:
    dependencies = _dependencies(
        {
            "scope": "insurance",
            "should_block": False,
            "requires_fresh_official_source": False,
            "requires_uploaded_policy_terms": True,
            "insurance_request": "내 암진단비 대기기간을 확인해줘",
            "out_of_scope_request": None,
            "reason": "실제 계약 원문이 필요한 질문",
        }
    )
    dependencies.input_decision = QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=False,
        requires_uploaded_policy_terms=True,
        insurance_request="내 암진단비 대기기간을 확인해줘",
        out_of_scope_request=None,
        reason="실제 계약 원문이 필요한 질문",
    )
    registered = dependencies.register(
        "official_rag",
        PortfolioQuestionResponse(
            status="answered",
            answer="일반적인 암보험 보장개시일 안내입니다.",
            citations=[],
            limitations=["일반 공식자료입니다."],
        ),
    )

    result = validated_agent_response(
        dependencies.context,
        AgentCounselorDraft(
            selected_result_id=registered.result_id,
            answer="일반 기준을 가입한 보험 조건으로 설명합니다.",
        ),
        dependencies,
    )

    assert result.status == "no_data"
    assert "약관 원문" in result.answer
    assert result.citations == []


def test_amount_tool_rejects_unrequested_multiple_coverage_sum() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "테스트보험", "상품명": "건강보험"},
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "유사암진단비", "가입금액": "1,000만원", "지급유형": "정액"},
                ],
            }
        )
    ]
    context = build_qa_context("암진단비 합계", policies, None, [])
    dependencies = QaAgentDependencies(
        context=context,
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )
    arguments = (
        '{"coverage_names":["암진단비","유사암진단비"],'
        '"all_fixed_coverages":false,"combine_multiple_coverages":false}'
    )
    tool_context = ToolContext(
        dependencies,
        tool_name="calculate_coverage_total",
        tool_call_id="call-1",
        tool_arguments=arguments,
    )

    async def invoke() -> object:
        return await calculate_coverage_total.on_invoke_tool(tool_context, arguments)

    raw = asyncio.run(invoke())
    result = (
        raw
        if isinstance(raw, GroundedToolAnswer)
        else GroundedToolAnswer.model_validate_json(cast(str, raw))
    )

    assert result.matched is False
    assert "Multiple coverage identities" in (result.reason or "")
