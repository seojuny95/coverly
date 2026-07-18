import asyncio
import json
from typing import Any, cast

from agents.tool_context import ToolContext

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.context import build_qa_context
from app.modules.qa.tools.claims import get_claim_channels
from app.modules.qa.tools.coverages import (
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
)
from app.modules.qa.tools.policies import inspect_portfolio, list_policies
from app.modules.qa.tools.web_search import WebSearchResult


def _unused_web_search(*_args: object, **_kwargs: object) -> WebSearchResult:
    return WebSearchResult(status="unavailable")


def _policies() -> list[PolicyInput]:
    rows = [
        ("p1", "삼성화재", "건강보험", "암진단비", 30_000_000, "질병", "정액"),
        ("p2", "DB손해보험", "자녀보험", "암진단비", 20_000_000, "질병", "정액"),
        ("p3", "현대해상", "자동차보험", "대물배상", None, "자동차", "실손"),
    ]
    return [
        PolicyInput.model_validate(
            {
                "id": policy_id,
                "기본정보": {
                    "보험사": insurer,
                    "상품명": product,
                    "보험분류": classification,
                },
                "보장목록": [
                    {
                        "담보명": coverage,
                        "가입금액숫자": amount,
                        "지급유형": payment_type,
                    }
                ],
            }
        )
        for policy_id, insurer, product, coverage, amount, classification, payment_type in rows
    ]


def _dependencies(question: str) -> QaAgentDependencies:
    return QaAgentDependencies(
        context=build_qa_context(question, _policies(), None, []),
        complete=None,
        official_answer=None,
        web_search=_unused_web_search,
    )


def _invoke(
    tool: Any,
    dependencies: QaAgentDependencies,
    arguments: dict[str, object],
) -> GroundedToolAnswer:
    raw_arguments = json.dumps(arguments, ensure_ascii=False)
    context = ToolContext(
        dependencies,
        tool_name=tool.name,
        tool_call_id="call-1",
        tool_arguments=raw_arguments,
    )

    async def invoke() -> object:
        return await tool.on_invoke_tool(context, raw_arguments)

    raw = asyncio.run(invoke())
    if isinstance(raw, GroundedToolAnswer):
        return raw
    return GroundedToolAnswer.model_validate_json(cast(str, raw))


def test_policy_inventory_returns_every_uploaded_classification() -> None:
    result = _invoke(list_policies, _dependencies("가입한 보험을 모두 보여줘"), {})

    assert result.matched is True
    assert result.response is not None
    assert "3건" in result.response.answer
    assert {item.policy_id for item in result.evidence} == {"p1", "p2", "p3"}


def test_coverage_tools_use_model_supplied_entities_and_structured_totals() -> None:
    dependencies = _dependencies("암진단비 가입금액 합계는?")

    found = _invoke(find_coverages, dependencies, {"coverage_names": ["암진단비"]})
    total = _invoke(
        calculate_coverage_total,
        dependencies,
        {
            "coverage_names": ["암진단비"],
            "all_fixed_coverages": False,
            "combine_multiple_coverages": False,
        },
    )

    assert found.matched is True
    assert len(found.evidence) == 1
    assert total.response is not None
    assert "50,000,000원" in total.response.answer


def test_overlap_and_snapshot_tools_use_precomputed_portfolio_facts() -> None:
    dependencies = _dependencies("겹치는 보장을 봐줘")

    overlap = _invoke(find_overlapping_coverages, dependencies, {})
    snapshot = _invoke(inspect_portfolio, dependencies, {})

    assert overlap.matched is True
    assert any("2개 증권" in item.fact for item in overlap.evidence)
    assert snapshot.matched is True
    assert 0 < len(snapshot.evidence) <= 24


def test_claim_channel_tool_uses_explicit_coverage_and_auto_selection() -> None:
    health = _invoke(
        get_claim_channels,
        _dependencies("암진단비 청구 경로를 알려줘"),
        {
            "coverage_names": ["암진단비"],
            "include_auto_policies": False,
            "include_medical_indemnity_service": False,
        },
    )
    auto = _invoke(
        get_claim_channels,
        _dependencies("자동차 사고 청구 경로를 알려줘"),
        {
            "coverage_names": ["대물배상"],
            "include_auto_policies": True,
            "include_medical_indemnity_service": False,
        },
    )

    assert health.response is not None and health.response.claim_channels is not None
    assert {item.name for item in health.response.claim_channels.insurers} == {
        "삼성화재",
        "DB손해보험",
    }
    assert auto.response is not None and auto.response.claim_channels is not None
    assert [item.name for item in auto.response.claim_channels.insurers] == ["현대해상"]
