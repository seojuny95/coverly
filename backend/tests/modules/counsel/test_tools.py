import asyncio
import json
from typing import cast

from agents import FunctionTool
from agents.tool_context import ToolContext

from app.modules.counsel.agent.tools.claims import ClaimChannelsResult, get_claim_channels
from app.modules.counsel.agent.tools.coverages import (
    CoverageNameInfo,
    CoverageTotalResult,
    FindCoveragesResult,
    OverlappingCoverage,
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
    list_coverage_names,
)
from app.modules.counsel.agent.tools.policies import PolicyListResult, list_policies
from app.modules.counsel.context import CounselContext
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


def _invoke_list_coverage_names(context: CounselContext) -> list[CoverageNameInfo]:
    return cast(list[CoverageNameInfo], _invoke(list_coverage_names, context))


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
) -> ClaimChannelsResult:
    return cast(
        ClaimChannelsResult,
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


def _driver_policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p9",
                "기본정보": {"보험사": "DB손해보험", "상품명": "참좋은운전자보험"},
                "보장목록": [
                    {
                        "담보명": "자동차사고변호사선임비용",
                        "가입금액": "3,000만원",
                        "가입금액숫자": 30_000_000,
                        "지급유형": "실손",
                    },
                    {
                        "담보명": "교통사고처리지원금",
                        "가입금액": "1억원",
                        "지급유형": "실손",
                    },
                ],
            }
        ),
    ]


def _symbol_named_policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p8",
                "기본정보": {"보험사": "미확인보험사", "상품명": "미확인상품"},
                "보장목록": [
                    {
                        "담보명": "---",
                        "가입금액": "1,000만원",
                        "가입금액숫자": 10_000_000,
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
                    "보험기간": {"시작일": "2026-01-01", "종료일": "2046-01-01"},
                    "만기일": "2046-01-01",
                    "납입기간": "20년납",
                    "피보험자정보": {"나이": 31, "성별": "남성", "생애단계": "성인"},
                },
                "보장목록": [],
                "분석상태": "완료",
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
    assert result.policies[0].policy_id == "p1"
    assert result.policies[0].분석상태 == "완료"
    assert result.policies[0].기본정보.보험사 == "NH농협손해보험"
    assert result.policies[0].기본정보.보험기간 == {
        "시작일": "2026-01-01",
        "종료일": "2046-01-01",
    }
    assert result.policies[0].기본정보.만기일 == "2046-01-01"
    assert result.policies[0].기본정보.납입기간 == "20년납"
    assert result.policies[0].기본정보.피보험자정보 is not None
    assert result.policies[0].기본정보.피보험자정보.나이 == 31


def test_missing_optional_fields_do_not_break_the_tool() -> None:
    policies = [
        PolicyInput.model_validate(
            {"id": "p1", "기본정보": {"보험사": "현대해상"}, "보장목록": []}
        ),
    ]
    context = CounselContext(policies=policies)

    result = _invoke_list_policies(context)

    assert result.count == 1
    assert result.policies[0].기본정보.보험사 == "현대해상"
    assert result.policies[0].기본정보.피보험자정보 is None


def test_empty_portfolio_returns_zero_count() -> None:
    context = CounselContext(policies=[])

    result = _invoke_list_policies(context)

    assert result.count == 0
    assert result.policies == []


def test_list_coverage_names_returns_every_distinct_name_sorted_with_its_type() -> None:
    context = CounselContext(policies=_policies())

    result = _invoke_list_coverage_names(context)

    assert result == [
        CoverageNameInfo(담보명="암진단비(유사암제외)", 지급유형="정액"),
        CoverageNameInfo(담보명="유사암진단비", 지급유형="정액"),
    ]


def test_list_coverage_names_surfaces_existing_type_and_category() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "현대해상", "상품명": "건강보험A"},
                "보장목록": [
                    {
                        "담보명": "긴급출동서비스",
                        "가입금액": "",
                        "지급유형": None,
                        "유형": "부가",
                        "보장분류": "서비스",
                    }
                ],
            }
        )
    ]
    context = CounselContext(policies=policies)

    result = _invoke_list_coverage_names(context)

    assert result == [
        CoverageNameInfo(
            담보명="긴급출동서비스",
            지급유형=None,
            유형="부가",
            보장분류="서비스",
        )
    ]


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
    assert result.matches[0].policy_id == "p1"
    assert result.matches[0].담보명 == "암진단비(유사암제외)"
    assert result.matches[0].가입금액숫자 == 20_000_000
    assert result.unmatched == []


