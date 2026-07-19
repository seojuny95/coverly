import asyncio
import json
from typing import cast

from agents import FunctionTool
from agents.tool_context import ToolContext

from app.modules.counsel.context import CounselContext
from app.modules.counsel.tools.claims import get_claim_channels
from app.modules.counsel.tools.coverages import (
    CoverageTotalResult,
    FindCoveragesResult,
    OverlappingCoverage,
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
    list_coverage_names,
)
from app.modules.counsel.tools.policies import PolicyListResult, list_policies
from app.modules.portfolio.schemas import PolicyInput
from app.modules.reference_data.contracts import ClaimChannelBlock


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


def _invoke_calculate_coverage_total(
    context: CounselContext, coverage_names: list[str]
) -> CoverageTotalResult:
    return cast(
        CoverageTotalResult,
        _invoke(calculate_coverage_total, context, json.dumps({"coverage_names": coverage_names})),
    )


def _invoke_find_overlapping_coverages(context: CounselContext) -> list[OverlappingCoverage]:
    return cast(list[OverlappingCoverage], _invoke(find_overlapping_coverages, context))


def _invoke_get_claim_channels(
    context: CounselContext, coverage_names: list[str]
) -> ClaimChannelBlock:
    return cast(
        ClaimChannelBlock,
        _invoke(get_claim_channels, context, json.dumps({"coverage_names": coverage_names})),
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


def _policies_with_indemnity_and_overlap() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "현대해상", "상품명": "건강보험A"},
                "보장목록": [
                    {
                        "담보명": "암진단비",
                        "가입금액": "3,000만원",
                        "가입금액숫자": 30_000_000,
                        "지급유형": "정액",
                    },
                    {
                        "담보명": "실손의료비",
                        "가입금액": "급여 90%",
                        "가입금액숫자": None,
                        "지급유형": "실손",
                    },
                ],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "p2",
                "기본정보": {"보험사": "삼성화재", "상품명": "건강보험B"},
                "보장목록": [
                    {
                        "담보명": "암진단비",
                        "가입금액": "2,000만원",
                        "가입금액숫자": 20_000_000,
                        "지급유형": "정액",
                    },
                ],
            }
        ),
    ]


def test_calculate_coverage_total_sums_only_fixed_amount_coverages() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_calculate_coverage_total(context, ["암진단비", "실손의료비"])

    assert result.total == 50_000_000
    assert len(result.included) == 2
    assert len(result.excluded) == 1
    assert result.excluded[0].담보명 == "실손의료비"
    assert result.unmatched == []


def test_calculate_coverage_total_reports_unmatched_names() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_calculate_coverage_total(context, ["존재하지않는담보"])

    assert result.total == 0
    assert result.included == []
    assert len(result.unmatched) == 1


def test_find_overlapping_coverages_reports_names_held_in_multiple_policies() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_find_overlapping_coverages(context)

    assert len(result) == 1
    assert result[0].담보명 == "암진단비"
    assert len(result[0].policies) == 2


def test_find_overlapping_coverages_excludes_names_held_once() -> None:
    # 실손의료비 only appears in one policy, so it must not be reported as an overlap.
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_find_overlapping_coverages(context)

    names = {item.담보명 for item in result}
    assert "실손의료비" not in names


def test_get_claim_channels_returns_verified_channels_for_matched_insurers() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, ["암진단비"])

    names = {insurer.name for insurer in result.insurers}
    assert names == {"현대해상", "삼성화재"}
    assert all(insurer.customer_center for insurer in result.insurers)


def test_get_claim_channels_returns_empty_when_no_coverage_matches() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, ["존재하지않는담보"])

    assert result.insurers == []
