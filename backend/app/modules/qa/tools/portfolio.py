"""Agent SDK tool for portfolio-wide premium and essential-coverage facts."""

from agents import RunContextWrapper, function_tool

from app.modules.counsel.facts import portfolio as portfolio_facts
from app.modules.qa.context import QaContext


@function_tool
def portfolio_overview(
    wrapper: RunContextWrapper[QaContext],
) -> portfolio_facts.PortfolioFactBundle:
    """보험료 합계와 필수 보장(암·뇌·심장·사망·실손 등) 확보 현황을 한 번에 확인합니다.

    "부족한 보장 있어?", "전체적으로 어때?", "보험료 얼마나 나가?" 같은 전반적인
    질문에는 이 도구를 먼저 부르세요. essential_coverages의 status가
    needs_review나 not_confirmed인 항목은, 사용자가 원하면 그 보장을 채우는
    것을 권할 수 있습니다 — 다만 특정 보험사나 상품을 지목하지 마세요. 여기
    담긴 금액도 그대로 인용하고 암산하지 마세요.

    각 essential_coverages 항목에는 reference_min_amount/reference_max_amount(권장
    범위), reference_amount_label, reference_basis(범위의 근거 설명), reference_sources
    (출처 목록, 각 항목에 label·url·reliability·caveat 포함)가 함께 옵니다. 이 범위와
    출처가 있으면 "충분해요/부족해요"처럼 단정하지 말고 "일반적으로는 X~Y원 수준을
    참고하는데(출처: ...), 지금은 Z원이 확인돼요"처럼 확인된 사실과 범위를 함께
    인용하세요. medical_indemnity처럼 범위가 없는 항목(reference_min_amount/
    reference_max_amount가 null)은 금액 비교 없이 가입 여부·중복만 이야기하세요.
    death 항목에는 guidance_situation/guidance_reason(부양가족·미성년 자녀·부채
    여부에 따른 상황별 가이드)이 추가로 붙을 수 있습니다.

    premium.benchmark가 있으면 이 연령대의 적정 보험료 참고 범위
    (suggested_min_premium~suggested_max_premium, age_band_label)와 출처가
    들어 있습니다. 보험료가 적정한지 물으면 monthly_total과 이 범위를 함께
    인용하되, 출처가 업계 가이드(B/C등급)라는 점을 "일반적으로는" 같은 말로
    드러내고 단정하지 마세요. benchmark가 null이면(나이가 확인되지 않는 등)
    비교 없이 monthly_total만 말하세요.
    """

    return portfolio_facts.build_portfolio_fact_bundle(wrapper.context.policies)
