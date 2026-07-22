"""Agent SDK tool for auto/driver/travel/fire policy coverage facts."""

from agents import RunContextWrapper, function_tool

from app.modules.qa.context import QaContext
from app.modules.qa.facts import special_policies as special_policy_facts


@function_tool
def special_policy_overview(
    wrapper: RunContextWrapper[QaContext],
) -> special_policy_facts.SpecialPolicyFactBundle:
    """자동차·운전자·여행자·화재보험에서 사고 상황별 보장이 실제로 있는지 확인합니다.

    구체적인 사고나 상황을 물으면 이 도구를 먼저 부르세요. 예를 들어:

    - "주차장에서 차를 박았는데", "접촉사고 났어", "상대방이 다쳤어",
      "내 차 수리비", "자차 처리하면?" — 자동차보험
    - "변호사 비용도 돼?", "형사합의금", "벌금 나왔는데" — 운전자보험
    - "여행 중에 다쳤어", "휴대폰 잃어버렸어", "해외에서 병원 갔어" — 여행자보험
    - "화재로 집이 탔어", "불나서 옆집까지", "누수·화재 배상" — 화재보험

    반환된 analyses의 각 coverage_check에서 status_label과
    matched_coverage_names를 그대로 인용하고, 담보명을 지어내지 마세요.
    matched_coverage_names가 비어 있는(미확인) 항목을 미가입이라고 단정하지
    말고, 지급 한도·면책 조건은 약관을 더 확인해야 한다고 안내하세요.
    analyses가 비어 있으면 해당 종류의 보험이 있는 것처럼 답하지 말고 note를
    따르세요.
    """

    return special_policy_facts.build_special_policy_facts(wrapper.context.policies)
