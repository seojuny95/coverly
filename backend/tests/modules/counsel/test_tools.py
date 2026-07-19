import asyncio
import json
from typing import cast

from agents import FunctionTool
from agents.tool_context import ToolContext

from app.modules.counsel.context import CounselContext
from app.modules.counsel.tools.coverages import (
    FindCoveragesResult,
    find_coverages,
    list_coverage_names,
)
from app.modules.counsel.tools.policies import PolicyListResult, list_policies
from app.modules.portfolio.schemas import PolicyInput


def _invoke(tool: FunctionTool, context: CounselContext, arguments: str = "{}") -> object:
    tool_context = ToolContext(
        context,
        tool_name=tool.name,
        tool_call_id="call-1",
        tool_arguments=arguments,
    )

    async def invoke() -> object:
        return await tool.on_invoke_tool(tool_context, arguments)

    return asyncio.run(invoke())


def _invoke_list_policies(context: CounselContext) -> PolicyListResult:
    return cast(PolicyListResult, _invoke(list_policies, context))


def _invoke_list_coverage_names(context: CounselContext) -> list[str]:
    return cast(list[str], _invoke(list_coverage_names, context))


def _invoke_find_coverages(
    context: CounselContext, coverage_names: list[str]
) -> FindCoveragesResult:
    return cast(
        FindCoveragesResult,
        _invoke(find_coverages, context, json.dumps({"coverage_names": coverage_names})),
    )


def _policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "NH농협손해보험", "상품명": "가성비건강보험"},
                "보장목록": [
                    {
                        "담보명": "암진단비(유사암제외)",
                        "가입금액": "2,000만원",
                        "가입금액숫자": 20_000_000,
                        "지급유형": "정액",
                    },
                    {
                        "담보명": "유사암진단비",
                        "가입금액": "2,000만원",
                        "가입금액숫자": 20_000_000,
                        "지급유형": "정액",
                    },
                ],
            }
        ),
    ]


def test_returns_basic_info_for_every_policy_with_an_explicit_count() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {
                    "보험사": "NH농협손해보험",
                    "상품명": "가성비건강보험",
                    "피보험자정보": {"나이": 31, "성별": "남성", "생애단계": "성인"},
                },
                "보장목록": [],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "p2",
                "기본정보": {"보험사": "현대해상", "상품명": "Hicar 다이렉트"},
                "보장목록": [],
            }
        ),
    ]
    context = CounselContext(policies=policies)

    result = _invoke_list_policies(context)

    assert result.count == 2
    assert len(result.policies) == 2
    assert result.policies[0].보험사 == "NH농협손해보험"
    assert result.policies[0].피보험자정보 is not None
    assert result.policies[0].피보험자정보.나이 == 31


def test_missing_optional_fields_do_not_break_the_tool() -> None:
    policies = [
        PolicyInput.model_validate(
            {"id": "p1", "기본정보": {"보험사": "현대해상"}, "보장목록": []}
        ),
    ]
    context = CounselContext(policies=policies)

    result = _invoke_list_policies(context)

    assert result.count == 1
    assert result.policies[0].보험사 == "현대해상"
    assert result.policies[0].피보험자정보 is None


def test_empty_portfolio_returns_zero_count() -> None:
    context = CounselContext(policies=[])

    result = _invoke_list_policies(context)

    assert result.count == 0
    assert result.policies == []


def test_list_coverage_names_returns_every_distinct_name_sorted() -> None:
    context = CounselContext(policies=_policies())

    result = _invoke_list_coverage_names(context)

    assert result == sorted(["암진단비(유사암제외)", "유사암진단비"])


def test_find_coverages_docstring_tells_the_model_to_ask_instead_of_guessing() -> None:
    # The candidate-handling behavior lives in the tool's own description (sent
    # to the model on every turn) rather than in agent.py's global instructions,
    # since it's specific to how this one tool's output should be handled.
    assert find_coverages.description is not None
    assert "candidates" in find_coverages.description
    assert "되물" in find_coverages.description


def test_find_coverages_matches_exact_names_only() -> None:
    context = CounselContext(policies=_policies())

    result = _invoke_find_coverages(context, ["암진단비(유사암제외)"])

    assert len(result.matches) == 1
    assert result.matches[0].담보명 == "암진단비(유사암제외)"
    assert result.matches[0].가입금액숫자 == 20_000_000
    assert result.unmatched == []


def test_find_coverages_does_not_confuse_substring_names() -> None:
    # "암진단비" is a substring of both "암진단비(유사암제외)" and "유사암진단비", but they
    # are distinct coverages. Asking for "암진단비" alone must not silently match either.
    context = CounselContext(policies=_policies())

    result = _invoke_find_coverages(context, ["암진단비"])

    assert result.matches == []
    assert len(result.unmatched) == 1
    assert result.unmatched[0].requested_name == "암진단비"
    # Prefix candidates surface "암진단비(유사암제외)" (starts with 암진단비) but never
    # "유사암진단비" (starts with 유사, not 암진단비) — no substring confusion.
    assert result.unmatched[0].candidates == ["암진단비(유사암제외)"]


def test_find_coverages_reports_unmatched_names_without_guessing() -> None:
    context = CounselContext(policies=_policies())

    result = _invoke_find_coverages(context, ["유사암진단비", "존재하지않는담보"])

    assert len(result.matches) == 1
    assert result.matches[0].담보명 == "유사암진단비"
    assert len(result.unmatched) == 1
    assert result.unmatched[0].requested_name == "존재하지않는담보"
    assert result.unmatched[0].candidates == []