def test_find_coverages_surfaces_existing_coverage_explanation() -> None:
    policies = [
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
                        "유형": "담보",
                        "보장분류": "암",
                        "보장내용": None,
                        "해설": "암 진단을 받았을 때 정액 보장을 확인하는 담보예요.",
                    },
                    {
                        "담보명": "입원일당",
                        "가입금액": "3만원",
                        "가입금액숫자": 30_000,
                        "지급유형": "정액",
                        "보장내용": "질병 또는 상해로 입원한 경우 1일당 지급",
                    },
                ],
            }
        ),
    ]
    context = CounselContext(policies=policies)

    generated = _invoke_find_coverages(context, ["암진단비"])
    wording = _invoke_find_coverages(context, ["입원일당"])

    assert generated.matches[0].해설 == "암 진단을 받았을 때 정액 보장을 확인하는 담보예요."
    assert generated.matches[0].설명근거 == "generated_guidance"
    assert generated.matches[0].유형 == "담보"
    assert generated.matches[0].보장분류 == "암"
    assert wording.matches[0].보장내용 == "질병 또는 상해로 입원한 경우 1일당 지급"
    assert wording.matches[0].설명근거 == "policy_wording"


def test_find_coverages_does_not_confuse_substring_names() -> None:
    # "암진단비" is a substring of both "암진단비(유사암제외)" and "유사암진단비", but they
    # are distinct coverages. Asking for "암진단비" alone must not silently match either.
    context = CounselContext(policies=_policies())

    result = _invoke_find_coverages(context, ["암진단비"])

    assert result.matches == []
    assert len(result.unmatched) == 1
    assert result.unmatched[0].requested_name == "암진단비"
    # Both are offered as candidates to ask back with — the user did say 암진단비, and
    # both coverages contain it. Candidates are never auto-selected, so widening them
    # cannot misattribute an amount; only `matches` above carries that risk.
    assert result.unmatched[0].candidates == ["암진단비(유사암제외)", "유사암진단비"]


def test_find_coverages_absorbs_spacing_and_notation_differences() -> None:
    # Users type spacing and full-width variants of the same coverage. Notation
    # differences are absorbed, but the meaningful "(유사암제외)" qualifier is kept.
    context = CounselContext(policies=_policies())

    result = _invoke_find_coverages(context, ["암 진단비（유사암 제외）"])

    assert len(result.matches) == 1
    assert result.matches[0].담보명 == "암진단비(유사암제외)"
    assert result.unmatched == []


def test_find_coverages_suggests_candidates_containing_every_requested_word() -> None:
    # "변호사 비용" is not a prefix of the held "자동차사고변호사선임비용", so prefix-only
    # candidates found nothing. Coverages containing every requested word must surface.
    context = CounselContext(policies=_driver_policies())

    result = _invoke_find_coverages(context, ["변호사 비용"])

    assert result.matches == []
    assert result.unmatched[0].candidates == ["자동차사고변호사선임비용"]


def test_find_coverages_never_matches_names_with_no_canonical_identity() -> None:
    # Canonicalization strips punctuation, so a symbol-only request and a symbol-only
    # coverage name both reduce to an empty key. An empty key is not an identity and
    # must never match, or an unrelated amount would be attributed to the request.
    context = CounselContext(policies=_symbol_named_policies())

    result = _invoke_find_coverages(context, ["???"])

    assert result.matches == []
    assert result.unmatched[0].requested_name == "???"
    assert result.unmatched[0].candidates == []


def test_find_coverages_reports_unmatched_names_without_guessing() -> None:
    context = CounselContext(policies=_policies())

    result = _invoke_find_coverages(context, ["유사암진단비", "존재하지않는담보"])

    assert len(result.matches) == 1
    assert result.matches[0].담보명 == "유사암진단비"
    assert len(result.unmatched) == 1
    assert result.unmatched[0].requested_name == "존재하지않는담보"
    assert result.unmatched[0].candidates == []


