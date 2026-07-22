"""Agent SDK tool for verified insurer claim channels."""

from agents import RunContextWrapper, function_tool

from app.modules.qa.context import QaContext
from app.modules.qa.facts import claims as claim_facts


@function_tool
def get_claim_channels(
    wrapper: RunContextWrapper[QaContext],
    coverage_names: list[str],
) -> claim_facts.ClaimChannelsResult:
    """청구와 관련된 담보의 보험사 고객센터·앱·청구 링크를 확인합니다.

    반환되는 연락처·링크는 검증된 참조 데이터에서만 나오며, 직접 지어내지
    마세요. 이 도구는 청구 채널만 알려주며 실제 지급 여부는 확정하지 않습니다.

    Args:
        coverage_names: 청구와 관련된 정확한 담보명 목록입니다. unmatched에
            candidates가 있으면 그중 정확한 이름으로 다시 호출하세요.
    """

    return claim_facts.get_claim_channel_facts(wrapper.context.policies, coverage_names)
