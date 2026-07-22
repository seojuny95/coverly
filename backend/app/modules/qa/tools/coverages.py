"""Agent SDK tools for coverage discovery, lookup, totals, and overlaps."""

from agents import RunContextWrapper, function_tool

from app.modules.qa.context import QaContext
from app.modules.qa.facts import coverages as coverage_facts


@function_tool
def list_coverage_names(
    wrapper: RunContextWrapper[QaContext],
) -> list[coverage_facts.CoverageNameInfo]:
    """사용자 증권 전체의 정확한 담보명과 지급유형을 모두 나열합니다.

    정확한 담보명이 확실하지 않으면(예: "(유사암제외)", "(감액없음)" 같은 접미사가
    붙는 경우가 많습니다) find_coverages를 부르기 전에 먼저 이 도구를 호출하세요.
    """

    return coverage_facts.list_coverage_name_facts(wrapper.context.policies)


@function_tool
def find_coverages(
    wrapper: RunContextWrapper[QaContext],
    coverage_names: list[str],
) -> coverage_facts.FindCoveragesResult:
    """사용자 증권에서 특정 담보를 정확한 이름으로 조회합니다.

    반환된 가입금액을 답변에 그대로 옮기세요. 암산하거나 반올림하지 말고,
    다른 담보나 다른 보험사의 금액과 섞어 쓰지 마세요. 요청한 이름이 정확히
    일치하지 않지만 결과에 candidates가 있으면, 임의로 하나를 골라 답하지
    말고 후보를 제시해 사용자에게 되물으세요.

    Args:
        coverage_names: 조회할 정확한 담보명 목록입니다. 정확한 철자가
            확실하지 않으면 먼저 list_coverage_names를 호출하세요.
    """

    return coverage_facts.find_coverage_facts(wrapper.context.policies, coverage_names)


@function_tool
def calculate_coverage_total(
    wrapper: RunContextWrapper[QaContext],
    coverage_names: list[str],
) -> coverage_facts.CoverageTotalResult:
    """지정한 담보들의 가입금액 합계를 정확히 계산합니다. 직접 암산하지 마세요.

    합계는 코드가 계산하며, 실손형처럼 고정 가입금액이 없는 담보는 합계에서
    제외되고 excluded에 이유와 함께 보고됩니다(0으로 취급하지 않습니다).
    같은 담보가 한 보험사에서 여러 번 확인되면 단계별로 나뉜 보장일 수 있어
    합계에 넣지 않고 needs_review에 따로 보고합니다 — 이 경우 total만 단정하지
    말고 needs_review 항목을 사용자에게 함께 알리고 각 금액을 확인하도록 안내하세요.
    사용자가 명시적으로 요청한 담보만 coverage_names에 넣으세요.
    "정액형 보장", "실손형 담보" 같은 카테고리·유형 이름은 담보명이 아니므로
    coverage_names에 절대 그대로 넣지 마세요 — 먼저 list_coverage_names로
    지급유형별 정확한 담보명을 골라낸 뒤 넘기세요. total은 이 도구가 돌려준
    값을 그대로 인용하세요.

    Args:
        coverage_names: 합산할 정확한 담보명 목록입니다.
    """

    return coverage_facts.calculate_coverage_total_fact(wrapper.context.policies, coverage_names)


@function_tool
def find_overlapping_coverages(
    wrapper: RunContextWrapper[QaContext],
) -> list[coverage_facts.OverlappingCoverage]:
    """같은 담보가 두 개 이상의 증권에 함께 들어 있는 경우를 모두 나열합니다.

    각 항목의 보상방식을 반드시 함께 전하세요. 정액형(각각지급)은 계약마다 전액
    지급되므로 중복이나 낭비라고 말하면 안 되고, 실손형(비례보상)만 여러 건이어도
    실제 부담한 의료비 안에서만 보상됩니다. 보상방식이 확인필요면 어느 쪽인지
    단정하지 마세요.
    """

    return coverage_facts.find_overlapping_coverage_facts(wrapper.context.policies)
