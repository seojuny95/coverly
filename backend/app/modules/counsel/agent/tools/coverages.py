"""Agent SDK tools for coverage discovery, lookup, totals, and overlaps."""

from agents import RunContextWrapper, function_tool

from app.modules.counsel.context import CounselContext
from app.modules.counsel.facts import coverages as coverage_facts

CoverageNameInfo = coverage_facts.CoverageNameInfo
CoverageTotalResult = coverage_facts.CoverageTotalResult
FindCoveragesResult = coverage_facts.FindCoveragesResult
OverlappingCoverage = coverage_facts.OverlappingCoverage


@function_tool
def list_coverage_names(wrapper: RunContextWrapper[CounselContext]) -> list[CoverageNameInfo]:
    """사용자 증권 전체의 정확한 담보명과 지급유형을 모두 나열합니다.

    정확한 담보명이 확실하지 않으면(예: "(유사암제외)", "(감액없음)" 같은 접미사가
    붙는 경우가 많습니다) find_coverages를 부르기 전에 먼저 이 도구를 호출하세요.
    "정액형만 합쳐줘"처럼 지급유형으로 걸러야 하는 질문에는, 여기서 지급유형으로
    먼저 골라낸 정확한 담보명만 calculate_coverage_total에 넘기세요 — "정액형
    보장"처럼 카테고리 이름 자체를 담보명으로 넘기지 마세요.
    """

    return coverage_facts.list_coverage_name_facts(wrapper.context.policies)


@function_tool
def find_coverages(
    wrapper: RunContextWrapper[CounselContext],
    coverage_names: list[str],
) -> FindCoveragesResult:
    """사용자 증권에서 특정 담보를 정확한 이름으로 조회합니다.

    요청한 이름이 정확히 일치하지 않지만 결과에 candidates가 있으면, 임의로
    하나를 골라 답하지 마세요. 후보를 제시하고 사용자에게 어떤 담보를
    말하는지 되물으세요.

    Args:
        coverage_names: 조회할 정확한 담보명 목록입니다. 정확한 철자가
            확실하지 않으면(예: "(유사암제외)" 같은 접미사) 먼저
            list_coverage_names를 호출하세요. 띄어쓰기나 표기 차이는 자동으로
            흡수되지만, 일치하지 않는 이름은 임의로 추측하거나 합쳐지지 않고
            요청한 낱말을 모두 포함한 후보 이름으로 보고됩니다.
    """

    return coverage_facts.find_coverage_facts(wrapper.context.policies, coverage_names)


@function_tool
def calculate_coverage_total(
    wrapper: RunContextWrapper[CounselContext],
    coverage_names: list[str],
) -> CoverageTotalResult:
    """지정한 담보들의 가입금액 합계를 정확히 계산합니다. 직접 암산하지 마세요.

    합계는 코드가 계산하며, 실손형처럼 고정 가입금액이 없는 담보는 합계에서
    제외되고 excluded에 이유와 함께 보고됩니다(0으로 취급하지 않습니다).
    사용자가 명시적으로 요청한 담보만 coverage_names에 넣으세요 — 사용자가
    언급하지 않은 관련 담보를 임의로 추가해 합치지 마세요.
    "정액형 보장", "실손형 담보" 같은 카테고리·유형 이름은 담보명이 아니므로
    coverage_names에 절대 그대로 넣지 마세요 — 사용자가 유형으로 말했다면
    반드시 먼저 list_coverage_names를 호출해 지급유형별로 정확한 담보명을
    골라낸 뒤, 그 담보명들만 여기 넘기세요.

    Args:
        coverage_names: 합산할 정확한 담보명 목록입니다. 정확한 철자가
            확실하지 않거나 사용자가 유형(정액형 등)으로만 말했다면 먼저
            list_coverage_names를 호출하세요.
    """

    return coverage_facts.calculate_coverage_total_fact(wrapper.context.policies, coverage_names)


@function_tool
def find_overlapping_coverages(
    wrapper: RunContextWrapper[CounselContext],
) -> list[OverlappingCoverage]:
    """같은 담보명이 두 개 이상의 증권에 중복 가입된 경우를 모두 나열합니다.

    중복 여부만 사실대로 알려주고, 해지하거나 줄이라고 권유하지 마세요.
    """

    return coverage_facts.find_overlapping_coverage_facts(wrapper.context.policies)