def _policies_with_same_insurer_tiers() -> list[PolicyInput]:
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
                        "담보명": "암진단비",
                        "가입금액": "2,000만원",
                        "가입금액숫자": 20_000_000,
                        "지급유형": "정액",
                    },
                ],
            }
        ),
    ]


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
    assert result.excluded[0].policy_id == "p1"
    assert result.excluded[0].담보명 == "실손의료비"
    assert result.unmatched == []


def test_calculate_coverage_total_reports_unmatched_names() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_calculate_coverage_total(context, ["존재하지않는담보"])

    assert result.total == 0
    assert result.included == []
    assert len(result.unmatched) == 1


def test_calculate_coverage_total_does_not_blindly_sum_same_insurer_tiers() -> None:
    # One insurer lists 암진단비 twice -- these can be tiers of a single contract,
    # so they must not be folded into one confident total; they surface for review.
    context = CounselContext(policies=_policies_with_same_insurer_tiers())

    result = _invoke_calculate_coverage_total(context, ["암진단비"])

    assert result.total == 0
    assert result.included == []
    assert result.excluded == []
    assert len(result.needs_review) == 1
    assert result.needs_review[0].담보명 == "암진단비"
    assert len(result.needs_review[0].rows) == 2


def test_find_overlapping_coverages_reports_names_held_in_multiple_policies() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_find_overlapping_coverages(context)

    assert len(result) == 1
    assert result[0].담보명 == "암진단비"
    assert len(result[0].policies) == 2
    assert result[0].policies[0].policy_id == "p1"


def test_find_overlapping_coverages_excludes_names_held_once() -> None:
    # 실손의료비 only appears in one policy, so it must not be reported as an overlap.
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_find_overlapping_coverages(context)

    names = {item.담보명 for item in result}
    assert "실손의료비" not in names


def test_get_claim_channels_returns_verified_channels_for_matched_insurers() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, ["암진단비"])

    names = {insurer.name for insurer in result.channels.insurers}
    assert names == {"현대해상", "삼성화재"}
    assert all(insurer.customer_center for insurer in result.channels.insurers)
    assert result.unmatched == []


def test_get_claim_channels_reports_unmatched_names_instead_of_returning_empty_silently() -> None:
    # A coverage-name mismatch (e.g. a name carried over unresolved from an earlier
    # turn) must surface as `unmatched` with candidates, not a silent empty channel
    # list — otherwise the agent reports "no claim channel data" for insurers that
    # actually have verified reference data.
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, ["암진단"])

    assert result.channels.insurers == []
    assert len(result.unmatched) == 1
    assert result.unmatched[0].requested_name == "암진단"
    assert result.unmatched[0].candidates == ["암진단비"]


def test_get_claim_channels_returns_empty_when_no_coverage_matches() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, ["존재하지않는담보"])

    assert result.channels.insurers == []
    assert len(result.unmatched) == 1


def test_get_claim_channels_without_names_covers_the_whole_portfolio() -> None:
    # "실손의료비는 어디로 청구해?" reaches here with no coverage name when the
    # planner does not fill one in. Every insurer on file is the right answer,
    # not "we could not find a coverage to look up".
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, [])

    insurers = {insurer.name for insurer in result.channels.insurers}
    assert insurers == {"현대해상", "삼성화재"}
    assert result.unmatched == []


def _indemnity_policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p10",
                "기본정보": {"보험사": "삼성화재", "상품명": "실손의료보험"},
                "보장목록": [
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        ),
    ]


def test_get_claim_channels_surfaces_the_medical_indemnity_service_for_실손_coverage() -> None:
    # 실손의료비 is claimed through 실손24, the same verified resource the analysis
    # screen already shows. Counsel should not have to hardcode or omit it.
    context = CounselContext(policies=_indemnity_policies())

    result = _invoke_get_claim_channels(context, ["실손의료비"])

    assert result.channels.medical_indemnity is not None
    assert result.channels.medical_indemnity.name == "실손24"


def test_get_claim_channels_omits_the_medical_indemnity_service_for_other_coverage() -> None:
    context = CounselContext(policies=_policies_with_indemnity_and_overlap())

    result = _invoke_get_claim_channels(context, ["암진단비"])

    assert result.channels.medical_indemnity is None


def test_get_claim_channels_without_names_includes_it_when_the_portfolio_has_실손() -> None:
    context = CounselContext(policies=_indemnity_policies())

    result = _invoke_get_claim_channels(context, [])

    assert result.channels.medical_indemnity is not None
