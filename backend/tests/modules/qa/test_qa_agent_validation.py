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
